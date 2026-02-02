"""Pipeline API router."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from src.api.dependencies import get_document_repo, get_orchestrator
from src.core.config import get_settings
from src.core.models import (DocumentStatus, PipelineStage,
                             PipelineStatusResponse)
from src.db.repositories.document_repo import DocumentRepository
from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.state_manager import PipelineStateManager

router = APIRouter(prefix="/api/v1/pipeline", tags=["Pipeline"])


class PipelineRunRequest(BaseModel):
    """Request to run pipeline."""

    document_id: str
    skip_vision: bool = False
    force_restart: bool = False


class PipelineRunResponse(BaseModel):
    """Response when pipeline starts."""

    document_id: str
    status: str
    message: str


@router.post("/run", response_model=PipelineRunResponse)
async def run_pipeline(
    request: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    document_repo: DocumentRepository = Depends(get_document_repo),
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator),
):
    """Start or resume pipeline processing.

    Pipeline runs in background. Use /status/{document_id} to check progress.
    """
    # Check document exists
    document = await document_repo.get(request.document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Check if already processing
    if document.status == DocumentStatus.PROCESSING and not request.force_restart:
        raise HTTPException(
            status_code=400,
            detail="Pipeline already running. Use force_restart=true to restart.",
        )

    # Get PDF path
    pdf_path = Path(document.file_path)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found")

    # Run pipeline in background
    background_tasks.add_task(
        orchestrator.run_pipeline,
        document_id=request.document_id,
        pdf_path=pdf_path,
        skip_vision=request.skip_vision,
        force_restart=request.force_restart,
    )

    return PipelineRunResponse(
        document_id=request.document_id,
        status="started",
        message="Pipeline started. Check /status for progress.",
    )


@router.get("/status/{document_id}")
async def get_pipeline_status(
    document_id: str,
    document_repo: DocumentRepository = Depends(get_document_repo),
):
    """Get current pipeline status with detailed progress."""
    # Check document exists
    document = await document_repo.get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Load pipeline state
    settings = get_settings()
    state_manager = PipelineStateManager(settings)
    state = await state_manager.load_state(document_id)

    if not state:
        return {
            "document_id": document_id,
            "overall_status": (
                document.status.value
                if hasattr(document.status, "value")
                else document.status
            ),
            "current_stage": None,
            "stages": [],
            "progress_percent": 0,
            "error_message": document.error_message,
        }

    # Build stage status list
    stages = []
    for stage in PipelineStage:
        stage_result = state.stages.get(stage.value)
        if stage_result:
            stages.append(
                {
                    "stage": stage.value,
                    "status": (
                        stage_result.status.value
                        if hasattr(stage_result.status, "value")
                        else stage_result.status
                    ),
                    "duration_seconds": stage_result.duration_seconds,
                    "error": stage_result.error_message,
                    "summary": stage_result.output_summary,
                }
            )
        else:
            stages.append(
                {
                    "stage": stage.value,
                    "status": "pending",
                    "duration_seconds": None,
                    "error": None,
                    "summary": None,
                }
            )

    # Calculate progress
    progress = await state_manager.get_progress(document_id)

    return {
        "document_id": document_id,
        "overall_status": (
            document.status.value
            if hasattr(document.status, "value")
            else document.status
        ),
        "current_stage": (
            (
                state.current_stage.value
                if hasattr(state.current_stage, "value")
                else state.current_stage
            )
            if state.current_stage
            else None
        ),
        "last_completed_stage": (
            (
                state.last_completed_stage.value
                if hasattr(state.last_completed_stage, "value")
                else state.last_completed_stage
            )
            if state.last_completed_stage
            else None
        ),
        "stages": stages,
        "progress_percent": progress.get("progress_percent", 0),
        "error_message": document.error_message,
        "started_at": state.started_at.isoformat() if state.started_at else None,
        "completed_at": state.completed_at.isoformat() if state.completed_at else None,
        "total_duration_seconds": state.total_duration_seconds,
    }


@router.get("/stage/{document_id}/{stage}")
async def get_stage_result(
    document_id: str,
    stage: str,
    include_output: bool = Query(False),
    document_repo: DocumentRepository = Depends(get_document_repo),
):
    """Get detailed result of a specific stage."""
    # Check document exists
    exists = await document_repo.exists(document_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Document not found")

    # Parse stage
    try:
        pipeline_stage = PipelineStage(stage)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid stage: {stage}")

    # Load state
    settings = get_settings()
    state_manager = PipelineStateManager(settings)
    state = await state_manager.load_state(document_id)

    if not state:
        raise HTTPException(status_code=404, detail="Pipeline state not found")

    stage_result = state.stages.get(stage)
    if not stage_result:
        return {
            "document_id": document_id,
            "stage": stage,
            "status": "pending",
            "message": "Stage has not run yet",
        }

    response = {
        "document_id": document_id,
        "stage": stage,
        "status": (
            stage_result.status.value
            if hasattr(stage_result.status, "value")
            else stage_result.status
        ),
        "started_at": (
            stage_result.started_at.isoformat() if stage_result.started_at else None
        ),
        "completed_at": (
            stage_result.completed_at.isoformat() if stage_result.completed_at else None
        ),
        "duration_seconds": stage_result.duration_seconds,
        "error_message": stage_result.error_message,
        "output_summary": stage_result.output_summary,
    }

    # Optionally include full output
    if include_output:
        output = await state_manager.load_stage_output(document_id, pipeline_stage)
        response["output"] = output

    return response


@router.post("/cancel/{document_id}")
async def cancel_pipeline(
    document_id: str,
    document_repo: DocumentRepository = Depends(get_document_repo),
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator),
):
    """Cancel running pipeline."""
    # Check document exists
    document = await document_repo.get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.status != DocumentStatus.PROCESSING:
        return {
            "document_id": document_id,
            "cancelled": False,
            "message": "Pipeline is not running",
        }

    success = await orchestrator.cancel_pipeline(document_id)

    return {
        "document_id": document_id,
        "cancelled": success,
        "message": "Pipeline cancelled" if success else "Failed to cancel",
    }


@router.post("/retry/{document_id}")
async def retry_pipeline(
    document_id: str,
    background_tasks: BackgroundTasks,
    document_repo: DocumentRepository = Depends(get_document_repo),
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator),
):
    """Retry pipeline from last failed stage."""
    # Check document exists
    document = await document_repo.get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.status != DocumentStatus.FAILED:
        return {
            "document_id": document_id,
            "started": False,
            "message": "Pipeline has not failed",
        }

    # Get PDF path
    pdf_path = Path(document.file_path)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found")

    # Resume from last completed stage
    background_tasks.add_task(
        orchestrator.run_pipeline,
        document_id=document_id,
        pdf_path=pdf_path,
        skip_vision=False,
        force_restart=False,
    )

    return {
        "document_id": document_id,
        "started": True,
        "message": "Pipeline retry started",
    }
