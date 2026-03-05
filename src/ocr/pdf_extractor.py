"""Stage 0: PyMuPDF 기반 PDF 추출기."""

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import structlog

from src.core.models import BoundingBox, Language

logger = structlog.get_logger()


@dataclass
class PageText:
    page_number: int
    content: str
    word_count: int = 0


@dataclass
class RawImage:
    page_number: int
    sequence_in_page: int
    image_path: str
    bbox: BoundingBox
    width: int
    height: int
    ext: str = "png"


@dataclass
class RawTable:
    page_number: int
    sequence_in_page: int
    bbox: BoundingBox
    rows: list[list[str]] = field(default_factory=list)
    markdown: str = ""


@dataclass
class ExtractionResult:
    document_id: str
    raw_text: str
    text_by_page: list[PageText]
    page_count: int
    images: list[RawImage]
    tables: list[RawTable]
    metadata: dict[str, Any]
    detected_language: Language
    is_scanned: bool


class PDFExtractor:
    """PyMuPDF를 사용한 PDF 텍스트/이미지/테이블 추출."""

    SCANNED_TEXT_THRESHOLD = 50  # 페이지당 최소 글자 수 (미만이면 스캔 PDF)

    def __init__(self, upload_dir: Path):
        self.upload_dir = upload_dir

    async def extract(self, pdf_path: Path, document_id: str) -> ExtractionResult:
        logger.info("PDF 추출 시작", document_id=document_id, path=str(pdf_path))

        doc = fitz.open(str(pdf_path))

        metadata = self._extract_metadata(doc)
        text_by_page = self._extract_text(doc)
        raw_text = "\n\n".join(p.content for p in text_by_page if p.content)
        is_scanned = self._detect_scanned(text_by_page)
        detected_language = self._detect_language(raw_text)

        images_dir = self.upload_dir / document_id / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        images = self._extract_images(doc, document_id, images_dir)
        tables = self._extract_tables(doc)

        doc.close()

        logger.info(
            "PDF 추출 완료",
            document_id=document_id,
            pages=len(text_by_page),
            images=len(images),
            tables=len(tables),
            is_scanned=is_scanned,
        )

        return ExtractionResult(
            document_id=document_id,
            raw_text=raw_text,
            text_by_page=text_by_page,
            page_count=len(text_by_page),
            images=images,
            tables=tables,
            metadata=metadata,
            detected_language=detected_language,
            is_scanned=is_scanned,
        )

    def _extract_metadata(self, doc: fitz.Document) -> dict[str, Any]:
        meta = doc.metadata or {}
        return {
            "title": meta.get("title") or None,
            "author": meta.get("author") or None,
            "subject": meta.get("subject") or None,
            "page_count": len(doc),
            "file_size_bytes": 0,  # 호출 전 설정
        }

    def _extract_text(self, doc: fitz.Document) -> list[PageText]:
        pages = []
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            pages.append(PageText(
                page_number=i,
                content=text,
                word_count=len(text.split()),
            ))
        return pages

    def _detect_scanned(self, pages: list[PageText]) -> bool:
        if not pages:
            return False
        total_chars = sum(len(p.content) for p in pages)
        avg_chars = total_chars / len(pages)
        return avg_chars < self.SCANNED_TEXT_THRESHOLD

    def _detect_language(self, text: str) -> Language:
        if not text:
            return Language.UNKNOWN
        sample = text[:2000]
        korean_chars = sum(1 for c in sample if "\uAC00" <= c <= "\uD7A3")
        ascii_chars = sum(1 for c in sample if c.isascii() and c.isalpha())
        total = len(sample)
        if total == 0:
            return Language.UNKNOWN
        ko_ratio = korean_chars / total
        en_ratio = ascii_chars / total
        if ko_ratio > 0.2 and en_ratio > 0.1:
            return Language.MIXED
        if ko_ratio > 0.1:
            return Language.KOREAN
        if en_ratio > 0.1:
            return Language.ENGLISH
        return Language.UNKNOWN

    def _extract_images(
        self, doc: fitz.Document, document_id: str, images_dir: Path
    ) -> list[RawImage]:
        results = []
        for page_num, page in enumerate(doc, start=1):
            seq = 0
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                try:
                    base_image = doc.extract_image(xref)
                    img_bytes = base_image["image"]
                    ext = base_image.get("ext", "png")

                    filename = f"page{page_num:03d}_img{seq:02d}.{ext}"
                    img_path = images_dir / filename
                    img_path.write_bytes(img_bytes)

                    # 바운딩 박스 추출
                    img_rects = page.get_image_rects(xref)
                    if img_rects:
                        r = img_rects[0]
                        bbox = BoundingBox(x0=r.x0, y0=r.y0, x1=r.x1, y1=r.y1)
                    else:
                        pr = page.rect
                        bbox = BoundingBox(x0=pr.x0, y0=pr.y0, x1=pr.x1, y1=pr.y1)

                    results.append(RawImage(
                        page_number=page_num,
                        sequence_in_page=seq,
                        image_path=str(img_path),
                        bbox=bbox,
                        width=base_image.get("width", 0),
                        height=base_image.get("height", 0),
                        ext=ext,
                    ))
                    seq += 1
                except Exception as e:
                    logger.warning("이미지 추출 실패", xref=xref, page=page_num, error=str(e))
        return results

    def _extract_tables(self, doc: fitz.Document) -> list[RawTable]:
        results = []
        for page_num, page in enumerate(doc, start=1):
            try:
                tables = page.find_tables()
                for seq, table in enumerate(tables):
                    rows = table.extract()
                    # 셀 None → 빈 문자열 처리
                    cleaned_rows = [
                        [str(cell) if cell is not None else "" for cell in row]
                        for row in rows
                    ]
                    markdown = self._rows_to_markdown(cleaned_rows)
                    r = table.bbox
                    bbox = BoundingBox(x0=r[0], y0=r[1], x1=r[2], y1=r[3])
                    results.append(RawTable(
                        page_number=page_num,
                        sequence_in_page=seq,
                        bbox=bbox,
                        rows=cleaned_rows,
                        markdown=markdown,
                    ))
            except Exception as e:
                logger.warning("테이블 추출 실패", page=page_num, error=str(e))
        return results

    def _rows_to_markdown(self, rows: list[list[str]]) -> str:
        if not rows:
            return ""
        lines = []
        header = rows[0]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---"] * len(header)) + " |")
        for row in rows[1:]:
            # 열 수 맞추기
            while len(row) < len(header):
                row.append("")
            lines.append("| " + " | ".join(row[: len(header)]) + " |")
        return "\n".join(lines)
