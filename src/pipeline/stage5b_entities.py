"""Stage 5b: Entity Extraction (Tables, Images)."""

from dataclasses import dataclass
from typing import Any, Optional

from src.core.models import (BoundingBox, Entity, EntityType, PipelineStage,
                             TOCNode, generate_id)
from src.ocr.image_handler import ExtractedImage
from src.ocr.table_handler import ExtractedTable, TableHandler
from src.pipeline.base import BaseStage


@dataclass
class Stage5bInput:
    """Input for Stage 5b."""

    document_id: str
    tables: list[ExtractedTable]
    images: list[ExtractedImage]
    toc_nodes: list[TOCNode]
    page_to_toc_mapping: dict[int, str]  # page_number -> toc_node_id


@dataclass
class Stage5bOutput:
    """Output from Stage 5b."""

    document_id: str
    entities: list[Entity]


class Stage5bEntities(BaseStage[Stage5bInput, Stage5bOutput]):
    """Stage 5b: Extract and create entity objects."""

    stage = PipelineStage.STAGE_5B_ENTITIES
    stage_name = "entities"

    def __init__(self, table_handler: Optional[TableHandler] = None):
        """Initialize stage.

        Args:
            table_handler: Optional table handler for conversions
        """
        super().__init__()
        self.table_handler = table_handler or TableHandler()

    def validate_input(self, input_data: Stage5bInput) -> bool:
        """Validate input."""
        return bool(input_data.document_id)

    def validate_output(self, output_data: Stage5bOutput) -> bool:
        """Validate output."""
        # Empty entities is valid if no tables/images
        return True

    async def execute(self, input_data: Stage5bInput) -> Stage5bOutput:
        """Create entity objects from tables and images.

        Args:
            input_data: Stage input

        Returns:
            Entity objects
        """
        self.logger.info(
            "Creating entities",
            document_id=input_data.document_id,
            tables=len(input_data.tables),
            images=len(input_data.images),
        )

        entities = []

        # Process tables
        for table in input_data.tables:
            entity = self._create_table_entity(
                table,
                input_data.document_id,
                input_data.page_to_toc_mapping,
            )
            entities.append(entity)

        # Process images
        for image in input_data.images:
            entity = self._create_image_entity(
                image,
                input_data.document_id,
                input_data.page_to_toc_mapping,
            )
            entities.append(entity)

        return Stage5bOutput(
            document_id=input_data.document_id,
            entities=entities,
        )

    def _create_table_entity(
        self,
        table: ExtractedTable,
        document_id: str,
        page_mapping: dict[int, str],
    ) -> Entity:
        """Create entity from extracted table."""
        # Convert to canonical JSON
        canonical = self.table_handler.table_to_canonical_json(table)

        # Convert to markdown
        markdown = self.table_handler.table_to_markdown(table)

        # Get TOC node from page mapping
        toc_node_id = page_mapping.get(table.page_number)

        # Create bbox
        bbox = None
        if table.bbox:
            bbox = BoundingBox(
                x0=table.bbox[0],
                y0=table.bbox[1],
                x1=table.bbox[2],
                y1=table.bbox[3],
            )

        return Entity(
            id=generate_id(),
            document_id=document_id,
            toc_node_id=toc_node_id,
            entity_type=EntityType.TABLE,
            page_number=table.page_number,
            sequence_in_page=table.table_index,
            bbox=bbox,
            canonical_json=canonical,
            markdown=markdown,
            caption=self._extract_table_caption(table),
        )

    def _create_image_entity(
        self,
        image: ExtractedImage,
        document_id: str,
        page_mapping: dict[int, str],
    ) -> Entity:
        """Create entity from extracted image."""
        # Get TOC node from page mapping
        toc_node_id = page_mapping.get(image.page_number)

        # Determine entity type based on image characteristics
        entity_type = self._classify_image_type(image)

        # Create bbox
        bbox = None
        if image.bbox:
            bbox = BoundingBox(
                x0=image.bbox[0],
                y0=image.bbox[1],
                x1=image.bbox[2],
                y1=image.bbox[3],
            )

        return Entity(
            id=generate_id(),
            document_id=document_id,
            toc_node_id=toc_node_id,
            entity_type=entity_type,
            page_number=image.page_number,
            sequence_in_page=image.image_index,
            bbox=bbox,
            image_path=str(image.file_path) if image.file_path else None,
            image_base64=image.base64_data,
            vision_processed=False,
        )

    def _extract_table_caption(self, table: ExtractedTable) -> Optional[str]:
        """Extract caption from table if present."""
        # Simple heuristic: check if first row looks like a caption
        if table.rows and len(table.rows) > 1:
            first_row = table.rows[0]
            if len(first_row) == 1 and first_row[0]:
                text = str(first_row[0]).strip()
                if text.lower().startswith(("table", "표")):
                    return text
        return None

    def _classify_image_type(self, image: ExtractedImage) -> EntityType:
        """Classify image type based on characteristics."""
        # Simple heuristic based on aspect ratio and size
        if image.width == 0 or image.height == 0:
            return EntityType.IMAGE

        aspect_ratio = image.width / image.height

        # Square-ish images might be diagrams
        if 0.8 <= aspect_ratio <= 1.2:
            return EntityType.DIAGRAM

        # Wide images might be charts
        if aspect_ratio > 2:
            return EntityType.CHART

        return EntityType.IMAGE

    def get_output_summary(self, output: Stage5bOutput) -> dict[str, Any]:
        """Get output summary."""
        type_counts = {}
        for entity in output.entities:
            t = (
                entity.entity_type.value
                if hasattr(entity.entity_type, "value")
                else entity.entity_type
            )
            type_counts[t] = type_counts.get(t, 0) + 1

        return {
            "total_entities": len(output.entities),
            "by_type": type_counts,
        }
