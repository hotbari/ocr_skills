"""Image extraction from PDF using PyMuPDF."""

import base64
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import fitz
import structlog
from PIL import Image

from src.core.exceptions import ImageExtractionError

logger = structlog.get_logger()


@dataclass
class ExtractedImage:
    """Extracted image with metadata."""

    page_number: int
    image_index: int
    file_path: Optional[Path] = None
    bbox: Optional[tuple[float, float, float, float]] = None
    width: int = 0
    height: int = 0
    format: str = "png"
    xref: int = 0  # PyMuPDF reference
    base64_data: Optional[str] = None


class ImageHandler:
    """Handles image extraction from PDF documents."""

    # Minimum dimensions to consider an image (filter out icons/decorations)
    MIN_WIDTH = 50
    MIN_HEIGHT = 50

    def __init__(self, output_dir: Optional[Path] = None):
        """Initialize image handler.

        Args:
            output_dir: Directory to save extracted images. If None, images stored in memory.
        """
        self.output_dir = output_dir
        self.logger = logger.bind(component="ImageHandler")

    def extract_images(self, pdf_path: Path, document_id: str) -> list[ExtractedImage]:
        """Extract all images from PDF.

        Args:
            pdf_path: Path to PDF file
            document_id: Document ID for organizing output

        Returns:
            List of ExtractedImage objects

        Raises:
            ImageExtractionError: If extraction fails
        """
        try:
            self.logger.info("Extracting images from PDF", path=str(pdf_path))

            doc = fitz.open(str(pdf_path))
            all_images = []

            # Create output directory if needed
            image_output_dir = None
            if self.output_dir:
                image_output_dir = self.output_dir / document_id / "images"
                image_output_dir.mkdir(parents=True, exist_ok=True)

            image_index = 0

            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images(full=True)

                for img_info in image_list:
                    xref = img_info[0]

                    try:
                        # Extract image
                        base_image = doc.extract_image(xref)
                        if not base_image:
                            continue

                        image_bytes = base_image["image"]
                        image_ext = base_image.get("ext", "png")

                        # Get dimensions
                        img = Image.open(io.BytesIO(image_bytes))
                        width, height = img.size

                        # Filter small images (likely icons/decorations)
                        if width < self.MIN_WIDTH or height < self.MIN_HEIGHT:
                            continue

                        # Get bounding box for the image on the page
                        bbox = self._get_image_bbox(page, xref)

                        extracted = ExtractedImage(
                            page_number=page_num + 1,
                            image_index=image_index,
                            width=width,
                            height=height,
                            format=image_ext,
                            xref=xref,
                            bbox=bbox,
                        )

                        # Save to file or encode as base64
                        if image_output_dir:
                            file_path = (
                                image_output_dir
                                / f"page{page_num + 1}_img{image_index}.{image_ext}"
                            )
                            with open(file_path, "wb") as f:
                                f.write(image_bytes)
                            extracted.file_path = file_path
                        else:
                            # Store as base64
                            extracted.base64_data = base64.b64encode(
                                image_bytes
                            ).decode("utf-8")

                        all_images.append(extracted)
                        image_index += 1

                    except Exception as e:
                        self.logger.warning(
                            "Failed to extract image",
                            page=page_num + 1,
                            xref=xref,
                            error=str(e),
                        )
                        continue

            doc.close()

            self.logger.info("Image extraction complete", image_count=len(all_images))
            return all_images

        except Exception as e:
            self.logger.error("Image extraction failed", error=str(e))
            raise ImageExtractionError(f"Failed to extract images: {e}")

    def _get_image_bbox(
        self, page: fitz.Page, xref: int
    ) -> Optional[tuple[float, float, float, float]]:
        """Get bounding box for an image on a page.

        Args:
            page: PyMuPDF page object
            xref: Image cross-reference

        Returns:
            Bounding box tuple or None
        """
        try:
            # Get all image instances on the page
            for img in page.get_images(full=True):
                if img[0] == xref:
                    # Find the image rectangle
                    for block in page.get_text("dict")["blocks"]:
                        if block.get("type") == 1:  # Image block
                            return (
                                block["bbox"][0],
                                block["bbox"][1],
                                block["bbox"][2],
                                block["bbox"][3],
                            )
            return None
        except Exception:
            return None

    def get_image_context(
        self, pdf_path: Path, image: ExtractedImage, context_chars: int = 500
    ) -> str:
        """Get surrounding text context for an image.

        Args:
            pdf_path: Path to PDF file
            image: Extracted image
            context_chars: Number of characters of context to extract

        Returns:
            Surrounding text context
        """
        try:
            doc = fitz.open(str(pdf_path))
            page = doc[image.page_number - 1]

            # Get all text on the page
            page_text = page.get_text("text")

            # If we have bbox, try to get nearby text
            if image.bbox:
                # Get text blocks
                blocks = page.get_text("dict")["blocks"]
                nearby_text = []

                img_center_y = (image.bbox[1] + image.bbox[3]) / 2

                for block in blocks:
                    if "lines" not in block:
                        continue

                    block_center_y = (block["bbox"][1] + block["bbox"][3]) / 2

                    # Check if block is near the image vertically
                    if abs(block_center_y - img_center_y) < 200:
                        for line in block["lines"]:
                            for span in line["spans"]:
                                nearby_text.append(span["text"])

                if nearby_text:
                    context = " ".join(nearby_text)[:context_chars]
                    doc.close()
                    return context

            # Fallback: return portion of page text
            doc.close()
            return page_text[:context_chars]

        except Exception as e:
            self.logger.warning("Failed to get image context", error=str(e))
            return ""

    def should_use_vision(
        self, image: ExtractedImage, has_caption: bool = False
    ) -> bool:
        """Determine if image should be processed with vision API.

        Args:
            image: Extracted image
            has_caption: Whether image has an existing caption

        Returns:
            True if vision processing is recommended
        """
        # Skip if too small (likely icon/decoration)
        if image.width < 100 or image.height < 100:
            return False

        # Skip if already has caption
        if has_caption:
            return False

        # Large images are more likely to be important
        if image.width > 300 and image.height > 300:
            return True

        # Medium images might be diagrams
        if image.width > 150 and image.height > 150:
            return True

        return False

    def image_to_base64(self, image: ExtractedImage) -> Optional[str]:
        """Get base64 encoded image data.

        Args:
            image: Extracted image

        Returns:
            Base64 encoded string or None
        """
        if image.base64_data:
            return image.base64_data

        if image.file_path and image.file_path.exists():
            with open(image.file_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")

        return None
