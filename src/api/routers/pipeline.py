"""파이프라인 실행 및 상태 조회 API."""

import asyncio

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from src.core.config import Settings, get_settings
from src.core.exceptions import DocumentNotFoundError
from src.core.models import DocumentStatus, PipelineStatusResponse, StageResult, StageStatus
from src.db.repositories.document_repo import DocumentRepository
from src.pipeline.orchestrator import PipelineOrchestrator

logger = structlog.get_logger()
router = APIRouter(prefix="/pipeline", tags=["pipeline"])

# 실행 중인 파이프라인 상태 (document_id → PipelineState)
_active_states: dict = {}
_active_lock = asyncio.Lock()


def get_doc_repo() -> DocumentRepository:
    return DocumentRepository()


@router.post("/{document_id}/run", status_code=status.HTTP_202_ACCEPTED)
async def run_pipeline(
    document_id: str,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    doc_repo: DocumentRepository = Depends(get_doc_repo),
):
    """파이프라인 비동기 실행 (백그라운드)."""
    document = await doc_repo.get(document_id)
    if not document:
        raise DocumentNotFoundError(document_id)

    if document.status == DocumentStatus.PROCESSING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 처리 중인 문서입니다.",
        )

    async def _run():
        async with _active_lock:
            orchestrator = PipelineOrchestrator(settings)
            state = await orchestrator.run(document)
            _active_states[document_id] = state

    background_tasks.add_task(_run)

    return {
        "document_id": document_id,
        "message": "파이프라인 시작됨",
        "status_url": f"/pipeline/{document_id}/status",
    }


@router.get("/{document_id}/status", response_model=PipelineStatusResponse)
async def get_pipeline_status(
    document_id: str,
    doc_repo: DocumentRepository = Depends(get_doc_repo),
):
    """파이프라인 진행 상태 조회."""
    document = await doc_repo.get(document_id)
    if not document:
        raise DocumentNotFoundError(document_id)

    # 메모리 상태 또는 DB 상태에서 조회
    state = _active_states.get(document_id)

    if state:
        stage_results = list(state.stages.values())
        completed = sum(1 for r in stage_results if r.status == StageStatus.COMPLETED)
        progress = round(completed / max(len(stage_results), 1) * 100, 1)
    else:
        stage_results = []
        progress = 100.0 if document.status == DocumentStatus.COMPLETED else 0.0

    return PipelineStatusResponse(
        document_id=document_id,
        overall_status=document.status,
        current_stage=document.current_stage,
        stages=stage_results,
        progress_percent=progress,
        error_message=document.error_message,
    )
