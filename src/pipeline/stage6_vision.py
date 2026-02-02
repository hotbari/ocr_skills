"""Stage 6: Vision Processing (Optional)."""

from dataclasses import dataclass
from typing import Any

from src.core.models import Entity, EntityType, PipelineStage
from src.llm.vision_client import VisionClient
from src.pipeline.base import SkippableStage


@dataclass
class Stage6Input:
    """Input for Stage 6."""

    document_id: str
    entities: list[Entity]
    skip_vision: bool = False


@dataclass
class Stage6Output:
    """Output from Stage 6."""

    document_id: str
    enhanced_entities: list[Entity]
    vision_processed_count: int
    vision_skipped_count: int


class Stage6Vision(SkippableStage[Stage6Input, Stage6Output]):
    """Stage 6: Enhance images/diagrams with vision descriptions."""

    stage = PipelineStage.STAGE_6_VISION
    stage_name = "vision"

    def __init__(self, vision_client: VisionClient):
        """Initialize stage.

        Args:
            vision_client: Vision API client
        """
        super().__init__()
        self.vision_client = vision_client

    def validate_input(self, input_data: Stage6Input) -> bool:
        """Validate input."""
        return bool(input_data.document_id)

    def validate_output(self, output_data: Stage6Output) -> bool:
        """Validate output."""
        return True

    def should_skip(self, input_data: Stage6Input) -> bool:
        """Check if stage should be skipped."""
        if input_data.skip_vision:
            return True

        # Skip if no processable entities
        processable = [
            e
            for e in input_data.entities
            if e.entity_type in (EntityType.IMAGE, EntityType.DIAGRAM, EntityType.CHART)
            and not e.vision_processed
        ]
        return len(processable) == 0

    async def execute(self, input_data: Stage6Input) -> Stage6Output:
        """Process images with vision API.

        Args:
            input_data: Stage input

        Returns:
            Enhanced entities
        """
        self.logger.info(
            "Processing with vision",
            document_id=input_data.document_id,
            total_entities=len(input_data.entities),
        )

        enhanced_entities = []
        processed_count = 0
        skipped_count = 0

        for entity in input_data.entities:
            # Skip non-visual entities
            if entity.entity_type not in (
                EntityType.IMAGE,
                EntityType.DIAGRAM,
                EntityType.CHART,
            ):
                enhanced_entities.append(entity)
                continue

            # Skip already processed
            if entity.vision_processed:
                enhanced_entities.append(entity)
                skipped_count += 1
                continue

            # Check if we have image data
            if not entity.image_path and not entity.image_base64:
                enhanced_entities.append(entity)
                skipped_count += 1
                continue

            try:
                # Process with vision
                from pathlib import Path

                description = await self.vision_client.describe_image(
                    image_path=Path(entity.image_path) if entity.image_path else None,
                    image_base64=entity.image_base64,
                    context=entity.surrounding_context or "",
                )

                # Update entity
                entity.vision_description = description.description
                entity.vision_processed = True

                # If diagram, try to extract IR
                if entity.entity_type == EntityType.DIAGRAM:
                    try:
                        ir = await self.vision_client.extract_diagram_ir(
                            image_path=(
                                Path(entity.image_path) if entity.image_path else None
                            ),
                            image_base64=entity.image_base64,
                            context=entity.surrounding_context or "",
                        )
                        entity.ir_yaml = self.vision_client.diagram_ir_to_yaml(ir)
                    except Exception as e:
                        self.logger.warning(
                            "Failed to extract diagram IR",
                            entity_id=entity.id,
                            error=str(e),
                        )

                enhanced_entities.append(entity)
                processed_count += 1

                self.logger.debug(
                    "Vision processed",
                    entity_id=entity.id,
                    type=entity.entity_type.value,
                )

            except Exception as e:
                self.logger.warning(
                    "Vision processing failed",
                    entity_id=entity.id,
                    error=str(e),
                )
                enhanced_entities.append(entity)
                skipped_count += 1

        return Stage6Output(
            document_id=input_data.document_id,
            enhanced_entities=enhanced_entities,
            vision_processed_count=processed_count,
            vision_skipped_count=skipped_count,
        )

    def get_output_summary(self, output: Stage6Output) -> dict[str, Any]:
        """Get output summary."""
        return {
            "total_entities": len(output.enhanced_entities),
            "vision_processed": output.vision_processed_count,
            "vision_skipped": output.vision_skipped_count,
        }
