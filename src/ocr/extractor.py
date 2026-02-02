"""Unified PDF extraction interface."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import structlog

from src.core.config import Settings, get_settings
from src.core.exceptions import OCRError
from src.core.models import Language
from src.ocr.image_handler import ExtractedImage, ImageHandler
from src.ocr.table_handler import ExtractedTable, TableHandler
from src.ocr.text_handler import PageText, TextHandler
from src.utils.language_detector import LanguageDetector

logger = structlog.get_logger()


@dataclass
class ExtractionResult:
    """Complete extraction result from PDF."""

    document_id: str
    raw_text: str
    page_count: int
    text_by_page: list[PageText]
    tables: list[ExtractedTable]
    images: list[ExtractedImage]
    metadata: dict[str, Any]
    detected_language: Language
    is_scanned: bool = False


class PDFExtractor:
    """Unified PDF extraction interface combining text, tables, and images."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        text_handler: Optional[TextHandler] = None,
        table_handler: Optional[TableHandler] = None,
        image_handler: Optional[ImageHandler] = None,
        language_detector: Optional[LanguageDetector] = None,
    ):
        """Initialize PDF extractor.

        Args:
            settings: Application settings
            text_handler: Custom text handler
            table_handler: Custom table handler
            image_handler: Custom image handler
            language_detector: Custom language detector
        """
        self.settings = settings or get_settings()
        self.text_handler = text_handler or TextHandler()
        self.table_handler = table_handler or TableHandler()
        self.image_handler = image_handler or ImageHandler(
            output_dir=self.settings.upload_dir
        )
        self.language_detector = language_detector or LanguageDetector()
        self.logger = logger.bind(component="PDFExtractor")

    async def extract(self, pdf_path: Path, document_id: str) -> ExtractionResult:
        """Extract all content from PDF.

        Args:
            pdf_path: Path to PDF file
            document_id: Document ID for organizing output

        Returns:
            Complete extraction result

        Raises:
            OCRError: If extraction fails
        """
        self.logger.info(
            "Starting PDF extraction",
            path=str(pdf_path),
            document_id=document_id,
        )

        try:
            # Check if scanned PDF
            is_scanned = self.text_handler.check_is_scanned(pdf_path)

            if is_scanned:
                self.logger.warning(
                    "PDF appears to be scanned, text extraction may be limited"
                )
                # TODO: Implement OCR fallback with pytesseract for scanned PDFs

            # Extract text
            raw_text, page_count = self.text_handler.extract_text(pdf_path)
            text_by_page = self.text_handler.extract_text_by_page(pdf_path)

            # Extract metadata
            metadata = self.text_handler.get_metadata(pdf_path)

            # Detect language
            detected_language = self.language_detector.detect(raw_text)

            # Extract tables
            tables = self.table_handler.extract_tables(pdf_path)

            # Extract images
            images = self.image_handler.extract_images(pdf_path, document_id)

            result = ExtractionResult(
                document_id=document_id,
                raw_text=raw_text,
                page_count=page_count,
                text_by_page=text_by_page,
                tables=tables,
                images=images,
                metadata=metadata,
                detected_language=detected_language,
                is_scanned=is_scanned,
            )

            self.logger.info(
                "PDF extraction complete",
                document_id=document_id,
                page_count=page_count,
                text_length=len(raw_text),
                table_count=len(tables),
                image_count=len(images),
                language=detected_language.value,
            )

            return result

        except Exception as e:
            self.logger.error(
                "PDF extraction failed",
                document_id=document_id,
                error=str(e),
            )
            raise OCRError(f"PDF extraction failed: {e}")

    def get_file_size(self, pdf_path: Path) -> int:
        """Get PDF file size in bytes.

        Args:
            pdf_path: Path to PDF file

        Returns:
            File size in bytes
        """
        return pdf_path.stat().st_size

    def validate_pdf(self, pdf_path: Path) -> tuple[bool, str]:
        """Validate PDF file.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Check file exists
            if not pdf_path.exists():
                return False, "File does not exist"

            # Check extension
            if pdf_path.suffix.lower() != ".pdf":
                return False, "File is not a PDF"

            # Check file size
            file_size = self.get_file_size(pdf_path)
            max_size = self.settings.max_file_size_mb * 1024 * 1024

            if file_size > max_size:
                return (
                    False,
                    f"File size exceeds {self.settings.max_file_size_mb}MB limit",
                )

            # Try to open with PyMuPDF
            import fitz

            doc = fitz.open(str(pdf_path))
            page_count = len(doc)

            if page_count == 0:
                doc.close()
                return False, "PDF has no pages"

            if page_count > self.settings.max_pages:
                doc.close()
                return False, f"PDF exceeds {self.settings.max_pages} page limit"

            doc.close()
            return True, ""

        except Exception as e:
            return False, f"Invalid PDF: {e}"
