"""Stage 1: PP-Structure 레이아웃 분석기.

PP-Structure를 사용해 페이지별 블록(제목/본문/테이블/이미지)을 감지합니다.
스캔 PDF의 경우 PaddleOCR로 텍스트도 함께 추출합니다.

설치:
    pip install paddlepaddle paddleocr
    pip install "paddleocr[ppstructure]"
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz
import structlog

from src.core.models import BlockType, BoundingBox, LayoutBlock

logger = structlog.get_logger()

# PP-Structure 타입 → 내부 BlockType 매핑
_TYPE_MAP: dict[str, BlockType] = {
    "title": BlockType.TITLE,
    "text": BlockType.TEXT,
    "table": BlockType.TABLE,
    "figure": BlockType.FIGURE,
    "figure_caption": BlockType.FIGURE_CAPTION,
    "table_caption": BlockType.TABLE_CAPTION,
    "header": BlockType.HEADER,
    "footer": BlockType.FOOTER,
    "reference": BlockType.REFERENCE,
    "equation": BlockType.EQUATION,
}


@dataclass
class LayoutAnalysisResult:
    document_id: str
    blocks_by_page: dict[int, list[LayoutBlock]]  # page_number → blocks
    total_blocks: int
    page_count: int


class LayoutAnalyzer:
    """PP-Structure 기반 레이아웃 분석기.

    PP-Structure가 설치되지 않은 경우 PyMuPDF 블록 분석으로 fallback합니다.
    """

    def __init__(self, use_gpu: bool = False):
        self.use_gpu = use_gpu
        self._pp_structure = None
        self._paddle_ocr = None
        self._pp_available = False
        self._try_init_pp_structure()

    def _try_init_pp_structure(self) -> None:
        try:
            from paddleocr import PPStructure
            self._pp_structure = PPStructure(
                table=True,
                ocr=True,
                show_log=False,
                use_gpu=self.use_gpu,
                lang="ch",  # 한국어 포함 다국어 지원
            )
            self._pp_available = True
            logger.info("PP-Structure 초기화 성공")
        except ImportError:
            logger.warning("PP-Structure 미설치 - PyMuPDF 블록 분석으로 fallback")
        except Exception as e:
            logger.warning("PP-Structure 초기화 실패", error=str(e), extra="PyMuPDF fallback 사용")

    async def analyze(
        self, pdf_path: Path, document_id: str, is_scanned: bool
    ) -> LayoutAnalysisResult:
        logger.info(
            "레이아웃 분석 시작",
            document_id=document_id,
            is_scanned=is_scanned,
            engine="PP-Structure" if self._pp_available else "PyMuPDF",
        )

        if self._pp_available:
            blocks_by_page = await self._analyze_with_pp_structure(pdf_path, document_id)
        else:
            blocks_by_page = self._analyze_with_pymupdf(pdf_path, document_id)

        total = sum(len(v) for v in blocks_by_page.values())
        logger.info("레이아웃 분석 완료", total_blocks=total)

        return LayoutAnalysisResult(
            document_id=document_id,
            blocks_by_page=blocks_by_page,
            total_blocks=total,
            page_count=len(blocks_by_page),
        )

    async def _analyze_with_pp_structure(
        self, pdf_path: Path, document_id: str
    ) -> dict[int, list[LayoutBlock]]:
        """PP-Structure로 페이지별 블록 감지."""
        import cv2
        import numpy as np

        doc = fitz.open(str(pdf_path))
        blocks_by_page: dict[int, list[LayoutBlock]] = {}

        for page_num, page in enumerate(doc, start=1):
            # PDF 페이지를 이미지로 변환
            mat = fitz.Matrix(2.0, 2.0)  # 2x 해상도
            pix = page.get_pixmap(matrix=mat)
            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            if pix.n == 4:  # RGBA → BGR
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR)
            elif pix.n == 3:
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

            try:
                result = self._pp_structure(img_array)
                blocks = self._parse_pp_result(result, page_num, document_id, scale=2.0)
            except Exception as e:
                logger.warning("PP-Structure 페이지 분석 실패", page=page_num, error=str(e))
                blocks = self._extract_pymupdf_page_blocks(page, page_num, document_id)

            blocks_by_page[page_num] = blocks

        doc.close()
        return blocks_by_page

    def _parse_pp_result(
        self,
        result: list[dict],
        page_num: int,
        document_id: str,
        scale: float = 1.0,
    ) -> list[LayoutBlock]:
        blocks = []
        for seq, item in enumerate(result):
            block_type_str = item.get("type", "text").lower()
            block_type = _TYPE_MAP.get(block_type_str, BlockType.TEXT)

            bbox_raw = item.get("bbox", [0, 0, 0, 0])
            bbox = BoundingBox(
                x0=bbox_raw[0] / scale,
                y0=bbox_raw[1] / scale,
                x1=bbox_raw[2] / scale,
                y1=bbox_raw[3] / scale,
            )

            # 텍스트 추출 (OCR 결과 포함)
            text = self._extract_text_from_pp_item(item)

            blocks.append(LayoutBlock(
                document_id=document_id,
                page_number=page_num,
                block_type=block_type,
                bbox=bbox,
                text=text,
                confidence=item.get("score", 1.0),
                sequence_in_page=seq,
            ))
        return blocks

    def _extract_text_from_pp_item(self, item: dict) -> str | None:
        """PP-Structure 결과에서 텍스트 추출."""
        # 직접 텍스트
        if "res" in item:
            res = item["res"]
            if isinstance(res, list):
                # OCR 결과 목록
                texts = []
                for r in res:
                    if isinstance(r, dict):
                        t = r.get("text", "") or ""
                        texts.append(t)
                    elif isinstance(r, (list, tuple)) and len(r) >= 2:
                        t = r[1][0] if isinstance(r[1], (list, tuple)) else str(r[1])
                        texts.append(t)
                return " ".join(texts).strip() or None
            elif isinstance(res, dict):
                return res.get("html") or res.get("text") or None
        return item.get("text") or None

    def _analyze_with_pymupdf(
        self, pdf_path: Path, document_id: str
    ) -> dict[int, list[LayoutBlock]]:
        """PyMuPDF 블록 분석 fallback."""
        doc = fitz.open(str(pdf_path))
        blocks_by_page: dict[int, list[LayoutBlock]] = {}

        for page_num, page in enumerate(doc, start=1):
            blocks = self._extract_pymupdf_page_blocks(page, page_num, document_id)
            blocks_by_page[page_num] = blocks

        doc.close()
        return blocks_by_page

    def _extract_pymupdf_page_blocks(
        self, page: fitz.Page, page_num: int, document_id: str
    ) -> list[LayoutBlock]:
        """PyMuPDF의 블록 정보를 LayoutBlock으로 변환."""
        raw_blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, block_type)
        blocks = []
        for seq, b in enumerate(raw_blocks):
            x0, y0, x1, y1, text, block_no, block_type_int = b[:7]
            text = text.strip()
            if not text:
                continue

            block_type = self._infer_block_type_from_text(text, x0, y0, page)

            blocks.append(LayoutBlock(
                document_id=document_id,
                page_number=page_num,
                block_type=block_type,
                bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1),
                text=text,
                confidence=1.0,
                sequence_in_page=seq,
            ))
        return blocks

    def _infer_block_type_from_text(
        self, text: str, x0: float, y0: float, page: fitz.Page
    ) -> BlockType:
        """텍스트 특성으로 블록 타입 추론 (PyMuPDF fallback용)."""
        stripped = text.strip()
        words = stripped.split()

        # 짧고 굵은 텍스트는 제목으로 추정
        if len(words) <= 10 and len(stripped) < 100:
            # 숫자로 시작하는 제목 패턴 (예: "1.", "1.1", "제1장")
            if (
                stripped[0].isdigit()
                or stripped.startswith("제")
                or stripped.startswith("#")
                or stripped.isupper()
            ):
                return BlockType.TITLE

        # 페이지 상단 10% → 헤더
        page_height = page.rect.height
        if y0 < page_height * 0.08:
            return BlockType.HEADER
        # 페이지 하단 8% → 푸터
        if y0 > page_height * 0.92:
            return BlockType.FOOTER

        return BlockType.TEXT
