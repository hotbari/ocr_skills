"""Pipeline state manager for persistence and resume."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import structlog

from src.core.config import Settings, get_settings
from src.core.exceptions import PipelineStateError
from src.core.models import (PipelineStage, PipelineState, StageResult,
                             StageStatus)

logger = structlog.get_logger()


class PipelineStateManager:
    """Manages pipeline state persistence for resume capability."""

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize state manager.

        Args:
            settings: Application settings
        """
        self.settings = settings or get_settings()
        self.state_dir = self.settings.pipeline_state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger.bind(component="PipelineStateManager")

    def _get_state_path(self, document_id: str) -> Path:
        """Get path to state file for a document."""
        doc_dir = self.state_dir / document_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        return doc_dir / "pipeline_state.json"

    def _get_stage_output_path(self, document_id: str, stage: PipelineStage) -> Path:
        """Get path to stage output file."""
        doc_dir = self.state_dir / document_id
        return doc_dir / f"{stage.value}_output.json"

    async def create_state(
        self,
        document_id: str,
        config_snapshot: Optional[dict[str, Any]] = None,
    ) -> PipelineState:
        """Create new pipeline state.

        Args:
            document_id: Document ID
            config_snapshot: Configuration to save

        Returns:
            New PipelineState
        """
        state = PipelineState(
            document_id=document_id,
            config_snapshot=config_snapshot or {},
        )

        await self.save_state(state)

        self.logger.info("Pipeline state created", document_id=document_id)
        return state

    async def load_state(self, document_id: str) -> Optional[PipelineState]:
        """Load pipeline state from disk.

        Args:
            document_id: Document ID

        Returns:
            PipelineState or None if not found
        """
        state_path = self._get_state_path(document_id)

        if not state_path.exists():
            return None

        try:
            with open(state_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Reconstruct StageResult objects
            if "stages" in data:
                for stage_key, stage_data in data["stages"].items():
                    data["stages"][stage_key] = StageResult.model_validate(stage_data)

            return PipelineState.model_validate(data)

        except Exception as e:
            self.logger.error(
                "Failed to load state",
                document_id=document_id,
                error=str(e),
            )
            return None

    async def save_state(self, state: PipelineState) -> None:
        """Save pipeline state to disk.

        Args:
            state: State to save
        """
        state_path = self._get_state_path(state.document_id)
        state.updated_at = datetime.utcnow()

        try:
            # Convert to dict with proper serialization
            data = state.model_dump(mode="json")

            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)

        except Exception as e:
            self.logger.error(
                "Failed to save state",
                document_id=state.document_id,
                error=str(e),
            )
            raise PipelineStateError(f"Failed to save pipeline state: {e}")

    async def update_stage(
        self,
        document_id: str,
        stage: PipelineStage,
        result: StageResult,
        output_path: Optional[str] = None,
    ) -> PipelineState:
        """Update state with stage result.

        Args:
            document_id: Document ID
            stage: Completed stage
            result: Stage result
            output_path: Path to stage output file

        Returns:
            Updated PipelineState
        """
        state = await self.load_state(document_id)

        if not state:
            raise PipelineStateError(f"State not found for document: {document_id}")

        state.stages[stage.value] = result
        state.current_stage = stage

        if result.status == StageStatus.COMPLETED:
            state.last_completed_stage = stage

        if output_path:
            state.stage_outputs[stage.value] = output_path

        await self.save_state(state)

        return state

    async def mark_running(
        self,
        document_id: str,
        stage: PipelineStage,
    ) -> PipelineState:
        """Mark stage as running.

        Args:
            document_id: Document ID
            stage: Stage starting

        Returns:
            Updated state
        """
        state = await self.load_state(document_id)

        if not state:
            raise PipelineStateError(f"State not found for document: {document_id}")

        state.current_stage = stage
        state.stages[stage.value] = StageResult(
            stage=stage,
            status=StageStatus.RUNNING,
            started_at=datetime.utcnow(),
        )

        await self.save_state(state)

        self.logger.info(
            "Stage marked running",
            document_id=document_id,
            stage=stage.value,
        )

        return state

    async def mark_completed(
        self,
        document_id: str,
        stage: Optional[PipelineStage] = None,
    ) -> PipelineState:
        """Mark pipeline or stage as completed.

        Args:
            document_id: Document ID
            stage: Specific stage, or None for entire pipeline

        Returns:
            Updated state
        """
        state = await self.load_state(document_id)

        if not state:
            raise PipelineStateError(f"State not found for document: {document_id}")

        if stage is None:
            # Mark entire pipeline complete
            state.completed_at = datetime.utcnow()
            state.total_duration_seconds = (
                state.completed_at - state.started_at
            ).total_seconds()
        else:
            state.last_completed_stage = stage

        await self.save_state(state)

        return state

    async def mark_error(
        self,
        document_id: str,
        stage: PipelineStage,
        error: str,
    ) -> PipelineState:
        """Mark stage as failed with error.

        Args:
            document_id: Document ID
            stage: Failed stage
            error: Error message

        Returns:
            Updated state
        """
        state = await self.load_state(document_id)

        if not state:
            raise PipelineStateError(f"State not found for document: {document_id}")

        if stage.value in state.stages:
            state.stages[stage.value].status = StageStatus.FAILED
            state.stages[stage.value].error_message = error
            state.stages[stage.value].completed_at = datetime.utcnow()

        await self.save_state(state)

        self.logger.error(
            "Stage marked failed",
            document_id=document_id,
            stage=stage.value,
            error=error,
        )

        return state

    async def get_resume_point(self, document_id: str) -> Optional[PipelineStage]:
        """Get stage to resume from after failure.

        Args:
            document_id: Document ID

        Returns:
            Stage to resume from, or None if should start fresh
        """
        state = await self.load_state(document_id)

        if not state:
            return None

        if state.completed_at:
            return None  # Already completed

        if state.last_completed_stage:
            # Get next stage after last completed
            stage_order = list(PipelineStage)
            last_idx = stage_order.index(state.last_completed_stage)

            if last_idx + 1 < len(stage_order):
                return stage_order[last_idx + 1]

        return PipelineStage.STAGE_0_EXTRACTION  # Start from beginning

    async def save_stage_output(
        self,
        document_id: str,
        stage: PipelineStage,
        output: Any,
    ) -> str:
        """Save stage output to file.

        Args:
            document_id: Document ID
            stage: Stage
            output: Output data to save

        Returns:
            Path to saved file
        """
        output_path = self._get_stage_output_path(document_id, stage)

        try:
            # Handle Pydantic models
            if hasattr(output, "model_dump"):
                data = output.model_dump(mode="json")
            elif isinstance(output, dict):
                data = output
            elif isinstance(output, list):
                data = [
                    (
                        item.model_dump(mode="json")
                        if hasattr(item, "model_dump")
                        else item
                    )
                    for item in output
                ]
            else:
                data = output

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str, ensure_ascii=False)

            return str(output_path)

        except Exception as e:
            self.logger.error(
                "Failed to save stage output",
                document_id=document_id,
                stage=stage.value,
                error=str(e),
            )
            raise PipelineStateError(f"Failed to save stage output: {e}")

    async def load_stage_output(
        self,
        document_id: str,
        stage: PipelineStage,
    ) -> Optional[Any]:
        """Load stage output from file.

        Args:
            document_id: Document ID
            stage: Stage

        Returns:
            Loaded output data or None
        """
        output_path = self._get_stage_output_path(document_id, stage)

        if not output_path.exists():
            return None

        try:
            with open(output_path, "r", encoding="utf-8") as f:
                return json.load(f)

        except Exception as e:
            self.logger.error(
                "Failed to load stage output",
                document_id=document_id,
                stage=stage.value,
                error=str(e),
            )
            return None

    async def delete_state(self, document_id: str) -> bool:
        """Delete all state for a document.

        Args:
            document_id: Document ID

        Returns:
            True if deleted
        """
        import shutil

        doc_dir = self.state_dir / document_id

        if doc_dir.exists():
            shutil.rmtree(doc_dir)
            self.logger.info("Pipeline state deleted", document_id=document_id)
            return True

        return False

    async def get_progress(self, document_id: str) -> dict[str, Any]:
        """Get pipeline progress summary.

        Args:
            document_id: Document ID

        Returns:
            Progress summary
        """
        state = await self.load_state(document_id)

        if not state:
            return {"status": "not_found", "progress_percent": 0}

        total_stages = len(PipelineStage)
        completed_stages = sum(
            1 for s in state.stages.values() if s.status == StageStatus.COMPLETED
        )
        skipped_stages = sum(
            1 for s in state.stages.values() if s.status == StageStatus.SKIPPED
        )

        progress_percent = ((completed_stages + skipped_stages) / total_stages) * 100

        return {
            "document_id": document_id,
            "status": "completed" if state.completed_at else "in_progress",
            "current_stage": (
                (
                    state.current_stage.value
                    if hasattr(state.current_stage, "value")
                    else state.current_stage
                )
                if state.current_stage
                else None
            ),
            "last_completed": (
                (
                    state.last_completed_stage.value
                    if hasattr(state.last_completed_stage, "value")
                    else state.last_completed_stage
                )
                if state.last_completed_stage
                else None
            ),
            "progress_percent": progress_percent,
            "stages_completed": completed_stages,
            "stages_skipped": skipped_stages,
            "total_stages": total_stages,
        }
