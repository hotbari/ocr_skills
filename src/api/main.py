"""FastAPI 메인 애플리케이션."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.routers import documents, pipeline
from src.api.routers import ocr_results
from src.core.config import get_settings
from src.core.exceptions import OCRPipelineError
from src.db.mongodb import MongoDB

_STATIC_DIR = Path(__file__).parent / "static"

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("OCR Pipeline API 시작")
    await MongoDB.connect(settings)
    settings.ensure_directories()
    yield
    logger.info("OCR Pipeline API 종료")
    await MongoDB.disconnect()


app = FastAPI(
    title="OCR Pipeline API",
    description="PP-Structure 기반 OCR 문서 처리 파이프라인",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(OCRPipelineError)
async def pipeline_error_handler(request: Request, exc: OCRPipelineError):
    logger.error("파이프라인 오류", code=exc.code, message=exc.message, path=request.url.path)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "code": exc.code, "detail": exc.detail},
    )


@app.exception_handler(Exception)
async def general_error_handler(request: Request, exc: Exception):
    logger.exception("예상치 못한 오류", error=str(exc), path=request.url.path)
    settings = get_settings()
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "code": "INTERNAL_ERROR",
            "detail": str(exc) if settings.debug else None,
        },
    )


app.include_router(documents.router)
app.include_router(pipeline.router)
app.include_router(ocr_results.router)

# 정적 파일 (데모 페이지)
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/health")
async def health_check():
    db_ok = await MongoDB.health_check()
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "version": "2.0.0",
    }


@app.get("/demo", include_in_schema=False)
async def demo_page():
    """OCR 결과 데모 뷰어."""
    return FileResponse(str(_STATIC_DIR / "demo.html"))


@app.get("/")
async def root():
    return {
        "name": "OCR Pipeline API v2",
        "description": "PP-Structure 기반 OCR 파이프라인 (벡터 없음, OCR 산출물 중심)",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health",
        "pipeline": {
            "stage0": "PDF 추출 (PyMuPDF)",
            "stage1": "레이아웃 분석 (PP-Structure)",
            "stage2": "구조화 (섹션/테이블/이미지)",
            "stage3": "이미지 캡셔닝 (gpt-4o Vision)",
            "stage4": "태그/요약 (gpt-4o-mini, 선택적)",
        },
    }


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )
