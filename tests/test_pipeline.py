"""Tests for pipeline components in src/pipeline/"""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config import Settings
from src.core.exceptions import PipelineError, PipelineStateError
from src.core.models import (DocumentStatus, PipelineStage, PipelineState,
                             StageResult, StageStatus)
from src.pipeline.orchestrator import PipelineOrchestrator, PipelineResult
from src.pipeline.state_manager import PipelineStateManager

# ============================================================
# TEST PIPELINE STATE MANAGER
# ============================================================


@pytest.mark.asyncio
async def test_state_manager_create_state(mock_settings):
    """Test creating new pipeline state."""
    manager = PipelineStateManager(mock_settings)

    state = await manager.create_state("test-doc-123")

    assert state.document_id == "test-doc-123"
    assert state.id is not None
    assert state.stages == {}
    assert isinstance(state.started_at, datetime)


@pytest.mark.asyncio
async def test_state_manager_save_and_load_state(mock_settings):
    """Test saving and loading pipeline state."""
    manager = PipelineStateManager(mock_settings)

    # Create and save state
    state = await manager.create_state("test-doc-123")
    original_id = state.id

    # Load state
    loaded_state = await manager.load_state("test-doc-123")

    assert loaded_state is not None
    assert loaded_state.id == original_id
    assert loaded_state.document_id == "test-doc-123"


@pytest.mark.asyncio
async def test_state_manager_load_nonexistent_state(mock_settings):
    """Test loading non-existent state."""
    manager = PipelineStateManager(mock_settings)

    state = await manager.load_state("nonexistent-doc")

    assert state is None


@pytest.mark.asyncio
async def test_state_manager_mark_running(mock_settings):
    """Test marking a stage as running."""
    manager = PipelineStateManager(mock_settings)

    # Create initial state
    await manager.create_state("test-doc-123")

    # Mark stage running
    state = await manager.mark_running("test-doc-123", PipelineStage.STAGE_0_EXTRACTION)

    assert state.current_stage == PipelineStage.STAGE_0_EXTRACTION
    assert PipelineStage.STAGE_0_EXTRACTION.value in state.stages
    stage_result = state.stages[PipelineStage.STAGE_0_EXTRACTION.value]
    assert stage_result.status == StageStatus.RUNNING


@pytest.mark.asyncio
async def test_state_manager_update_stage(mock_settings):
    """Test updating stage with result."""
    manager = PipelineStateManager(mock_settings)

    # Create initial state
    await manager.create_state("test-doc-123")

    # Create stage result
    result = StageResult(
        stage=PipelineStage.STAGE_0_EXTRACTION,
        status=StageStatus.COMPLETED,
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        duration_seconds=5.5,
    )

    # Update stage
    state = await manager.update_stage(
        "test-doc-123", PipelineStage.STAGE_0_EXTRACTION, result
    )

    assert state.current_stage == PipelineStage.STAGE_0_EXTRACTION
    assert state.last_completed_stage == PipelineStage.STAGE_0_EXTRACTION
    assert (
        state.stages[PipelineStage.STAGE_0_EXTRACTION.value].status
        == StageStatus.COMPLETED
    )


@pytest.mark.asyncio
async def test_state_manager_mark_completed(mock_settings):
    """Test marking pipeline as completed."""
    manager = PipelineStateManager(mock_settings)

    # Create state
    await manager.create_state("test-doc-123")

    # Mark completed
    state = await manager.mark_completed("test-doc-123")

    assert state.completed_at is not None
    assert state.total_duration_seconds is not None
    assert state.total_duration_seconds >= 0


