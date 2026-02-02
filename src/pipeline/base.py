"""Base interface for pipeline stages."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Generic, TypeVar

import structlog

from src.core.models import PipelineStage, StageResult, StageStatus

logger = structlog.get_logger()

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class BaseStage(ABC, Generic[InputT, OutputT]):
    """Abstract base class for all pipeline stages."""

    stage: PipelineStage
    stage_name: str

    def __init__(self):
        self.logger = logger.bind(
            component=f"Stage_{self.stage_name}",
            stage=self.stage.value,
        )

    @abstractmethod
    async def execute(self, input_data: InputT) -> OutputT:
        """Execute the stage processing.

        Args:
            input_data: Input data for this stage

        Returns:
            Processed output data
        """
        pass

    @abstractmethod
    def validate_input(self, input_data: InputT) -> bool:
        """Validate input data before execution.

        Args:
            input_data: Input data to validate

        Returns:
            True if valid, False otherwise
        """
        pass

    @abstractmethod
    def validate_output(self, output_data: OutputT) -> bool:
        """Validate output data after execution.

        Args:
            output_data: Output data to validate

        Returns:
            True if valid, False otherwise
        """
        pass

    def get_output_summary(self, output_data: OutputT) -> dict[str, Any]:
        """Generate summary of output for logging.

        Args:
            output_data: Output data to summarize

        Returns:
            Dictionary with summary information
        """
        return {"status": "completed"}

    async def run(self, input_data: InputT) -> tuple[OutputT, StageResult]:
        """Full execution with timing, validation, and error handling.

        Args:
            input_data: Input data for this stage

        Returns:
            Tuple of (output_data, stage_result)

        Raises:
            ValueError: If input validation fails
            Exception: If execution fails
        """
        result = StageResult(
            stage=self.stage,
            status=StageStatus.RUNNING,
            started_at=datetime.utcnow(),
        )

        self.logger.info("Stage starting")

        try:
            # Validate input
            if not self.validate_input(input_data):
                raise ValueError(f"Invalid input for stage {self.stage_name}")

            # Execute
            output = await self.execute(input_data)

            # Validate output
            if not self.validate_output(output):
                raise ValueError(f"Invalid output from stage {self.stage_name}")

            # Success
            result.status = StageStatus.COMPLETED
            result.completed_at = datetime.utcnow()
            result.duration_seconds = (
                result.completed_at - result.started_at
            ).total_seconds()
            result.output_summary = self.get_output_summary(output)

            self.logger.info(
                "Stage completed",
                duration=result.duration_seconds,
                summary=result.output_summary,
            )

            return output, result

        except Exception as e:
            result.status = StageStatus.FAILED
            result.completed_at = datetime.utcnow()
            result.duration_seconds = (
                result.completed_at - result.started_at
            ).total_seconds()
            result.error_message = str(e)

            self.logger.error(
                "Stage failed",
                duration=result.duration_seconds,
                error=str(e),
            )

            raise


class SkippableStage(BaseStage[InputT, OutputT]):
    """Base class for stages that can be skipped."""

    def should_skip(self, input_data: InputT) -> bool:
        """Determine if this stage should be skipped.

        Args:
            input_data: Input data

        Returns:
            True if stage should be skipped
        """
        return False

    async def run(self, input_data: InputT) -> tuple[OutputT | None, StageResult]:
        """Run with skip check.

        Args:
            input_data: Input data

        Returns:
            Tuple of (output or None if skipped, stage_result)
        """
        if self.should_skip(input_data):
            result = StageResult(
                stage=self.stage,
                status=StageStatus.SKIPPED,
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                duration_seconds=0,
                output_summary={"reason": "skipped"},
            )
            self.logger.info("Stage skipped")
            return None, result

        return await super().run(input_data)
