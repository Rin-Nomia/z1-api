# logger.py
"""
logger.py
Continuum Logger (HF Space friendly)

Provides:
- DataLogger: log_analysis / log_feedback / get_stats
- GitHubBackup: optional restore hook (safe no-op by default)

GOVERNANCE PURITY POLICY (Upgraded):
- ✅ Store ONLY hash + length for any text.
- ✅ Do NOT store original text / repaired text / raw LLM output.
- ✅ Add verifiable output fingerprints to validate decision correctness WITHOUT content.
    - input_fingerprint: sha256 + length (raw request input)
    - normalized_fingerprint: sha256 + length (post-normalize & truncate, pipeline truth)
    - output_fingerprint: sha256 + length (governed output / repaired_text)
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


def _sha256_text(s: str) -> str:
    s = s if isinstance(s, str) else str(s or "")
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _fingerprint_text(s: Any) -> Dict[str, Any]:
    s2 = s if isinstance(s, str) else str(s or "")
    return {"sha256": _sha256_text(s2), "length": len(s2)}


def _strip_content_fields(obj: Any) -> Any:
    """
    Defense-in-depth: remove any obvious content-bearing fields if they leak into result.
    We keep audit/metrics truth and fingerprints, but never raw text.
    """
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            lk = str(k).lower()

            # drop raw content fields (common names)
            if lk in {
                "text", "original", "normalized", "repaired_text", "repair_note",
                "raw_ai_output", "llm_raw_output", "llm_raw_response", "prompt",
                "messages", "content"
            }:
                continue

            cleaned[k] = _strip_content_fields(v)
        return cleaned

    if isinstance(obj, list):
        return [_strip_content_fields(x) for x in obj]

    return obj


def _output_kind(freq_type: str, mode: str, scenario: str = "") -> str:
    """
    One-word governance classification for quick scanning.
    """
    ft = (freq_type or "").strip()
    md = (mode or "").strip().lower()
    sc = (scenario or "").strip().lower()

    if ft == "OutOfScope" or md == "block" or "crisis" in sc or "out_of_scope" in sc:
        return "block"
    if md == "no-op":
        return "pass"
    if md == "repair":
        return "rewrite"
    if md == "suggest":
        return "guide"
    return "unknown"


def _extract_governance_truth_with_fingerprints(pipeline_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Keep only the minimum set to prove the decision was correct.
    Upgraded: include normalized/output fingerprints (hash+len).
    """
    if not isinstance(pipeline_result, dict):
        return {"error": True, "reason": "invalid_pipeline_result"}

    out = pipeline_result.get("output") if isinstance(pipeline_result.get("output"), dict) else {}
    conf = pipeline_result.get("confidence") if isinstance(pipeline_result.get("confidence"), dict) else {}
    audit = pipeline_result.get("audit") if isinstance(pipeline_result.get("audit"), dict) else {}
    metrics = pipeline_result.get("metrics") if isinstance(pipeline_result.get("metrics"), dict) else None

    # ---- Fingerprints (NO CONTENT STORED) ----
    normalized_text = pipeline_result.get("normalized", "")
    governed_text = out.get("repaired_text", pipeline_result.get("repaired_text", ""))

    # Ensure block doesn't accidentally fingerprint input (pipeline should already set to "")
    mode = pipeline_result.get("mode", "no-op")
    freq_type = pipeline_result.get("freq_type", "Unknown")
    scenario = out.get("scenario", pipeline_result.get("scenario", "unknown"))

    # If block, governed_text should be "", but keep guardrail:
    if (str(mode).lower() == "block") or (freq_type == "OutOfScope"):
        governed_text = "" if governed_text is None else str(governed_text or "")

    truth = {
        "freq_type": freq_type,
        "mode": mode,
        "scenario": scenario,

        "output_kind": _output_kind(freq_type, mode, scenario),

        "confidence": {
            "final": conf.get("final", pipeline_result.get("confidence_final", 0.0)),
            "classifier": conf.get("classifier", pipeline_result.get("confidence_classifier", None)),
            "base": conf.get("base", None),
        },

        # ✅ fingerprints that let you validate correctness without content
        "fingerprints": {
            "normalized": _fingerprint_text(normalized_text),
            "output": _fingerprint_text(governed_text),
        },

        # top-level compat truth (source of truth from pipeline)
        "llm_used": pipeline_result.get("llm_used", out.get("llm_used", None)),
        "cache_hit": pipeline_result.get("cache_hit", out.get("cache_hit", None)),
        "model": pipeline_result.get("model", out.get("model", "")),
        "usage": pipeline_result.get("usage", out.get("usage", {})),
        "output_source": pipeline_result.get("output_source", out.get("output_source", None)),

        "processing_time_ms": pipeline_result.get("processing_time_ms", None),

        # audit + metrics are allowed (but cleaned)
        "audit": audit,
        "metrics": metrics,
    }

    # Clean any accidental content fields (defense-in-depth)
    truth = _strip_content_fields(truth)
    return truth


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

        data = {"message": f"Add log {payload.get('id', '')}".strip(), "content": b64}

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

    Methods:
    - log_analysis(input_text, output_result, metadata) -> dict
    - log_feedback(log_id, accuracy, helpful, accepted) -> dict
    - get_stats() -> dict
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
            print("[DataLogger] GitHub credentials not set; logging will be local-only (in-memory stats).")

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    def log_analysis(self, input_text: str, output_result: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Governance log event (Upgraded):
        - input: sha256 + length only
        - result: decision truth + normalized/output fingerprints (hash+len), no content
        """
        ts = datetime.utcnow().isoformat() + "Z"
        event_id = self._new_id("a")

        payload = {
            "id": event_id,
            "timestamp": ts,
            "type": "analysis",

            # ✅ governance purity: no text
            "input": _fingerprint_text(input_text),

            # ✅ decision truth + fingerprints only
            "result": _extract_governance_truth_with_fingerprints(output_result),

            "metadata": _strip_content_fields(metadata or {}),
            "runtime": {"source": "hf_space"},
        }

        self._analysis_count += 1
        self._last_analysis_ts = ts

        if self.writer.enabled:
            ok = self.writer.write_event(category="analysis", event=payload, event_id=event_id)
            if not ok:
                payload["github_write"] = "failed"

        return {"timestamp": event_id, "created_at": ts}

    def log_feedback(self, log_id: str, accuracy: int, helpful: int, accepted: bool) -> Dict[str, Any]:
        ts = datetime.utcnow().isoformat() + "Z"
        event_id = self._new_id("f")

        payload = {
            "id": event_id,
            "timestamp": ts,
            "type": "feedback",
            "target_log_id": log_id,
            "feedback": {
                "accuracy": int(accuracy),
                "helpful": int(helpful),
                "accepted": bool(accepted),
            },
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