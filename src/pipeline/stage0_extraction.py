"""Stage 0: PDF Extraction."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.models import Language, PipelineStage
from src.ocr.extractor import ExtractionResult, PDFExtractor
from src.ocr.image_handler import ExtractedImage
from src.ocr.table_handler import ExtractedTable
from src.pipeline.base import BaseStage


@dataclass
class Stage0Input:
    """Input for Stage 0."""

    document_id: str
    file_path: Path


@dataclass
class Stage0Output:
    """Output from Stage 0."""

    document_id: str
    raw_text: str
    raw_text_by_page: list[str]
    page_count: int
    detected_language: Language
    tables: list[ExtractedTable]
    images: list[ExtractedImage]
    metadata: dict[str, Any]
    is_scanned: bool


class Stage0Extraction(BaseStage[Stage0Input, Stage0Output]):
    """Stage 0: Extract content from PDF."""

    stage = PipelineStage.STAGE_0_EXTRACTION
    stage_name = "extraction"

    def __init__(self, extractor: PDFExtractor):
        """Initialize stage.

        Args:
            extractor: PDF extractor instance
        """
        super().__init__()
        self.extractor = extractor

    def validate_input(self, input_data: Stage0Input) -> bool:
        """Validate input."""
        if not input_data.document_id:
            return False
        if not input_data.file_path.exists():
            return False
        return True

    def validate_output(self, output_data: Stage0Output) -> bool:
        """Validate output."""
        if not output_data.raw_text:
            # Allow empty text for scanned PDFs
            return output_data.is_scanned
        return True

    async def execute(self, input_data: Stage0Input) -> Stage0Output:
        """Execute PDF extraction.

        Args:
            input_data: Stage input

        Returns:
            Extraction results
        """
        self.logger.info(
            "Extracting PDF",
            document_id=input_data.document_id,
            path=str(input_data.file_path),
        )

        result = await self.extractor.extract(
            input_data.file_path,
            input_data.document_id,
        )

        return Stage0Output(
            document_id=result.document_id,
            raw_text=result.raw_text,
            raw_text_by_page=[p.content for p in result.text_by_page],
            page_count=result.page_count,
            detected_language=result.detected_language,
            tables=result.tables,
            images=result.images,
            metadata=result.metadata,
            is_scanned=result.is_scanned,
        )

    def get_output_summary(self, output: Stage0Output) -> dict[str, Any]:
        """Get output summary."""
        return {
            "page_count": output.page_count,
            "text_length": len(output.raw_text),
            "table_count": len(output.tables),
            "image_count": len(output.images),
            "language": output.detected_language.value,
            "is_scanned": output.is_scanned,
        }
