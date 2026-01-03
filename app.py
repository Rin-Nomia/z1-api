"""
Continuum API - HF-safe version
RIN Protocol — Tone Rhythm Repair Module
Auto-sync from z1_mvp + manual GitHub data backup
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import logging
import os
from datetime import datetime

# 🔥 環境變數檢查
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
if not ANTHROPIC_API_KEY:
    print("⚠️  WARNING: ANTHROPIC_API_KEY not set")
    print("   API will start but LLM features will be disabled")

# Auto-copied by GitHub Actions
from pipeline.z1_pipeline import Z1Pipeline
from logger import DataLogger, GitHubBackup

# ------------------------
# App & Logging
# ------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Continuum API",
    version="1.0.0",
    description="RIN Protocol — Tone Rhythm Repair Module. AI-powered tone detection and repair for complete sentences"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------
# Initialization
# ------------------------

try:
    pipeline = Z1Pipeline(config_path="configs/settings.yaml", debug=False)
    data_logger = DataLogger()
    gh_backup = GitHubBackup()
    logger.info("✅ Pipeline, Logger, Backup initialized")
except Exception as e:
    logger.error(f"❌ Init failed: {e}")
    pipeline = None
    data_logger = None
    gh_backup = None

# ------------------------
# Data Models
# ------------------------

class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)

class AnalyzeResponse(BaseModel):
    original: str
    freq_type: str
    confidence: float
    scenario: str
    repaired_text: Optional[str] = None
    repair_note: Optional[str] = None
    log_id: Optional[str] = None

class FeedbackRequest(BaseModel):
    log_id: str
    accuracy: int = Field(..., ge=1, le=5)
    helpful: int = Field(..., ge=1, le=5)
    accepted: bool

# ------------------------
# Language Detection
# ------------------------

def detect_language(text: str) -> str:
    clean_text = "".join(
        c for c in text if c.isalpha() or "\u4e00" <= c <= "\u9fff"
    )

    if not clean_text:
        return "zh"

    chinese_chars = sum(
        1 for c in clean_text if "\u4e00" <= c <= "\u9fff"
    )

    return "zh" if chinese_chars / len(clean_text) > 0.3 else "en"

# ------------------------
# Contextual Response
# ------------------------

def generate_contextual_response(
    text: str, freq_type: str, confidence: float
) -> tuple[str, str]:

    text_len = len(text.strip())
    lang = detect_language(text)

    messages = {
        "short": {
            "zh": f"此訊息較短（{text_len} 字）。Continuum 專注於完整句子（建議 15 字以上）的語氣分析。",
            "en": f"This message is short ({text_len} characters). Continuum works best on complete sentences (15+).",
        },
        "medium_low_conf": {
            "zh": f"語氣判斷信心度 {int(confidence*100)}%。建議使用更完整的表達。",
            "en": f"Tone confidence {int(confidence*100)}%. Consider expanding your expression.",
        },
        "unknown": {
            "zh": "語氣特徵不明確，建議更具體的完整句子。",
            "en": "Tone unclear. More complete expressions recommended.",
        },
        "low_conf": {
            "zh": f"信心度 {int(confidence*100)}%，建議人工確認。",
            "en": f"Confidence {int(confidence*100)}%. Manual review recommended.",
        },
    }

    if text_len < 10:
        return text, messages["short"][lang]
    if text_len < 20 and confidence < 0.4:
        return text, messages["medium_low_conf"][lang]
    if freq_type == "Unknown":
        return text, messages["unknown"][lang]
    if confidence < 0.3:
        return text, messages["low_conf"][lang]

    return text, None

# ------------------------
# Startup (HF-safe)
# ------------------------

@app.on_event("startup")
async def startup_event():
    if gh_backup:
        try:
            gh_backup.restore()
            logger.info("✅ Logs restored")
        except Exception:
            logger.info("ℹ️ No previous logs found")

# ------------------------
# API Endpoints
# ------------------------

@app.get("/")
async def root():
    return {
        "message": "Continuum API — RIN Protocol",
        "product": "Continuum",
        "version": "1.0.0",
        "languages": ["zh", "en"],
        "docs": "/docs",
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy" if pipeline else "unhealthy",
        "pipeline": pipeline is not None,
        "logger": data_logger is not None,
        "backup": gh_backup is not None,
    }

@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):

    if not pipeline:
        raise HTTPException(503, "Pipeline not ready")

    result = pipeline.process(request.text)

    if result.get("error"):
        raise HTTPException(400, result.get("reason"))

    freq_type = result["freq_type"]
    confidence = result["confidence"]["final"]
    repaired_text = result["output"].get("repaired_text")
    repair_note = None

    if freq_type == "Unknown" or confidence < 0.3:
        repaired_text, repair_note = generate_contextual_response(
            request.text, freq_type, confidence
        )

    log_id = None
    if data_logger:
        log = data_logger.log(
            input_text=request.text,
            output_result=result,
            metadata={
                "confidence": confidence,
                "freq_type": freq_type,
                "text_length": len(request.text),
            },
        )
        log_id = log.get("timestamp")

    return AnalyzeResponse(
        original=result["original"],
        freq_type=freq_type,
        confidence=confidence,
        scenario=result["output"]["scenario"],
        repaired_text=repaired_text,
        repair_note=repair_note,
        log_id=log_id,
    )

@app.post("/api/v1/feedback")
async def submit_feedback(feedback: FeedbackRequest):
    if not data_logger:
        raise HTTPException(503, "Logger not ready")

    data_logger.log_feedback(
        log_id=feedback.log_id,
        accuracy=feedback.accuracy,
        helpful=feedback.helpful,
        accepted=feedback.accepted,
    )
    return {"status": "ok"}

@app.post("/api/v1/backup")
async def manual_backup():
    if not gh_backup:
        raise HTTPException(503, "Backup not ready")

    gh_backup.backup()
    return {"status": "ok"}

# ------------------------
# Local run
# ------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 7860)),
    )
