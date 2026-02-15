# app.py
"""
Continuum API - Hugging Face Spaces Compatible App
--------------------------------------------------
HF-safe FastAPI lifespan + pipeline truth pass-through.

SEALING PATCH (V1.0 Evidence Contract + Enterprise Audit):
- ✅ Evidence Schema v1.0 contract (app.py is the schema packager)
- ✅ Strict scrub: NO content-derived signals (matched_keywords/detected_keywords/oos_matched/trigger_words/etc.)
- ✅ logger.py remains pure receiver + scrub (defense-in-depth)
- ✅ /api/v1/stats + /api/v1/feedback endpoints for governance loop
- ✅ Never passes raw input text into logger
- ✅ Keep pipeline timing_ms.total untouched; only add server_overhead
"""

import os
import time
import math
import asyncio
import logging
import hashlib
from collections import deque
from typing import Optional, Dict, Any, Tuple, List, Literal, Deque
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import uvicorn

PIPELINE_IMPORT_ERROR: Optional[str] = None
try:
    from pipeline.z1_pipeline import Z1Pipeline
except Exception as e:
    # Keep API process alive and surface precise operability error via health/status.
    Z1Pipeline = None  # type: ignore[assignment,misc]
    PIPELINE_IMPORT_ERROR = f"{type(e).__name__}: {e}"
from logger import DataLogger, GitHubBackup

LICENSE_IMPORT_ERROR: Optional[str] = None
try:
    from core.license_manager import LicenseManager
except Exception as e:
    LicenseManager = None  # type: ignore[assignment,misc]
    LICENSE_IMPORT_ERROR = f"{type(e).__name__}: {e}"

# -------------------- Logging --------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("continuum-api")

# -------------------- Versioning --------------------
APP_VERSION = os.environ.get("APP_VERSION", "2.2.4-hf").strip() or "2.2.4-hf"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PIPELINE_MIN_INPUT_LENGTH = int(os.environ.get("PIPELINE_MIN_INPUT_LENGTH", "5"))
PIPELINE_MAX_INPUT_LENGTH = int(os.environ.get("PIPELINE_MAX_INPUT_LENGTH", "500"))

# -------------------- Globals --------------------
pipeline: Optional[Z1Pipeline] = None
data_logger: Optional[DataLogger] = None
github_backup: Optional[GitHubBackup] = None
license_manager: Optional["LicenseManager"] = None
license_check_task: Optional[asyncio.Task] = None
last_decision_state: Optional[str] = None
last_decision_time: Optional[str] = None

ALLOWED_DECISION_STATES = {"ALLOW", "GUIDE", "BLOCK"}
PRIVACY_GUARD_OK = True
LATENCY_WINDOW_SIZE = int(os.environ.get("LATENCY_WINDOW_SIZE", "2000"))
LICENSE_ENFORCEMENT_MODE = os.environ.get("LICENSE_ENFORCEMENT_MODE", "degrade").strip().lower() or "degrade"
LICENSE_CHECK_INTERVAL_SECONDS = int(os.environ.get("LICENSE_CHECK_INTERVAL_SECONDS", "3600"))

runtime_decision_counts: Dict[str, int] = {"ALLOW": 0, "GUIDE": 0, "BLOCK": 0}
runtime_total_analyses: int = 0
runtime_llm_used_true: int = 0
runtime_oos_hits: int = 0
runtime_latency_ms: Deque[int] = deque(maxlen=LATENCY_WINDOW_SIZE)
license_status: Dict[str, Any] = {
    "valid": False,
    "reason": "license_not_checked",
    "license_id": "",
    "expiry_date": None,
    "quota_limit": None,
    "usage_count": 0,
    "quota_remaining": None,
    "checked_at_utc": None,
}
service_halted_by_license: bool = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_conf(v, default: float = 0.0) -> float:
    try:
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return default
        return max(0.0, min(1.0, x))
    except Exception:
        return default


