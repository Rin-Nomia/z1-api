"""
logger.py
Continuum Logger (HF Space friendly)

Provides:
- DataLogger: log_analysis / log_feedback / get_stats
- GitHubBackup: optional restore hook (safe no-op by default)

Design goals:
- Never break the API if logging fails
- Avoid GitHub SHA race conditions by writing ONE FILE PER EVENT
- Works in Hugging Face Spaces using Secrets:
    GITHUB_TOKEN = GitHub Fine-grained PAT (Contents: Read & Write)
    GITHUB_REPO  = "owner/repo" (e.g., "Rin-Nomia/continuum-logs")
"""

from __future__ import annotations

import json
import os
import time
import uuid
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


class GitHubWriter:
    """
    Minimal GitHub Contents API writer.
    Writes one file per event to avoid SHA conflicts.
    """

    def __init__(self):
        self.github_token = os.environ.get("GITHUB_TOKEN")
        self.github_repo = os.environ.get("GITHUB_REPO")  # owner/repo

        self.enabled = bool(self.github_token and self.github_repo)

        # Use a stable UA to reduce GitHub API quirks
        self.headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "continuum-api-logger",
        }
        if self.github_token:
            # GitHub accepts both "token" and "Bearer"; token is classic, Bearer is fine-grained friendly too.
            self.headers["Authorization"] = f"Bearer {self.github_token}"

    def _put_file(self, path: str, payload: Dict[str, Any]) -> bool:
        """
        Create/overwrite a single file via PUT.
        Returns True on success.
        """
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
            # 201 created, 200 updated
            if r.status_code in (200, 201):
                return True
            # Useful debug line (won't crash API)
            print(f"[GitHubWriter] PUT failed {r.status_code}: {r.text[:200]}")
            return False
        except Exception as e:
            print(f"[GitHubWriter] PUT exception: {e}")
            return False

    def write_event(self, category: str, event: Dict[str, Any], event_id: str) -> bool:
        """
        Write event as a unique file:
          logs/<YYYY-MM>/<YYYYMMDD>/<category>/<event_id>.json
        """
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

        # in-memory counters (safe minimal stats; persists only within runtime)
        self._analysis_count = 0
        self._feedback_count = 0
        self._last_analysis_ts: Optional[str] = None

        if self.writer.enabled:
            print(f"[DataLogger] GitHub logging enabled -> {os.environ.get('GITHUB_REPO')}")
        else:
            print("[DataLogger] GitHub credentials not set; logging will be local-only (in-memory stats).")

    @staticmethod
    def _new_id(prefix: str) -> str:
        # short, URL-safe
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    def log_analysis(self, input_text: str, output_result: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Create a new analysis log event and (optionally) ship to GitHub.
        Returns a dict containing 'timestamp' which app.py uses as log_id.
        """
        ts = datetime.utcnow().isoformat() + "Z"
        event_id = self._new_id("a")

        payload = {
            "id": event_id,
            "timestamp": ts,
            "type": "analysis",
            "input": {
                "text": input_text,
                "text_length": len(input_text),
            },
            "result": output_result,
            "metadata": metadata or {},
            "runtime": {
                "source": "hf_space",
            },
        }

        # Update minimal stats
        self._analysis_count += 1
        self._last_analysis_ts = ts

        # Write to GitHub if enabled (failure must not break API)
        if self.writer.enabled:
            ok = self.writer.write_event(category="analysis", event=payload, event_id=event_id)
            if not ok:
                # still return a log_id; API continues
                payload["github_write"] = "failed"

        # app.py expects log.get("timestamp") as log_id
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
                "accuracy": accuracy,
                "helpful": helpful,
                "accepted": accepted,
            },
        }

        self._feedback_count += 1

        if self.writer.enabled:
            ok = self.writer.write_event(category="feedback", event=payload, event_id=event_id)
            if not ok:
                payload["github_write"] = "failed"

        return {"status": "ok", "feedback_id": event_id, "created_at": ts}

    def get_stats(self) -> Dict[str, Any]:
        """
        Minimal stats that never break.
        If you later want 'real stats from GitHub logs', we can add a separate scheduled job.
        """
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

    If later you want "restore last logs to local", we can implement,
    but HF Spaces typically don't rely on local disk logs.
    """

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir

    def restore(self) -> None:
        # Safe no-op: do not break startup
        print("[GitHubBackup] restore() skipped (no-op)")
        return
