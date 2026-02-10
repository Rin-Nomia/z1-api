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
- ✅ Only SHA256 fingerprints + lengths + decision evidence are logged.
- ✅ Optional salt supported via LOG_SALT (recommended for enterprise).
"""

from __future__ import annotations

import json
import os
import uuid
import hashlib
from datetime import datetime
from typing import Any, Dict, Optional

import requests


def _utc_dates():
    now = datetime.utcnow()
    return (
        now.strftime("%Y-%m"),   # year_month
        now.strftime("%Y%m%d"),  # date_str
        now.strftime("%H%M%S"),  # time_str
    )


def _utc_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


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


class GitHubWriter:
    """
    Minimal GitHub Contents API writer.
    Writes one file per event to avoid SHA conflicts.
    """

    def __init__(self):
        self.github_token = os.environ.get("GITHUB_TOKEN")
        self.github_repo = os.environ.get("GITHUB_REPO")  # owner/repo

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

        content_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        b64 = __import__("base64").b64encode(content_bytes).decode("utf-8")

        data = {
            "message": f"Add log {payload.get('id', '')}".strip(),
            "content": b64,
        }

        try:
            r = requests.put(url, headers=self.headers, json=data, timeout=15)
            if r.status_code in (200, 201):
                return True
            print(f"[GitHubWriter] PUT failed {r.status_code}: {r.text[:200]}")
            return False
        except Exception as e:
            print(f"[GitHubWriter] PUT exception: {e}")
            return False

    def write_event(self, category: str, event: Dict[str, Any], event_id: str) -> bool:
        year_month, date_str, _ = _utc_dates()
        path = f"logs/{year_month}/{date_str}/{category}/{event_id}.json"
        return self._put_file(path, event)


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
        input_text: str,
        output_result: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new analysis log event and (optionally) ship to GitHub.
        Returns {"timestamp": <log_id>, "created_at": <utc>}.

        IMPORTANT:
        - input_text is accepted for compatibility but NOT stored.
        - fingerprints are computed and stored instead.
        """
        ts = _utc_iso()
        event_id = self._new_id("a")

        in_len = len(input_text or "")
        in_fp = _sha256_hex(input_text or "", salt=self._salt)

        # output_result should already be content-free (recommended),
        # but we still enforce a safety scrub for known risky keys.
        safe_result = dict(output_result or {})
        # hard-delete any accidental raw text keys (defense-in-depth)
        for k in ["text", "input_text", "original", "normalized", "repaired_text", "raw_ai_output", "llm_raw_response", "llm_raw_output"]:
            if k in safe_result:
                safe_result.pop(k, None)

        payload = {
            "id": event_id,
            "timestamp": ts,
            "type": "analysis",

            # content-free identifiers
            "input": {
                "fp_sha256": in_fp,
                "length": in_len,
                "fingerprint_salted": bool(self._salt),
            },

            # decision evidence (must be content-free)
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
            "target_log_id": log_id,
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
                "salted": bool(self._salt),
            },
            "counts": {
                "analyses_in_runtime": self._analysis_count,
                "feedback_in_runtime": self._feedback_count,
            },
            "last_analysis_utc": self._last_analysis_ts,
        }


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