def _none_if_empty(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    if isinstance(s, str) and s.strip() == "":
        return None
    return s


def _sha256_hex(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()


def _bool_or_none(v) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    return None


def _safe_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return int(default)


def _safe_str(v, default: str = "") -> str:
    try:
        if v is None:
            return default
        return str(v)
    except Exception:
        return default


def _decision_from_mode(mode: str) -> str:
    m = _safe_str(mode, "").strip().lower()
    if m == "no-op":
        return "ALLOW"
    if m == "block":
        return "BLOCK"
    return "GUIDE"


def _decision_state_from_truth(*, mode: str, freq_type: str, scenario: str) -> str:
    if _safe_str(freq_type, "") == "OutOfScope":
        return "BLOCK"
    sc = _safe_str(scenario, "").strip().lower()
    if "out_of_scope" in sc or "crisis" in sc:
        return "BLOCK"

    return _decision_from_mode(mode)


def _percentile(values: List[int], p: float) -> Optional[float]:
    if not values:
        return None
    if p <= 0:
        return float(min(values))
    if p >= 100:
        return float(max(values))
    sv = sorted(values)
    k = (len(sv) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sv[int(k)])
    d0 = sv[f] * (c - k)
    d1 = sv[c] * (k - f)
    return float(d0 + d1)


def _current_usage_for_license() -> int:
    if data_logger and hasattr(data_logger, "get_usage_snapshot"):
        try:
            snap = data_logger.get_usage_snapshot()
            return int((snap or {}).get("analysis_in_month", 0))
        except Exception:
            return 0
    return 0


def _refresh_license_status() -> Dict[str, Any]:
    global license_status
    if not license_manager:
        license_status = {
            "valid": False,
            "reason": "license_manager_not_ready",
            "license_id": "",
            "expiry_date": None,
            "quota_limit": None,
            "usage_count": _current_usage_for_license(),
            "quota_remaining": None,
            "checked_at_utc": _utc_now(),
        }
        return license_status

    usage = _current_usage_for_license()
    try:
        result = license_manager.validate(usage_count=usage)
        license_status = result.to_dict() if hasattr(result, "to_dict") else dict(result)  # type: ignore[arg-type]
    except Exception as e:
        license_status = {
            "valid": False,
            "reason": f"license_validation_exception:{e}",
            "license_id": "",
            "expiry_date": None,
            "quota_limit": None,
            "usage_count": usage,
            "quota_remaining": None,
            "checked_at_utc": _utc_now(),
        }
    return license_status


async def _license_watchdog_loop() -> None:
    global service_halted_by_license
    while True:
        st = _refresh_license_status()
        if not st.get("valid", False):
            reason = st.get("reason", "unknown")
            if LICENSE_ENFORCEMENT_MODE == "stop":
                service_halted_by_license = True
                logger.critical(f"License invalid in stop mode, service halted: {reason}")
            else:
                logger.warning(f"License invalid in degrade mode: {reason}")
        await asyncio.sleep(max(60, LICENSE_CHECK_INTERVAL_SECONDS))


# -------------------- Content-derived scrub (hard privacy line) --------------------
# Anything that can leak or reconstruct text fragments must be scrubbed.
# NOTE: We normalize keys to lower-case and compare against LOWERED set.
CONTENT_DERIVED_KEYS_LOWER = {
    # generic
    "matched", "matches", "match", "keywords", "keyword", "tokens", "token",
    "spans", "span", "entities", "entity", "phrases", "phrase",
    # known fields
    "matched_keywords", "detected_keywords", "oos_matched", "trigger_words",
    "trigger_word", "trigger", "triggers",
    # common LLM / prompt artifacts
    "prompt", "messages", "completion", "response_text", "raw", "raw_text",
    # raw text keys (double safety)
    "text", "input_text", "original", "normalized", "repaired_text",
    "raw_ai_output", "llm_raw_response", "llm_raw_output",
}

def scrub_no_content_derived(obj: Any) -> Any:
    """
    Recursive scrub that removes:
    - raw text fields
    - content-derived signals (keywords/matched lists/etc.)
    This enforces the external claim: "We never store content" (incl. derived fragments).
    """
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            k_str = str(k)
            k_low = k_str.strip().lower()
            if k_low in CONTENT_DERIVED_KEYS_LOWER:
                continue
            out[k_str] = scrub_no_content_derived(v)
        return out
    if isinstance(obj, list):
        return [scrub_no_content_derived(x) for x in obj]
    return obj


# -------------------- Evidence Schema v1.0 (contract) --------------------
# This is the contract stored in logs. Keep stable.
EVIDENCE_SCHEMA_V1 = {
    "version": "1.0",
    "required_top_keys": [
        "schema_version",
        "input_fp_sha256",
        "input_length",
        "output_fp_sha256",
        "output_length",
        "freq_type",
        "mode",
        "scenario",
        "confidence",
        "metrics",
        "audit",
        "llm_used",
        "cache_hit",
        "model",
        "usage",
        "output_source",
        "api_version",
        "pipeline_version_fingerprint",
    ],
    "required_confidence_keys": ["final", "classifier"],
}

def validate_evidence_v1(e: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(e, dict):
        return False, ["evidence_not_dict"]

    for k in EVIDENCE_SCHEMA_V1["required_top_keys"]:
        if k not in e:
            errors.append(f"missing:{k}")

    conf = e.get("confidence")
    if not isinstance(conf, dict):
        errors.append("confidence_not_dict")
    else:
        for ck in EVIDENCE_SCHEMA_V1["required_confidence_keys"]:
            if ck not in conf:
                errors.append(f"missing:confidence.{ck}")

    # type sanity (soft)
    if "input_length" in e and not isinstance(e.get("input_length"), int):
        errors.append("type:input_length_not_int")
    if "output_length" in e and not isinstance(e.get("output_length"), int):
        errors.append("type:output_length_not_int")
    if "llm_used" in e and e.get("llm_used") is not None and not isinstance(e.get("llm_used"), bool):
        errors.append("type:llm_used_not_bool_or_none")
    if "cache_hit" in e and e.get("cache_hit") is not None and not isinstance(e.get("cache_hit"), bool):
        errors.append("type:cache_hit_not_bool_or_none")
    if "usage" in e and not isinstance(e.get("usage"), dict):
        errors.append("type:usage_not_dict")
    if "audit" in e and not isinstance(e.get("audit"), dict):
        errors.append("type:audit_not_dict")
    if "metrics" in e and not isinstance(e.get("metrics"), dict):
        errors.append("type:metrics_not_dict")

    return (len(errors) == 0), errors


def build_evidence_v1(
    *,
    req_text: str,
    repaired_text: Optional[str],
    freq_type: str,
    mode: str,
    scenario: str,
    confidence_final: float,
    confidence_classifier: float,
    metrics: Optional[Dict[str, Any]],
    audit_top: Dict[str, Any],
    llm_used: Optional[bool],
    cache_hit: Optional[bool],
    model_name: str,
    usage: Dict[str, Any],
    output_source: Optional[str],
    pipeline_version_fingerprint: str,
) -> Dict[str, Any]:
    # fingerprints
    inp_fp = _sha256_hex(req_text)
    out_text = repaired_text if isinstance(repaired_text, str) else ("" if repaired_text is None else str(repaired_text))
    out_fp = _sha256_hex(out_text)

    # scrub audit/metrics from any content-derived fragments BEFORE logging
    audit_safe = scrub_no_content_derived(audit_top if isinstance(audit_top, dict) else {})
    metrics_safe = scrub_no_content_derived(metrics if isinstance(metrics, dict) else {})

    evidence: Dict[str, Any] = {
        "schema_version": "1.0",

        # fingerprints (content-free)
        "input_fp_sha256": inp_fp,
        "input_length": len(req_text or ""),
        "output_fp_sha256": out_fp,
        "output_length": len(out_text or ""),

        # decision truth
        "freq_type": _safe_str(freq_type, "Unknown"),
        "mode": _safe_str(mode, "no-op"),
        "scenario": _safe_str(scenario, "unknown"),
        "confidence": {
            "final": float(_safe_conf(confidence_final, 0.0)),
            "classifier": float(_safe_conf(confidence_classifier, 0.0)),
        },

        # governance truth (scrubbed)
        "metrics": metrics_safe if isinstance(metrics_safe, dict) else {},
        "audit": audit_safe if isinstance(audit_safe, dict) else {},

        # compat truth
        "llm_used": llm_used,
        "cache_hit": cache_hit,
        "model": _safe_str(model_name, ""),
        "usage": usage if isinstance(usage, dict) else {},

        "output_source": output_source,

        # versioning
        "api_version": APP_VERSION,
        "pipeline_version_fingerprint": _safe_str(pipeline_version_fingerprint, ""),
    }

    ok, errs = validate_evidence_v1(evidence)
    if not ok:
        # Do not break runtime; attach schema errors (content-free)
        evidence["schema_valid"] = False
        evidence["schema_errors"] = errs
    else:
        evidence["schema_valid"] = True

    return evidence


# -------------------- Lifespan (HF-safe) --------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline, data_logger, github_backup, license_manager, license_check_task, service_halted_by_license

    logger.info("🚀 Starting Continuum API (HF Space)")
    if PIPELINE_IMPORT_ERROR:
        logger.error(f"Pipeline import failed: {PIPELINE_IMPORT_ERROR}")
        pipeline = None
    else:
        pipeline = Z1Pipeline(debug=False)
    data_logger = DataLogger(log_dir="logs")

    # License manager bootstrap
    if LICENSE_IMPORT_ERROR:
        logger.error(f"License manager import failed: {LICENSE_IMPORT_ERROR}")
        license_manager = None
    elif LicenseManager is None:
        license_manager = None
    else:
        license_manager = LicenseManager.from_env()

    st = _refresh_license_status()
    if not st.get("valid", False):
        reason = st.get("reason", "license_invalid")
        if LICENSE_ENFORCEMENT_MODE == "stop":
            logger.critical(f"Startup blocked by license (stop mode): {reason}")
            raise RuntimeError(f"license_startup_blocked:{reason}")
        logger.warning(f"Startup in degraded mode due to invalid license: {reason}")

    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO")
    if token and repo:
        try:
            github_backup = GitHubBackup(log_dir="logs")
            github_backup.restore()
            logger.info("📦 GitHub backup restored")
        except Exception as e:
            logger.warning(f"GitHub backup skipped: {e}")
            github_backup = None
    else:
        github_backup = None

    # Hourly (configurable) license guard loop
    license_check_task = asyncio.create_task(_license_watchdog_loop())

    logger.info("✅ Startup complete")
    yield

    # finalize signed monthly usage summary on shutdown
    try:
        if data_logger and hasattr(data_logger, "emit_signed_monthly_summary"):
            data_logger.emit_signed_monthly_summary()
    except Exception as e:
        logger.warning(f"Usage summary finalization skipped: {e}")

    if license_check_task:
        license_check_task.cancel()
        try:
            await license_check_task
        except asyncio.CancelledError:
            pass

    logger.info("🧹 Shutdown complete")


# -------------------- FastAPI App --------------------
app = FastAPI(
    title="Continuum API",
    description="AI conversation risk governance (output-side)",
    version=APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------- Models --------------------
class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=PIPELINE_MIN_INPUT_LENGTH, max_length=PIPELINE_MAX_INPUT_LENGTH)


class AnalyzeResponse(BaseModel):
    decision_state: Literal["ALLOW", "GUIDE", "BLOCK"]
    freq_type: str
    confidence_final: float
    confidence_classifier: Optional[float] = None
    scenario: str
    repaired_text: Optional[str] = None
    repair_note: Optional[str] = None
    privacy_guard_ok: bool = True

    llm_used: Optional[bool] = None
    cache_hit: Optional[bool] = None
    model: str = ""
    usage: Dict[str, Any] = {}
    output_source: Optional[str] = None

    audit: Dict[str, Any]
    metrics: Optional[Dict[str, Any]] = None


class FeedbackRequest(BaseModel):
    log_id: str = Field(..., min_length=1, max_length=100)
    accuracy: int = Field(0, ge=0, le=5)
    helpful: int = Field(0, ge=0, le=5)
    accepted: bool = False


class UsageSummaryResponse(BaseModel):
    month: str
    summary_path: str
    sig_path: str
    signature: str
    counts: Dict[str, int]


# -------------------- Endpoints --------------------
@app.get("/")
async def root():
    return {
        "name": "Continuum API",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "status_dashboard": "/status",
        "version": APP_VERSION,
    }


@app.get("/health")
async def health():
    return {
        "pipeline_ready": pipeline is not None,
        "pipeline_import_error": PIPELINE_IMPORT_ERROR,
        "license_import_error": LICENSE_IMPORT_ERROR,
        "license_enforcement_mode": LICENSE_ENFORCEMENT_MODE,
        "license_valid": bool(license_status.get("valid", False)),
        "license_reason": license_status.get("reason"),
        "service_halted_by_license": service_halted_by_license,
        "logger_ready": data_logger is not None,
        "github_backup_enabled": github_backup is not None,
        "time": _utc_now(),
        "version": APP_VERSION,
    }


@app.get("/status", include_in_schema=False)
async def status_dashboard():
    return FileResponse(os.path.join(BASE_DIR, "status.html"))


@app.get("/api/v1/status")
async def runtime_status():
    return {
        "started": (pipeline is not None) and (data_logger is not None),
        "pipeline_import_error": PIPELINE_IMPORT_ERROR,
        "license_import_error": LICENSE_IMPORT_ERROR,
        "license_enforcement_mode": LICENSE_ENFORCEMENT_MODE,
        "license_status": dict(license_status),
        "service_halted_by_license": service_halted_by_license,
        "last_decision_state": last_decision_state,
        "last_decision_time": last_decision_time,
        "privacy_guard_ok": PRIVACY_GUARD_OK,
        "time": _utc_now(),
        "version": APP_VERSION,
    }


@app.get("/api/v1/ops/metrics")
async def ops_metrics():
    total = runtime_total_analyses
    dist = {
        k: {
            "count": int(v),
            "rate": (float(v) / float(total)) if total > 0 else 0.0,
        }
        for k, v in runtime_decision_counts.items()
    }
    lat_samples = list(runtime_latency_ms)
    p95 = _percentile(lat_samples, 95.0)
    p50 = _percentile(lat_samples, 50.0)
    p99 = _percentile(lat_samples, 99.0)

    return {
        "ok": True,
        "time": _utc_now(),
        "version": APP_VERSION,
        "license_status": dict(license_status),
        "service_halted_by_license": service_halted_by_license,
        "window_size": len(lat_samples),
        "totals": {
            "analyses": total,
            "llm_used_true": runtime_llm_used_true,
            "oos_hits": runtime_oos_hits,
        },
        "decision_state_distribution": dist,
        "rates": {
            "llm_usage_rate": (float(runtime_llm_used_true) / float(total)) if total > 0 else 0.0,
            "oos_hit_rate": (float(runtime_oos_hits) / float(total)) if total > 0 else 0.0,
        },
        "latency_ms": {
            "p50": p50,
            "p95": p95,
            "p99": p99,
            "max": float(max(lat_samples)) if lat_samples else None,
        },
    }


@app.get("/api/v1/stats")
async def stats():
    """
    Governance ops endpoint (content-free).
    Shows runtime counters + whether GitHub logging is enabled.
    """
    if not data_logger:
        return {"ok": False, "reason": "logger_not_ready", "time": _utc_now(), "version": APP_VERSION}

    payload = {
        "ok": True,
        "time": _utc_now(),
        "version": APP_VERSION,
        "license_status": dict(license_status),
        "service_halted_by_license": service_halted_by_license,
        "logger": data_logger.get_stats(),
    }

    # include pipeline fingerprint if available (content-free)
    try:
        if pipeline and hasattr(pipeline, "pipeline_version_fingerprint"):
            payload["pipeline_version_fingerprint"] = getattr(pipeline, "pipeline_version_fingerprint", "")
    except Exception:
        pass

    return payload


@app.post("/api/v1/feedback")
async def feedback(req: FeedbackRequest):
    """
    Governance feedback loop (content-free).
    """
    if not data_logger:
        raise HTTPException(503, "Logger not ready")

    try:
        res = data_logger.log_feedback(
            log_id=req.log_id,
            accuracy=req.accuracy,
            helpful=req.helpful,
            accepted=req.accepted,
        )
        return {"ok": True, "result": res, "time": _utc_now()}
    except Exception as e:
        # never break the API contract; but feedback is a governance tool, so surface error.
        raise HTTPException(500, f"feedback_failed:{e}")


@app.post("/api/v1/billing/usage-summary", response_model=UsageSummaryResponse)
async def export_usage_summary(month: Optional[str] = None):
    if not data_logger:
        raise HTTPException(503, "Logger not ready")
    if not hasattr(data_logger, "emit_signed_monthly_summary"):
        raise HTTPException(500, "signed_usage_not_supported")
    try:
        res = data_logger.emit_signed_monthly_summary(month=month)
        return UsageSummaryResponse(**res)
    except Exception as e:
        raise HTTPException(500, f"usage_summary_failed:{e}")


@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    global last_decision_state, last_decision_time
    global runtime_total_analyses, runtime_llm_used_true, runtime_oos_hits

    st = _refresh_license_status()
    if service_halted_by_license:
        raise HTTPException(503, f"service_halted_by_license:{st.get('reason', 'unknown')}")
    if not st.get("valid", False):
        # Payment/license semantics: invalid license leads to safe degradation
        raise HTTPException(402, f"license_invalid:{st.get('reason', 'unknown')}")

    if not pipeline:
        detail = "Pipeline not ready"
        if PIPELINE_IMPORT_ERROR:
            detail = f"pipeline_import_failed:{PIPELINE_IMPORT_ERROR}"
        raise HTTPException(503, detail)

    t0 = time.time()
    result = pipeline.process(req.text)

    if result.get("error"):
        raise HTTPException(400, result.get("reason", "pipeline_error"))

    # -------------------- Core truth --------------------
    freq_type = result.get("freq_type", "Unknown")
    mode = (result.get("mode") or "no-op").lower()

    # Confidence (truth)
    conf_obj = result.get("confidence") or {}
    confidence_final = _safe_conf(conf_obj.get("final", result.get("confidence_final", 0.0)))
    confidence_classifier = _safe_conf(conf_obj.get("classifier", result.get("confidence_classifier", 0.0)))

    # Output (truth)
    out = result.get("output") or {}
    scenario = out.get("scenario", result.get("scenario", "unknown"))

    repaired_text = out.get("repaired_text", result.get("repaired_text"))
    repair_note = out.get("repair_note", result.get("repair_note"))

    # Ensure BLOCK stays explicit (""), not None
    if repaired_text is None and mode == "block":
        repaired_text = ""

    # Top-level compat truth (do not guess; only type-normalize)
    llm_used = _bool_or_none(result.get("llm_used", None))
    cache_hit = _bool_or_none(result.get("cache_hit", None))
    model_name = result.get("model", "") or ""
    usage = result.get("usage", {}) if isinstance(result.get("usage", {}), dict) else {}
    output_source = result.get("output_source", None)

    # Audit: pass-through pipeline truth, add server_overhead WITHOUT overwriting total
    audit_top = result.get("audit") if isinstance(result.get("audit"), dict) else {}
    audit = dict(audit_top)

    if not isinstance(audit.get("timing_ms"), dict):
        audit["timing_ms"] = {}

    server_overhead = int((time.time() - t0) * 1000)
    audit["timing_ms"]["server_overhead"] = server_overhead
    audit["server_time_utc"] = _utc_now()

    # Metrics: pipeline truth
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    metrics = dict(metrics)
    decision_state = _decision_state_from_truth(
        mode=mode,
        freq_type=freq_type,
        scenario=scenario,
    )
    upstream_state = _safe_str(metrics.get("decision_state"), "").strip().upper()
    if upstream_state in ALLOWED_DECISION_STATES and upstream_state != decision_state:
        logger.warning(
            f"decision_state corrected by app truth: upstream={upstream_state}, normalized={decision_state}"
        )
    metrics["decision_state"] = decision_state
    if "action" not in metrics:
        metrics["action"] = "intercept" if decision_state == "BLOCK" else ("pass" if decision_state == "ALLOW" else "constrain")

    # Fingerprint (truth)
    pipeline_fp = (
        result.get("pipeline_version_fingerprint")
        or result.get("pipeline_fingerprint")
        or ""
    )

    # -------------------- Enterprise-safe log (Schema V1.0, NO CONTENT) --------------------
    if data_logger:
        try:
            evidence = build_evidence_v1(
                req_text=req.text,
                repaired_text=repaired_text,
                freq_type=freq_type,
                mode=mode,
                scenario=scenario,
                confidence_final=confidence_final,
                confidence_classifier=confidence_classifier,
                metrics=metrics,
                audit_top=audit_top,
                llm_used=llm_used,
                cache_hit=cache_hit,
                model_name=model_name,
                usage=usage,
                output_source=output_source,
                pipeline_version_fingerprint=pipeline_fp,
            )

            meta = {"runtime": {"platform": "hf_space"}}

            # IMPORTANT: do NOT pass raw input into logger
            log_res = data_logger.log_analysis(
                input_text=None,
                output_result=evidence,
                metadata=meta
            )

            # attach log_id into audit for feedback/tracing
            if isinstance(log_res, dict) and log_res.get("timestamp"):
                audit["log_id"] = log_res["timestamp"]

        except Exception as e:
            logger.warning(f"Logging skipped: {e}")

    last_decision_state = decision_state
    last_decision_time = _utc_now()
    runtime_total_analyses += 1
    runtime_decision_counts[decision_state] = int(runtime_decision_counts.get(decision_state, 0)) + 1
    if bool(llm_used):
        runtime_llm_used_true += 1
    if freq_type == "OutOfScope" or ("out_of_scope" in _safe_str(scenario, "").lower()) or ("crisis" in _safe_str(scenario, "").lower()):
        runtime_oos_hits += 1
    runtime_latency_ms.append(max(0, server_overhead))

    return AnalyzeResponse(
        decision_state=decision_state,
        freq_type=freq_type,
        confidence_final=confidence_final,
        confidence_classifier=confidence_classifier,
        scenario=scenario,
        repaired_text=repaired_text,
        repair_note=repair_note,
        privacy_guard_ok=PRIVACY_GUARD_OK,

        llm_used=llm_used,
        cache_hit=cache_hit,
        model=model_name,
        usage=usage,
        output_source=output_source,

        audit=audit,
        metrics=metrics,
    )


# -------------------- HF entrypoint --------------------
if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=7860,
        log_level="info",
    )