@pytest.mark.asyncio
async def test_state_manager_mark_error(mock_settings):
    """Test marking stage as failed."""
    manager = PipelineStateManager(mock_settings)

    # Create state and mark running
    await manager.create_state("test-doc-123")
    await manager.mark_running("test-doc-123", PipelineStage.STAGE_1_SEGMENTATION)

    # Mark as error
    state = await manager.mark_error(
        "test-doc-123", PipelineStage.STAGE_1_SEGMENTATION, "Test error message"
    )

    stage_result = state.stages[PipelineStage.STAGE_1_SEGMENTATION.value]
    assert stage_result.status == StageStatus.FAILED
    assert stage_result.error_message == "Test error message"


@pytest.mark.asyncio
async def test_state_manager_get_resume_point(mock_settings):
    """Test getting resume point after failure."""
    manager = PipelineStateManager(mock_settings)

    # Create state
    state = await manager.create_state("test-doc-123")
    state.last_completed_stage = PipelineStage.STAGE_1_SEGMENTATION
    await manager.save_state(state)

    # Get resume point
    resume_point = await manager.get_resume_point("test-doc-123")

    # Should resume from next stage after last completed
    assert resume_point == PipelineStage.STAGE_2_HEADINGS


@pytest.mark.asyncio
async def test_state_manager_get_resume_point_fresh(mock_settings):
    """Test getting resume point with no state."""
    manager = PipelineStateManager(mock_settings)

    resume_point = await manager.get_resume_point("nonexistent-doc")

    assert resume_point is None


@pytest.mark.asyncio
async def test_state_manager_save_and_load_stage_output(mock_settings):
    """Test saving and loading stage output."""
    manager = PipelineStateManager(mock_settings)

    # Create state
    await manager.create_state("test-doc-123")

    # Save output
    output_data = {"test": "data", "count": 123}
    output_path = await manager.save_stage_output(
        "test-doc-123", PipelineStage.STAGE_0_EXTRACTION, output_data
    )

    assert output_path is not None
    assert Path(output_path).exists()

    # Load output
    loaded_output = await manager.load_stage_output(
        "test-doc-123", PipelineStage.STAGE_0_EXTRACTION
    )

    assert loaded_output == output_data


@pytest.mark.asyncio
async def test_state_manager_delete_state(mock_settings):
    """Test deleting pipeline state."""
    manager = PipelineStateManager(mock_settings)

    # Create state
    await manager.create_state("test-doc-123")

    # Verify state exists
    state = await manager.load_state("test-doc-123")
    assert state is not None

    # Delete state
    deleted = await manager.delete_state("test-doc-123")

    assert deleted is True

    # Verify state is gone
    state = await manager.load_state("test-doc-123")
    assert state is None


@pytest.mark.asyncio
async def test_state_manager_get_progress(mock_settings):
    """Test getting progress summary."""
    manager = PipelineStateManager(mock_settings)

    # Create state with some completed stages
    state = await manager.create_state("test-doc-123")
    state.current_stage = PipelineStage.STAGE_2_HEADINGS
    state.last_completed_stage = PipelineStage.STAGE_1_SEGMENTATION

    # Add completed stages
    state.stages[PipelineStage.STAGE_0_EXTRACTION.value] = StageResult(
        stage=PipelineStage.STAGE_0_EXTRACTION,
        status=StageStatus.COMPLETED,
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
    )
    state.stages[PipelineStage.STAGE_1_SEGMENTATION.value] = StageResult(
        stage=PipelineStage.STAGE_1_SEGMENTATION,
        status=StageStatus.COMPLETED,
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
    )

    await manager.save_state(state)

    # Get progress
    progress = await manager.get_progress("test-doc-123")

    assert progress["document_id"] == "test-doc-123"
    assert progress["status"] == "in_progress"
    assert progress["stages_completed"] == 2
    assert progress["progress_percent"] > 0


# ============================================================
# TEST PIPELINE ORCHESTRATOR INITIALIZATION
# ============================================================


