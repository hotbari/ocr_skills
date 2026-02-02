"""Text extraction from PDF using PyMuPDF."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
import structlog

from src.core.exceptions import TextExtractionError

logger = structlog.get_logger()


@dataclass
class PageText:
    """Text content from a single page."""

    page_number: int
    content: str
    char_count: int


@dataclass
class TextBlock:
    """Positioned text block for layout analysis."""

    page_number: int
    content: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1
    block_type: int  # 0=text, 1=image


class TextHandler:
    """Handles text extraction from PDF documents."""

    def __init__(self):
        self.logger = logger.bind(component="TextHandler")

    def extract_text(self, pdf_path: Path) -> tuple[str, int]:
        """Extract all text from PDF.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Tuple of (raw_text, page_count)

        Raises:
            TextExtractionError: If extraction fails
        """
        try:
            self.logger.info("Extracting text from PDF", path=str(pdf_path))

            doc = fitz.open(str(pdf_path))
            page_count = len(doc)
            all_text = []

            for page_num in range(page_count):
                page = doc[page_num]
                text = page.get_text("text")
                all_text.append(text)

            doc.close()

            raw_text = "\n\n".join(all_text)
            self.logger.info(
                "Text extraction complete",
                page_count=page_count,
                char_count=len(raw_text),
            )

            return raw_text, page_count

        except Exception as e:
            self.logger.error("Text extraction failed", error=str(e))
            raise TextExtractionError(f"Failed to extract text: {e}")

    def extract_text_by_page(self, pdf_path: Path) -> list[PageText]:
        """Extract text from each page separately.

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of PageText objects, one per page

        Raises:
            TextExtractionError: If extraction fails
        """
        try:
            doc = fitz.open(str(pdf_path))
            pages = []

            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")
                pages.append(
                    PageText(
                        page_number=page_num + 1,  # 1-indexed
                        content=text,
                        char_count=len(text),
                    )
                )

            doc.close()
            return pages

        except Exception as e:
            raise TextExtractionError(f"Failed to extract text by page: {e}")

    def extract_text_blocks(self, pdf_path: Path) -> list[TextBlock]:
        """Extract positioned text blocks for layout analysis.

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of TextBlock objects with position info

        Raises:
            TextExtractionError: If extraction fails
        """
        try:
            doc = fitz.open(str(pdf_path))
            blocks = []

            for page_num in range(len(doc)):
                page = doc[page_num]
                page_blocks = page.get_text("dict")["blocks"]

                for block in page_blocks:
                    if "lines" in block:  # Text block
                        text_content = ""
                        for line in block["lines"]:
                            for span in line["spans"]:
                                text_content += span["text"]
                            text_content += "\n"

                        blocks.append(
                            TextBlock(
                                page_number=page_num + 1,
                                content=text_content.strip(),
                                bbox=(
                                    block["bbox"][0],
                                    block["bbox"][1],
                                    block["bbox"][2],
                                    block["bbox"][3],
                                ),
                                block_type=0,
                            )
                        )

            doc.close()
            return blocks

        except Exception as e:
            raise TextExtractionError(f"Failed to extract text blocks: {e}")

    def get_metadata(self, pdf_path: Path) -> dict:
        """Extract PDF metadata.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Dictionary with metadata fields
        """
        try:
            doc = fitz.open(str(pdf_path))
            metadata = doc.metadata
            page_count = len(doc)
            doc.close()

            return {
                "title": metadata.get("title"),
                "author": metadata.get("author"),
                "subject": metadata.get("subject"),
                "creator": metadata.get("creator"),
                "producer": metadata.get("producer"),
                "creation_date": metadata.get("creationDate"),
                "modification_date": metadata.get("modDate"),
                "page_count": page_count,
            }

        except Exception as e:
            self.logger.warning("Failed to extract metadata", error=str(e))
            return {}

    def check_is_scanned(self, pdf_path: Path) -> bool:
        """Check if PDF appears to be scanned (image-based).

        Args:
            pdf_path: Path to PDF file

        Returns:
            True if PDF appears to be scanned/image-based
        """
        try:
            doc = fitz.open(str(pdf_path))

            # Check first few pages
            pages_to_check = min(3, len(doc))
            total_text = 0
            total_images = 0

            for page_num in range(pages_to_check):
                page = doc[page_num]
                text = page.get_text("text").strip()
                total_text += len(text)
                total_images += len(page.get_images())

            doc.close()

            # If very little text but images exist, likely scanned
            is_scanned = total_text < 100 and total_images > 0
            self.logger.info(
                "Scanned PDF check",
                is_scanned=is_scanned,
                text_chars=total_text,
                image_count=total_images,
            )

            return is_scanned

        except Exception:
            return False
