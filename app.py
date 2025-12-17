"""
Z1 Tone Firewall API
FastAPI 包裝，支援單句分析和批次分析
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
import logging
import os
from pathlib import Path

from pipeline.z1_pipeline import Z1Pipeline

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 初始化 FastAPI
app = FastAPI(
    title="Z1 Tone Firewall API",
    description="AI-powered tone detection and repair system",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 設定（允許 Chrome 擴充套件呼叫）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生產環境應該限制特定 domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化 Z1 Pipeline
try:
    pipeline = Z1Pipeline(
        config_path='configs/settings.yaml',
        debug=False
    )
    logger.info("✅ Z1 Pipeline initialized")
except Exception as e:
    logger.error(f"❌ Failed to initialize Z1 Pipeline: {e}")
    pipeline = None


# ============================================================
# Pydantic Models（API 輸入輸出格式）
# ============================================================

class AnalyzeRequest(BaseModel):
    """單句分析請求"""
    text: str = Field(..., description="要分析的文字", min_length=1, max_length=5000)
    repair_mode: Optional[str] = Field(
        "standard",
        description="修復模式：light, standard, formal, empathy"
    )
    lang: Optional[str] = Field("zh", description="語言：zh 或 en")


class BatchAnalyzeRequest(BaseModel):
    """批次分析請求"""
    texts: List[str] = Field(..., description="要分析的文字列表", max_items=50)
    repair_mode: Optional[str] = Field("standard", description="修復模式")
    lang: Optional[str] = Field("zh", description="語言")


class AnalyzeResponse(BaseModel):
    """分析結果"""
    original: str
    language: str
    freq_type: str
    confidence: float
    scenario: str
    scenario_confidence: float
    mode: str
    repaired_text: Optional[str] = None
    repair_mode: str
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """健康檢查"""
    status: str
    version: str
    pipeline_ready: bool


class StatsResponse(BaseModel):
    """系統統計"""
    api_calls: dict
    rate_limiter: dict
    cache: dict


# ============================================================
# API Endpoints
# ============================================================

@app.get("/", response_model=dict)
async def root():
    """根路徑"""
    return {
        "message": "Z1 Tone Firewall API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """健康檢查"""
    return {
        "status": "healthy" if pipeline else "unhealthy",
        "version": "1.0.0",
        "pipeline_ready": pipeline is not None
    }


@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze_text(request: AnalyzeRequest):
    """
    單句語氣分析
    
    關卡說明：
    1. 接收 POST request
    2. 驗證輸入格式
    3. 呼叫 Z1 Pipeline
    4. 回傳分析結果
    """
    
    if not pipeline:
        raise HTTPException(
            status_code=503,
            detail="Z1 Pipeline not initialized"
        )
    
    try:
        # 關卡 1：接收請求
        logger.info(f"[關卡 1] 收到分析請求：{len(request.text)} 字元")
        
        # 關卡 2：執行 Pipeline
        logger.info("[關卡 2] 執行 Z1 Pipeline")
        result = pipeline.process(request.text)
        
        # 關卡 3：檢查錯誤
        if result.get("error"):
            logger.warning(f"[關卡 3] Pipeline 錯誤：{result.get('reason')}")
            raise HTTPException(
                status_code=400,
                detail=f"Pipeline error: {result.get('reason')}"
            )
        
        # 關卡 4：格式化輸出
        logger.info("[關卡 4] 格式化輸出")
        response = AnalyzeResponse(
            original=result["original"],
            language=result.get("language", "unknown"),
            freq_type=result["freq_type"],
            confidence=result["confidence"]["final"],
            scenario=result["output"]["scenario"],
            scenario_confidence=result["output"]["scenario_confidence"],
            mode=result["mode"],
            repaired_text=result["output"].get("repaired_text"),
            repair_mode=result["output"].get("repair_mode", "standard")
        )
        
        logger.info(f"✅ 分析完成：{response.freq_type} (信心值 {response.confidence:.2f})")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 分析失敗：{e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )


@app.post("/api/v1/batch", response_model=List[AnalyzeResponse])
async def batch_analyze(request: BatchAnalyzeRequest):
    """
    批次語氣分析（最多 50 筆）
    """
    
    if not pipeline:
        raise HTTPException(
            status_code=503,
            detail="Z1 Pipeline not initialized"
        )
    
    if len(request.texts) > 50:
        raise HTTPException(
            status_code=400,
            detail="Maximum 50 texts per batch"
        )
    
    try:
        logger.info(f"[Batch] 收到 {len(request.texts)} 筆請求")
        
        results = []
        for i, text in enumerate(request.texts, 1):
            logger.info(f"[Batch {i}/{len(request.texts)}] 處理中")
            
            result = pipeline.process(text)
            
            if result.get("error"):
                # 錯誤案例也回傳
                results.append(AnalyzeResponse(
                    original=text,
                    language="unknown",
                    freq_type="Unknown",
                    confidence=0.0,
                    scenario="unknown",
                    scenario_confidence=0.0,
                    mode="error",
                    error=result.get("reason")
                ))
            else:
                results.append(AnalyzeResponse(
                    original=result["original"],
                    language=result.get("language", "unknown"),
                    freq_type=result["freq_type"],
                    confidence=result["confidence"]["final"],
                    scenario=result["output"]["scenario"],
                    scenario_confidence=result["output"]["scenario_confidence"],
                    mode=result["mode"],
                    repaired_text=result["output"].get("repaired_text"),
                    repair_mode=result["output"].get("repair_mode", "standard")
                ))
        
        logger.info(f"✅ Batch 完成：{len(results)} 筆")
        return results
        
    except Exception as e:
        logger.error(f"❌ Batch 分析失敗：{e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )


@app.get("/api/v1/stats", response_model=dict)
async def get_stats():
    """
    取得系統統計資訊
    """
    
    if not pipeline:
        raise HTTPException(
            status_code=503,
            detail="Z1 Pipeline not initialized"
        )
    
    try:
        from core.repairer import get_system_stats
        stats = get_system_stats()
        return stats
    except Exception as e:
        logger.error(f"❌ 取得統計失敗：{e}")
        return {"error": str(e)}


# ============================================================
# 啟動設定
# ============================================================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("PORT", 7860))
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