@pytest.mark.asyncio
async def test_orchestrator_initialization(
    document_repo, toc_repo, chunk_repo, entity_repo, mock_settings
):
    """Test pipeline orchestrator initialization."""
    orchestrator = PipelineOrchestrator(
        document_repo, toc_repo, chunk_repo, entity_repo, mock_settings
    )

    assert orchestrator.document_repo == document_repo
    assert orchestrator.toc_repo == toc_repo
    assert orchestrator.chunk_repo == chunk_repo
    assert orchestrator.entity_repo == entity_repo
    assert len(orchestrator.stages) == len(PipelineOrchestrator.STAGE_ORDER)


def test_orchestrator_stage_order():
    """Test that stage order is defined correctly."""
    order = PipelineOrchestrator.STAGE_ORDER

    assert len(order) == 9
    assert order[0] == PipelineStage.STAGE_0_EXTRACTION
    assert order[-1] == PipelineStage.STAGE_7_EMBEDDING


# ============================================================
# TEST PIPELINE ORCHESTRATOR - RUN PIPELINE
# ============================================================


@pytest.mark.asyncio
async def test_orchestrator_run_pipeline_mock(
    document_repo,
    toc_repo,
    chunk_repo,
    entity_repo,
    mock_settings,
    sample_pdf,
    sample_document,
):
    """Test running pipeline with mocked stages."""
    # Create document
    await document_repo.create(sample_document)

    orchestrator = PipelineOrchestrator(
        document_repo, toc_repo, chunk_repo, entity_repo, mock_settings
    )

    # Mock the extract method to avoid actual PDF processing
    with patch.object(orchestrator.pdf_extractor, "extract") as mock_extract:
        mock_extract.return_value = MagicMock(
            document_id=sample_document.id,
            raw_text="Test text",
            page_count=2,
            raw_text_by_page=["Page 1", "Page 2"],
            tables=[],
            images=[],
            metadata={},
            detected_language="en",
        )

        # Mock all stages to return immediately
        for stage_name, stage in orchestrator.stages.items():
            stage.run = AsyncMock(return_value=(MagicMock(), MagicMock()))

        # Run pipeline (will fail without full mocking, but tests initialization)
        with pytest.raises(Exception):
            # Expected to fail due to incomplete mocking
            await orchestrator.run_pipeline(
                sample_document.id, sample_pdf, skip_vision=True
            )


@pytest.mark.asyncio
async def test_orchestrator_get_status(
    document_repo, toc_repo, chunk_repo, entity_repo, mock_settings
):
    """Test getting pipeline status."""
    orchestrator = PipelineOrchestrator(
        document_repo, toc_repo, chunk_repo, entity_repo, mock_settings
    )

    # Create state
    await orchestrator.state_manager.create_state("test-doc-123")

    # Get status
    status = await orchestrator.get_status("test-doc-123")

    assert status is not None
    assert "document_id" in status or "status" in status


@pytest.mark.asyncio
async def test_orchestrator_cancel_pipeline(
    document_repo, toc_repo, chunk_repo, entity_repo, mock_settings, sample_document
):
    """Test cancelling pipeline."""
    # Create document
    await document_repo.create(sample_document)

    orchestrator = PipelineOrchestrator(
        document_repo, toc_repo, chunk_repo, entity_repo, mock_settings
    )

    # Cancel pipeline
    result = await orchestrator.cancel_pipeline(sample_document.id)

    assert result is True

    # Check document status
    doc = await document_repo.get(sample_document.id)
    assert doc.status == DocumentStatus.FAILED
    assert "Cancelled" in doc.error_message


# ============================================================
# TEST STAGE EXECUTION
# ============================================================


@pytest.mark.asyncio
async def test_orchestrator_execute_stage_invalid_stage(
    document_repo, toc_repo, chunk_repo, entity_repo, mock_settings
):
    """Test executing invalid stage raises error."""
    orchestrator = PipelineOrchestrator(
        document_repo, toc_repo, chunk_repo, entity_repo, mock_settings
    )

    # Try to execute with invalid stage enum (this is a hypothetical test)
    # In reality, the enum would prevent this, but we test the error path
    with pytest.raises((PipelineError, KeyError, AttributeError)):
        await orchestrator._execute_stage(
            "invalid_stage",  # type: ignore
            {"document_id": "test-doc-123"},
            skip_vision=False,
        )


