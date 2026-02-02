"""FastAPI main application."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routers import documents, pipeline, search
from src.core.config import get_settings
from src.core.exceptions import PipelineBaseError
from src.db.mongodb import MongoDB

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    settings = get_settings()
    logger.info("Starting RAG VectorDB PDF Pipeline API")

    # Connect to MongoDB
    await MongoDB.connect(settings)

    # Ensure directories exist
    settings.ensure_directories()

    yield

    # Shutdown
    logger.info("Shutting down API")
    await MongoDB.disconnect()


# Create FastAPI app
app = FastAPI(
    title="RAG VectorDB PDF Pipeline",
    description="RAG Pipeline for PDF Processing with MongoDB Vector Storage",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
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


# Global exception handler
@app.exception_handler(PipelineBaseError)
async def pipeline_error_handler(request: Request, exc: PipelineBaseError):
    """Handle pipeline-specific errors."""
    logger.error(
        "Pipeline error",
        code=exc.code,
        message=exc.message,
        detail=exc.detail,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.message,
            "code": exc.code,
            "detail": exc.detail,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors."""
    logger.exception(
        "Unexpected error",
        error=str(exc),
        path=request.url.path,
    )

    settings = get_settings()
    detail = str(exc) if settings.debug else None

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "code": "INTERNAL_ERROR",
            "detail": detail,
        },
    )


# Include routers
app.include_router(documents.router)
app.include_router(pipeline.router)
app.include_router(search.router)


# Health check
@app.get("/health")
async def health_check():
    """Check API health status."""
    db_healthy = await MongoDB.health_check()

    return {
        "status": "healthy" if db_healthy else "degraded",
        "database": "connected" if db_healthy else "disconnected",
        "version": "1.0.0",
    }


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "RAG VectorDB PDF Pipeline",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


# Run with: uvicorn src.api.main:app --reload
if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )
