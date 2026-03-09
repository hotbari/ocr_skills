"""Stage 0: PyMuPDF 기반 PDF 추출기."""

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import numpy as np
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
    scanned_pages: list[int] = field(default_factory=list)  # 스캔으로 판별된 페이지 번호 목록


class PDFExtractor:
    """PyMuPDF를 사용한 PDF 텍스트/이미지/테이블 추출."""

    def __init__(
        self,
        upload_dir: Path,
        scan_min_chars_per_page: int = 50,
        scan_image_ratio_threshold: float = 0.8,
    ):
        self.upload_dir = upload_dir
        self.scan_min_chars_per_page = scan_min_chars_per_page
        self.scan_image_ratio_threshold = scan_image_ratio_threshold

    async def extract(self, pdf_path: Path, document_id: str) -> ExtractionResult:
        logger.info("PDF 추출 시작", document_id=document_id, path=str(pdf_path))

        doc = fitz.open(str(pdf_path))

        metadata = self._extract_metadata(doc)
        text_by_page = self._extract_text(doc)
        raw_text = "\n\n".join(p.content for p in text_by_page if p.content)
        scanned_pages = self._detect_scanned_pages(doc, text_by_page)
        is_scanned = len(scanned_pages) > len(text_by_page) / 2
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
            scanned_pages_count=len(scanned_pages),
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
            scanned_pages=scanned_pages,
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

    def _detect_scanned_pages(self, doc: fitz.Document, pages: list[PageText]) -> list[int]:
        """페이지별 스캔 여부를 판별하여 스캔 페이지 번호 목록을 반환한다.

        판별 기준 (OR 조건):
        - 텍스트 글자수 < scan_min_chars_per_page
        - 이미지 면적 비율 > scan_image_ratio_threshold AND 임베디드 폰트 없음
        """
        scanned = []
        for page_num, page in enumerate(doc, start=1):
            text_len = len(page.get_text().strip())
            has_fonts = len(page.get_fonts()) > 0

            # 이미지 면적 합산
            image_area = 0.0
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                try:
                    for r in page.get_image_rects(xref):
                        image_area += (r.x1 - r.x0) * (r.y1 - r.y0)
                except Exception:
                    pass
            page_area = page.rect.width * page.rect.height
            img_ratio = image_area / page_area if page_area > 0 else 0.0

            is_scan = (
                text_len < self.scan_min_chars_per_page
                or (img_ratio > self.scan_image_ratio_threshold and not has_fonts)
            )
            if is_scan:
                scanned.append(page_num)

        logger.debug(
            "스캔 페이지 판별",
            total_pages=len(pages),
            scanned_count=len(scanned),
            scanned_pages=scanned,
        )
        return scanned

    @staticmethod
    def preprocess_scan_image(img_array: np.ndarray) -> np.ndarray:
        """스캔 페이지 이미지를 OCR에 최적화된 형태로 전처리한다.

        처리 순서:
        1. 저해상도(width<1500 or height<2000)이면 2x 업스케일
        2. 그레이스케일 변환
        3. Otsu 이진화
        4. 모폴로지 노이즈 제거
        5. BGR로 복원 (PP-Structure 입력 형식 유지)
        """
        import cv2

        h, w = img_array.shape[:2]
        if w < 1500 or h < 2000:
            img_array = cv2.resize(img_array, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
        else:
            gray = img_array

        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        denoised = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        result = cv2.cvtColor(denoised, cv2.COLOR_GRAY2BGR)
        return result

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