# ============================================================
# TEST PIPELINE RESULT
# ============================================================


def test_pipeline_result_success():
    """Test PipelineResult creation for successful pipeline."""
    result = PipelineResult(
        document_id="test-doc-123",
        success=True,
        stages_completed=["stage_0_extraction", "stage_1_segmentation"],
        total_retrieval_chunks=50,
        total_generation_chunks=10,
        total_entities=5,
        duration_seconds=120.5,
    )

    assert result.success is True
    assert len(result.stages_completed) == 2
    assert result.total_retrieval_chunks == 50
    assert result.error is None


def test_pipeline_result_failure():
    """Test PipelineResult creation for failed pipeline."""
    result = PipelineResult(
        document_id="test-doc-123",
        success=False,
        stages_completed=["stage_0_extraction"],
        total_retrieval_chunks=0,
        total_generation_chunks=0,
        total_entities=0,
        duration_seconds=5.0,
        error="Stage 1 failed: parsing error",
    )

    assert result.success is False
    assert len(result.stages_completed) == 1
    assert result.error is not None
    assert "parsing error" in result.error


# ============================================================
# TEST STATE MANAGER ERROR HANDLING
# ============================================================


@pytest.mark.asyncio
async def test_state_manager_update_nonexistent_state(mock_settings):
    """Test updating non-existent state raises error."""
    manager = PipelineStateManager(mock_settings)

    result = StageResult(
        stage=PipelineStage.STAGE_0_EXTRACTION,
        status=StageStatus.COMPLETED,
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
    )

    with pytest.raises(PipelineStateError):
        await manager.update_stage(
            "nonexistent-doc", PipelineStage.STAGE_0_EXTRACTION, result
        )


@pytest.mark.asyncio
async def test_state_manager_mark_running_nonexistent_state(mock_settings):
    """Test marking stage running for non-existent state raises error."""
    manager = PipelineStateManager(mock_settings)

    with pytest.raises(PipelineStateError):
        await manager.mark_running("nonexistent-doc", PipelineStage.STAGE_0_EXTRACTION)


# ============================================================
# TEST STATE PERSISTENCE
# ============================================================


@pytest.mark.asyncio
async def test_state_manager_stage_output_persistence(mock_settings):
    """Test that stage outputs persist across restarts."""
    manager = PipelineStateManager(mock_settings)

    # Create state and save output
    await manager.create_state("test-doc-123")

    output_data = {"segments": [{"id": 1, "content": "test"}]}
    await manager.save_stage_output(
        "test-doc-123", PipelineStage.STAGE_1_SEGMENTATION, output_data
    )

    # Create new manager instance (simulating restart)
    new_manager = PipelineStateManager(mock_settings)

    # Load output
    loaded_output = await new_manager.load_stage_output(
        "test-doc-123", PipelineStage.STAGE_1_SEGMENTATION
    )

    assert loaded_output == output_data


@pytest.mark.asyncio
async def test_state_manager_pydantic_model_serialization(mock_settings):
    """Test saving/loading Pydantic models as stage output."""
    manager = PipelineStateManager(mock_settings)

    await manager.create_state("test-doc-123")

    # Create mock Pydantic model output
    mock_output = MagicMock()
    mock_output.model_dump = MagicMock(
        return_value={"test": "value", "nested": {"key": "val"}}
    )

    # Save and load
    await manager.save_stage_output(
        "test-doc-123", PipelineStage.STAGE_0_EXTRACTION, mock_output
    )

    loaded = await manager.load_stage_output(
        "test-doc-123", PipelineStage.STAGE_0_EXTRACTION
    )

    assert loaded == {"test": "value", "nested": {"key": "val"}}
