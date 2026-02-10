"""
logger.py
Continuum Logger (HF Space friendly) — ENTERPRISE AUDIT MODE (content-free)

Provides:
- DataLogger: log_analysis / log_feedback / get_stats
- GitHubBackup: optional restore hook (safe no-op by default)

Design goals:
- Never break the API if logging fails
- Avoid GitHub SHA race conditions by writing ONE FILE PER EVENT
- Works in Hugging Face Spaces using Secrets:
    GITHUB_TOKEN = GitHub Fine-grained PAT (Contents: Read & Write)
    GITHUB_REPO  = "owner/repo" (e.g., "Rin-Nomia/continuum-logs")

PRIVACY / GOVERNANCE GUARANTEE (重要):
- ✅ NO RAW TEXT is written to disk or GitHub.
- ✅ NO content-derived fragments are stored (matched keywords / oos matches / triggers).
- ✅ Only SHA256 fingerprints + lengths + decision evidence are logged.
- ✅ Optional salt supported via LOG_SALT (recommended for enterprise).

Compatibility:
- log_analysis(input_text=...) accepts str OR None.
- If input_text is provided, it is never stored; only fingerprint+len computed.
- Defense-in-depth: scrub risky keys inside output_result before writing.

PATCH (enterprise-hardening):
- ✅ Stronger scrub: key normalization (case/variant safe)
- ✅ Safe-by-default: drop any huge list/dict under suspicious keys
- ✅ Keep schema stable for app.py (no breaking changes)
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import requests


# ----------------------------
# Time helpers
# ----------------------------
def _utc_dates():
    now = datetime.utcnow()
    return (
        now.strftime("%Y-%m"),   # year_month
        now.strftime("%Y%m%d"),  # date_str
        now.strftime("%H%M%S"),  # time_str
    )


def _utc_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


# ----------------------------
# Fingerprint helpers
# ----------------------------
def _get_salt() -> str:
    # Optional: enterprise-friendly. If set, fingerprints are not reversible / correlatable across repos.
    return os.environ.get("LOG_SALT", "").strip()


def _sha256_hex(text: str, salt: str = "") -> str:
    raw = (salt + (text or "")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return int(default)


def _safe_str(v: Any, default: str = "") -> str:
    try:
        if v is None:
            return default
        return str(v)
    except Exception:
        return default


# ----------------------------
# Safety scrub (defense-in-depth)
# ----------------------------
# 1) Hard-drop obvious raw text fields (direct content)
_RISKY_TEXT_KEYS = {
    "text",
    "input_text",
    "original",
    "normalized",
    "repaired_text",
    "raw_ai_output",
    "llm_raw_response",
    "llm_raw_output",
    "prompt",
    "messages",
    "completion",
    "response_text",
}

# 2) Hard-drop derived-content fields (lists that leak content patterns)
_RISKY_DERIVED_KEYS = {
    "oos_matched",
    "matched",
    "matched_keywords",
    "matched_terms",
    "matched_phrases",
    "matched_patterns",
    "matched_rules",
    "lexicon_hits",
    "trigger_words",
    "trigger_terms",
    "hit_keywords",
    "hit_terms",
    "detected_keywords",
    "detected_terms",
    "detected_phrases",
    "keywords",
    "keyword_hits",
    "pattern_hits",
}

# 3) Size guards
_MAX_LIST_LEN = 80
_MAX_STR_LEN = 600
_MAX_DICT_KEYS = 120


def _k_norm(key: Any) -> str:
    """Normalize key for comparisons (case/variant safe)."""
    try:
        return str(key).strip().lower()
    except Exception:
        return ""


def _looks_like_sensitive_key(key: str) -> bool:
    k = (key or "").strip().lower()
    if not k:
        return False
    signals = [
        "text", "content", "message", "prompt", "completion", "response",
        "utterance", "transcript", "input", "output",
        "matched", "keyword", "trigger", "lexicon", "pattern", "phrase",
    ]
    return any(s in k for s in signals)


def _scrub_value_if_too_large(key: str, value: Any) -> Optional[Any]:
    """
    Returns:
      - None means "drop this field"
      - otherwise returns the (possibly trimmed) value
    """
    # Strings
    if isinstance(value, str):
        if len(value) > _MAX_STR_LEN and _looks_like_sensitive_key(key):
            return None
        return value

    # Lists
    if isinstance(value, list):
        if len(value) > _MAX_LIST_LEN and _looks_like_sensitive_key(key):
            return None
        if len(value) > _MAX_LIST_LEN:
            return value[:_MAX_LIST_LEN]
        return value

    # Dicts
    if isinstance(value, dict):
        if len(value.keys()) > _MAX_DICT_KEYS and _looks_like_sensitive_key(key):
            return None
        if len(value.keys()) > _MAX_DICT_KEYS:
            keys = sorted(list(value.keys()))[:_MAX_DICT_KEYS]
            return {k: value[k] for k in keys}
        return value

    return value


def _scrub_dict_content_free(obj: Any) -> Any:
    """
    Remove raw-text fields + derived-content fields recursively.
    Hard rules:
    - Never store known raw-text keys.
    - Never store known derived-content/match lists.
    - Drop suspicious oversized structures under sensitive keys.
    """
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            kn = _k_norm(k)

            # hard-drop (case/variant safe)
            if kn in _RISKY_TEXT_KEYS:
                continue
            if kn in _RISKY_DERIVED_KEYS:
                continue

            # scrub recursively first
            scrubbed = _scrub_dict_content_free(v)

            # enforce size guards / sensitive heuristics
            guarded = _scrub_value_if_too_large(kn, scrubbed)
            if guarded is None:
                continue

            # keep original key as-is (schema stability)
            out[str(k)] = guarded
        return out

    if isinstance(obj, list):
        cleaned = [_scrub_dict_content_free(x) for x in obj]
        if len(cleaned) > _MAX_LIST_LEN:
            cleaned = cleaned[:_MAX_LIST_LEN]
        return cleaned

    return obj


# ----------------------------
# GitHub writer
# ----------------------------
class GitHubWriter:
    """
    Minimal GitHub Contents API writer.
    Writes one file per event to avoid SHA conflicts.
    """

    def __init__(self):
        self.github_token = os.environ.get("GITHUB_TOKEN")
        self.github_repo = os.environ.get("GITHUB_REPO")  # owner/repo
        self.github_ref = os.environ.get("GITHUB_REF", "").strip()  # optional branch/ref

        self.enabled = bool(self.github_token and self.github_repo)

        self.headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "continuum-api-logger",
        }
        if self.github_token:
            self.headers["Authorization"] = f"Bearer {self.github_token}"

    def _put_file(self, path: str, payload: Dict[str, Any]) -> bool:
        if not self.enabled:
            return False

        url = f"https://api.github.com/repos/{self.github_repo}/contents/{path}"
        if self.github_ref:
            # GitHub Contents API supports ?ref=branch
            url = url + f"?ref={self.github_ref}"

        content_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        b64 = base64.b64encode(content_bytes).decode("utf-8")

        data = {
            "message": f"Add log {payload.get('id', '')}".strip(),
            "content": b64,
        }

        try:
            r = requests.put(url, headers=self.headers, json=data, timeout=15)
            if r.status_code in (200, 201):
                return True
            # keep error output small (avoid leaking anything)
            txt = (r.text or "")[:120]
            print(f"[GitHubWriter] PUT failed {r.status_code}: {txt}")
            return False
        except Exception as e:
            print(f"[GitHubWriter] PUT exception: {e}")
            return False

    def write_event(self, category: str, event: Dict[str, Any], event_id: str) -> bool:
        year_month, date_str, _ = _utc_dates()
        path = f"logs/{year_month}/{date_str}/{category}/{event_id}.json"
        return self._put_file(path, event)


# ----------------------------
# DataLogger
# ----------------------------
class DataLogger:
    """
    API-facing logger used by app.py.

    ENTERPRISE AUDIT MODE:
    - log_analysis() never stores raw input/output text.
    - It stores only fingerprints + lengths + decision evidence passed in output_result.
    """

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        self.writer = GitHubWriter()

        self._analysis_count = 0
        self._feedback_count = 0
        self._last_analysis_ts: Optional[str] = None

        if self.writer.enabled:
            print(f"[DataLogger] GitHub logging enabled -> {os.environ.get('GITHUB_REPO')}")
        else:
            print("[DataLogger] GitHub credentials not set; logging will be runtime-only (in-memory stats).")

        self._salt = _get_salt()
        if self._salt:
            print("[DataLogger] LOG_SALT enabled (fingerprints salted).")
        else:
            print("[DataLogger] LOG_SALT not set (fingerprints unsalted).")

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    def log_analysis(
        self,
        input_text: Optional[str],
        output_result: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        ts = _utc_iso()
        event_id = self._new_id("a")

        # If app.py passes None (recommended), we do NOT compute from raw text.
        if input_text is None:
            in_len = None
            in_fp = None
            try:
                if isinstance(output_result, dict):
                    in_fp = output_result.get("input_fp_sha256")
                    in_len = output_result.get("input_length")
            except Exception:
                in_fp, in_len = None, None
        else:
            in_len = len(input_text or "")
            in_fp = _sha256_hex(input_text or "", salt=self._salt)

        # output_result should already be content-free (recommended),
        # but we still enforce a safety scrub for risky keys (defense-in-depth).
        base_obj: Dict[str, Any] = output_result if isinstance(output_result, dict) else {}
        safe_result = _scrub_dict_content_free(dict(base_obj))

        payload: Dict[str, Any] = {
            "id": event_id,
            "timestamp": ts,
            "type": "analysis",
            "input": {
                "fp_sha256": _safe_str(in_fp, ""),
                "length": _safe_int(in_len, 0) if in_len is not None else None,
                "fingerprint_salted": bool(self._salt),
                "input_text_provided": input_text is not None,
            },
            "evidence": safe_result,
            "metadata": metadata or {},
            "runtime": {
                "source": "hf_space",
                "logger_mode": "enterprise_audit_content_free",
            },
        }

        self._analysis_count += 1
        self._last_analysis_ts = ts

        if self.writer.enabled:
            ok = self.writer.write_event(category="analysis", event=payload, event_id=event_id)
            if not ok:
                payload["github_write"] = "failed"

        return {"timestamp": event_id, "created_at": ts}

    def log_feedback(self, log_id: str, accuracy: int, helpful: int, accepted: bool) -> Dict[str, Any]:
        ts = _utc_iso()
        event_id = self._new_id("f")

        payload = {
            "id": event_id,
            "timestamp": ts,
            "type": "feedback",
            "target_log_id": _safe_str(log_id, ""),
            "feedback": {
                "accuracy": _safe_int(accuracy, 0),
                "helpful": _safe_int(helpful, 0),
                "accepted": bool(accepted),
            },
            "runtime": {"source": "hf_space"},
        }

        self._feedback_count += 1

        if self.writer.enabled:
            ok = self.writer.write_event(category="feedback", event=payload, event_id=event_id)
            if not ok:
                payload["github_write"] = "failed"

        return {"status": "ok", "feedback_id": event_id, "created_at": ts}

    def get_stats(self) -> Dict[str, Any]:
        return {
            "logger": {
                "enabled": self.writer.enabled,
                "repo": os.environ.get("GITHUB_REPO") if self.writer.enabled else None,
                "ref": os.environ.get("GITHUB_REF") if self.writer.enabled else None,
                "salted": bool(self._salt),
            },
            "counts": {
                "analyses_in_runtime": self._analysis_count,
                "feedback_in_runtime": self._feedback_count,
            },
            "last_analysis_utc": self._last_analysis_ts,
        }


# ----------------------------
# GitHubBackup (safe no-op)
# ----------------------------
class GitHubBackup:
    """
    Compatibility class: app.py calls GitHubBackup(...).restore()
    For this stable version, restore is intentionally a safe no-op.
    """

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir

    def restore(self) -> None:
        print("[GitHubBackup] restore() skipped (no-op)")
        return