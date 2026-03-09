"""Stage 1: 레이아웃 분석기 (PP-Structure 미사용, 한국어 최적화).

디지털 PDF:
  - 텍스트/제목/헤더/푸터: PyMuPDF get_text("dict") → 폰트 크기 기반 분류
  - 테이블: PyMuPDF get_drawings() 벡터 선 감지 → PyMuPDF get_textbox() 한국어 셀 추출
  - 이미지: Stage 0에서 수집된 RawImage 활용 (FIGURE 블록 생성)

스캔 PDF:
  - EasyOCR(['ko', 'en']) → 텍스트 인식 + 위치 기반 레이아웃 추론
"""

import re
from dataclasses import dataclass
from pathlib import Path

import fitz
import structlog

from src.core.models import BlockType, BoundingBox, LayoutBlock

logger = structlog.get_logger()


@dataclass
class LayoutAnalysisResult:
    document_id: str
    blocks_by_page: dict[int, list[LayoutBlock]]   # page_number → blocks
    total_blocks: int
    page_count: int


class LayoutAnalyzer:
    """한국어 최적화 레이아웃 분석기.

    PP-Structure 미사용. PyMuPDF + EasyOCR 조합으로 한국어 정확도 최우선.
    """

    def __init__(
        self,
        use_gpu: bool = False,
        lang: str = "korean",
        use_angle_cls: bool = False,
        block_merge_enabled: bool = True,
        block_merge_y_gap: float = 10.0,
        easyocr_lang: list[str] | None = None,
        # 테이블 감지 파라미터
        table_min_line_len: float = 20.0,      # 테이블 선 최소 길이(pt)
        table_max_line_width: float = 3.0,     # 테이블 선 최대 두께(pt)
        table_row_gap_threshold: float = 80.0, # 행 클러스터 갭 임계값(pt)
    ):
        self.use_gpu = use_gpu
        self.lang = lang
        self.block_merge_enabled = block_merge_enabled
        self.block_merge_y_gap = block_merge_y_gap
        self.easyocr_lang = easyocr_lang or ["ko", "en"]
        self.table_min_line_len = table_min_line_len
        self.table_max_line_width = table_max_line_width
        self.table_row_gap_threshold = table_row_gap_threshold

        self._easyocr_reader = None
        self._easyocr_tried = False

        logger.info(
            "LayoutAnalyzer 초기화",
            engine="PyMuPDF+VectorTable+EasyOCR",
            easyocr_lang=self.easyocr_lang,
        )

    # ── EasyOCR lazy init ─────────────────────────────────────────────────

    def _lazy_init_easyocr(self) -> None:
        if self._easyocr_tried:
            return
        self._easyocr_tried = True
        try:
            import easyocr
            self._easyocr_reader = easyocr.Reader(
                self.easyocr_lang, gpu=self.use_gpu, verbose=False
            )
            logger.info("EasyOCR 초기화 성공", lang=self.easyocr_lang)
        except ImportError:
            logger.warning("EasyOCR 미설치 - 스캔 페이지 PyMuPDF fallback 사용")
        except Exception as e:
            logger.warning("EasyOCR 초기화 실패", error=str(e))

    # ── 공개 API ──────────────────────────────────────────────────────────

    async def analyze(
        self,
        pdf_path: Path,
        document_id: str,
        is_scanned: bool,
        scanned_pages: list[int] | None = None,
    ) -> LayoutAnalysisResult:
        scanned_pages = scanned_pages or []
        logger.info(
            "레이아웃 분석 시작",
            document_id=document_id,
            engine="PyMuPDF+VectorTable",
            scanned_pages_count=len(scanned_pages),
            easyocr_for_scanned=bool(scanned_pages),
        )

        blocks_by_page = self._analyze_document(pdf_path, document_id, scanned_pages)

        total = sum(len(v) for v in blocks_by_page.values())
        logger.info("레이아웃 분석 완료", total_blocks=total)

        return LayoutAnalysisResult(
            document_id=document_id,
            blocks_by_page=blocks_by_page,
            total_blocks=total,
            page_count=len(blocks_by_page),
        )

    # ── 문서 분석 ─────────────────────────────────────────────────────────

    def _analyze_document(
        self,
        pdf_path: Path,
        document_id: str,
        scanned_pages: list[int],
    ) -> dict[int, list[LayoutBlock]]:
        doc = fitz.open(str(pdf_path))
        blocks_by_page: dict[int, list[LayoutBlock]] = {}

        for page_num, page in enumerate(doc, start=1):
            if page_num in scanned_pages:
                blocks = self._analyze_scanned_page(page, page_num, document_id)
            else:
                blocks = self._analyze_digital_page(page, page_num, document_id)

            blocks_by_page[page_num] = self._postprocess_blocks(blocks, page.rect.width)

        doc.close()
        return blocks_by_page

    # ── 디지털 페이지 분석 ────────────────────────────────────────────────

    def _analyze_digital_page(
        self, page: fitz.Page, page_num: int, document_id: str
    ) -> list[LayoutBlock]:
        """디지털 페이지: PyMuPDF 텍스트 블록 + 벡터선 기반 테이블."""
        text_blocks = self._extract_text_blocks(page, page_num, document_id)
        table_blocks = self._detect_vector_tables(page, page_num, document_id)

        # 텍스트 블록 중 테이블 영역과 겹치는 것 제거
        filtered_text = [
            b for b in text_blocks
            if not any(self._bbox_overlap_ratio(b.bbox, t.bbox) > 0.3 for t in table_blocks)
        ]

        # 테이블에 sequence_in_page 부여
        for i, tb in enumerate(table_blocks):
            tb.sequence_in_page = i

        return filtered_text + table_blocks

    def _extract_text_blocks(
        self, page: fitz.Page, page_num: int, document_id: str
    ) -> list[LayoutBlock]:
        """PyMuPDF get_text('dict')로 폰트 크기 기반 텍스트 블록 추출."""
        page_dict = page.get_text("dict")
        page_height = page.rect.height

        # 페이지 전체 폰트 크기 수집 → 중앙값
        raw_sizes: list[float] = []
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    raw_sizes.append(span["size"])
        median_size = sorted(raw_sizes)[len(raw_sizes) // 2] if raw_sizes else 12.0

        blocks: list[LayoutBlock] = []
        seq = 0
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue

            lines_text: list[str] = []
            max_size = 0.0
            is_bold = False

            for line in block.get("lines", []):
                line_parts: list[str] = []
                for span in line.get("spans", []):
                    line_parts.append(span["text"])
                    if span["size"] > max_size:
                        max_size = span["size"]
                    if span["flags"] & 16:
                        is_bold = True
                lines_text.append("".join(line_parts))

            text = re.sub(r"\s+", " ", " ".join(lines_text)).strip()
            if not text:
                continue

            b = block["bbox"]
            bbox = BoundingBox(x0=b[0], y0=b[1], x1=b[2], y1=b[3])
            block_type = self._infer_type_from_font(
                max_size, median_size, is_bold, b[1], page_height
            )

            blocks.append(LayoutBlock(
                document_id=document_id,
                page_number=page_num,
                block_type=block_type,
                bbox=bbox,
                text=text,
                confidence=1.0,
                sequence_in_page=seq,
                font_size=round(max_size, 2),
            ))
            seq += 1

        return blocks

    def _infer_type_from_font(
        self,
        font_size: float,
        median_size: float,
        is_bold: bool,
        y0: float,
        page_height: float,
    ) -> BlockType:
        if y0 < page_height * 0.08:
            return BlockType.HEADER
        if y0 > page_height * 0.92:
            return BlockType.FOOTER
        if font_size > median_size * 1.4 or (is_bold and font_size > median_size * 1.1):
            return BlockType.TITLE
        return BlockType.TEXT

    # ── 벡터선 기반 테이블 감지 ───────────────────────────────────────────

    def _detect_vector_tables(
        self, page: fitz.Page, page_num: int, document_id: str
    ) -> list[LayoutBlock]:
        """PDF 벡터 선 정보로 테이블 그리드를 감지하고 셀 텍스트를 추출한다.

        컬럼 경계: 수평선(h_lines)의 x 끝점 집합
        행 경계:   수평선 y값 + 수직선(v_lines) y 끝점 집합
        테이블 분리: 연속된 y값들 사이 큰 갭으로 구분
        """
        drawings = page.get_drawings()

        h_lines: list[tuple[float, float, float]] = []  # (y_center, x0, x1)
        v_lines: list[tuple[float, float, float]] = []  # (x_center, y0, y1)

        for d in drawings:
            r = d["rect"]
            w, h = r.width, r.height
            if h <= self.table_max_line_width and w >= self.table_min_line_len:
                h_lines.append(((r.y0 + r.y1) / 2, r.x0, r.x1))
            elif w <= self.table_max_line_width and h >= self.table_min_line_len:
                v_lines.append(((r.x0 + r.x1) / 2, r.y0, r.y1))

        if len(h_lines) < 2 or len(v_lines) < 2:
            return []

        # 모든 행 경계 y값 수집: h_lines y값 + v_lines 끝점
        all_ys = sorted({
            round(y) for y, x0, x1 in h_lines
        } | {
            round(y) for x, y0, y1 in v_lines for y in (y0, y1)
        })

        # 큰 갭(>gap_threshold)으로 테이블 그룹 분리
        y_groups: list[list[int]] = []
        group: list[int] = [all_ys[0]]
        for y in all_ys[1:]:
            if y - group[-1] > self.table_row_gap_threshold:
                y_groups.append(group)
                group = [y]
            else:
                group.append(y)
        y_groups.append(group)

        result_blocks: list[LayoutBlock] = []
        for y_group in y_groups:
            if len(y_group) < 2:
                continue

            table_y0 = float(y_group[0])
            table_y1 = float(y_group[-1])

            # 이 y 범위와 겹치는 수평선만 → 컬럼 경계 추출
            relevant_h = [
                h for h in h_lines if table_y0 - 5 <= h[0] <= table_y1 + 5
            ]
            if not relevant_h:
                continue

            col_xs = sorted({round(x) for y, x0, x1 in relevant_h for x in (x0, x1)})
            if len(col_xs) < 2:
                continue

            # 셀별 텍스트 추출 (PyMuPDF → 한국어 정확)
            rows: list[list[str]] = []
            for i in range(len(y_group) - 1):
                row: list[str] = []
                for j in range(len(col_xs) - 1):
                    cell_rect = fitz.Rect(
                        col_xs[j], y_group[i], col_xs[j + 1], y_group[i + 1]
                    )
                    text = re.sub(r"\s+", " ", page.get_textbox(cell_rect)).strip()
                    row.append(text)
                if any(c.strip() for c in row):
                    rows.append(row)

            if not rows:
                continue

            markdown = self._rows_to_markdown(rows)
            bbox = BoundingBox(
                x0=float(col_xs[0]), y0=table_y0,
                x1=float(col_xs[-1]), y1=table_y1,
            )

            logger.debug(
                "벡터 테이블 감지",
                page=page_num,
                rows=len(rows),
                cols=len(col_xs) - 1,
                bbox=f"{bbox.x0:.0f},{bbox.y0:.0f}-{bbox.x1:.0f},{bbox.y1:.0f}",
            )

            result_blocks.append(LayoutBlock(
                document_id=document_id,
                page_number=page_num,
                block_type=BlockType.TABLE,
                bbox=bbox,
                text=markdown,
                confidence=1.0,
                sequence_in_page=0,
            ))

        return result_blocks

    @staticmethod
    def _rows_to_markdown(rows: list[list[str]]) -> str:
        if not rows:
            return ""
        n_cols = max(len(r) for r in rows)
        lines = []
        header = rows[0] + [""] * (n_cols - len(rows[0]))
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---"] * n_cols) + " |")
        for row in rows[1:]:
            row_pad = row + [""] * (n_cols - len(row))
            lines.append("| " + " | ".join(row_pad) + " |")
        return "\n".join(lines)

    # ── 스캔 페이지 분석 (EasyOCR) ────────────────────────────────────────

    def _analyze_scanned_page(
        self, page: fitz.Page, page_num: int, document_id: str
    ) -> list[LayoutBlock]:
        """스캔 페이지: EasyOCR로 한국어 텍스트 인식."""
        import cv2
        import numpy as np
        from src.ocr.pdf_extractor import PDFExtractor

        self._lazy_init_easyocr()

        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)
        img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        )
        if pix.n == 4:
            img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR)
        elif pix.n == 3:
            img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

        img_preprocessed = PDFExtractor.preprocess_scan_image(img_array)

        if self._easyocr_reader is None:
            logger.warning("EasyOCR 없음 - PyMuPDF fallback", page=page_num)
            return self._extract_text_blocks(page, page_num, document_id)

        try:
            results = self._easyocr_reader.readtext(img_preprocessed)
        except Exception as e:
            logger.warning("EasyOCR 실패", page=page_num, error=str(e))
            return self._extract_text_blocks(page, page_num, document_id)

        page_height = page.rect.height
        page_width = page.rect.width
        blocks: list[LayoutBlock] = []
        seq = 0

        for (bbox_pts, text, confidence) in results:
            text = re.sub(r"\s+", " ", text).strip()
            if not text:
                continue

            xs = [p[0] / 2.0 for p in bbox_pts]
            ys = [p[1] / 2.0 for p in bbox_pts]
            bbox = BoundingBox(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))
            block_type = self._infer_type_from_position(
                bbox.y0, bbox.x0, bbox.x1, bbox.y1, page_height, page_width
            )
            blocks.append(LayoutBlock(
                document_id=document_id,
                page_number=page_num,
                block_type=block_type,
                bbox=bbox,
                text=text,
                confidence=float(confidence),
                sequence_in_page=seq,
            ))
            seq += 1

        logger.debug("EasyOCR 페이지 처리 완료", page=page_num, blocks=len(blocks))
        return blocks

    def _infer_type_from_position(
        self,
        y0: float, x0: float, x1: float, y1: float,
        page_height: float, page_width: float,
    ) -> BlockType:
        if y0 < page_height * 0.08:
            return BlockType.HEADER
        if y1 > page_height * 0.92:
            return BlockType.FOOTER
        cx = (x0 + x1) / 2
        block_width = x1 - x0
        block_height = y1 - y0
        is_centered = abs(cx - page_width / 2) < page_width * 0.15
        is_compact = block_height > 18 and block_width < page_width * 0.6
        if is_centered and is_compact:
            return BlockType.TITLE
        return BlockType.TEXT

    # ── bbox 유틸 ─────────────────────────────────────────────────────────

    @staticmethod
    def _bbox_overlap_ratio(a: BoundingBox, b: BoundingBox) -> float:
        ix0 = max(a.x0, b.x0)
        iy0 = max(a.y0, b.y0)
        ix1 = min(a.x1, b.x1)
        iy1 = min(a.y1, b.y1)
        if ix1 <= ix0 or iy1 <= iy0:
            return 0.0
        inter = (ix1 - ix0) * (iy1 - iy0)
        area_a = (a.x1 - a.x0) * (a.y1 - a.y0)
        area_b = (b.x1 - b.x0) * (b.y1 - b.y0)
        smaller = min(area_a, area_b)
        return inter / smaller if smaller > 0 else 0.0

    # ── 블록 후처리 ───────────────────────────────────────────────────────

    def _postprocess_blocks(
        self, blocks: list[LayoutBlock], page_width: float
    ) -> list[LayoutBlock]:
        if self.block_merge_enabled:
            blocks = self._merge_nearby_text_blocks(blocks, self.block_merge_y_gap)
        blocks = self._sort_reading_order(blocks, page_width)
        for i, block in enumerate(blocks):
            block.sequence_in_page = i
        return blocks

    def _merge_nearby_text_blocks(
        self, blocks: list[LayoutBlock], y_gap: float
    ) -> list[LayoutBlock]:
        sorted_blocks = sorted(blocks, key=lambda b: (b.bbox.y0, b.bbox.x0))
        merged: list[LayoutBlock] = []
        prev: LayoutBlock | None = None

        for block in sorted_blocks:
            if (
                prev is not None
                and prev.block_type == BlockType.TEXT
                and block.block_type == BlockType.TEXT
                and block.bbox.y0 - prev.bbox.y1 <= y_gap
                and abs(block.bbox.x0 - prev.bbox.x0) < 50
            ):
                new_text = re.sub(
                    r"\s+",
                    " ",
                    (prev.text or "") + " " + (block.text or ""),
                ).strip()
                merged[-1] = LayoutBlock(
                    id=prev.id,
                    document_id=prev.document_id,
                    page_number=prev.page_number,
                    block_type=prev.block_type,
                    bbox=BoundingBox(
                        x0=prev.bbox.x0, y0=prev.bbox.y0,
                        x1=max(prev.bbox.x1, block.bbox.x1),
                        y1=block.bbox.y1,
                    ),
                    text=new_text,
                    confidence=min(prev.confidence, block.confidence),
                    sequence_in_page=prev.sequence_in_page,
                    font_size=prev.font_size,
                )
                prev = merged[-1]
            else:
                merged.append(block)
                prev = block

        return merged

    def _sort_reading_order(
        self, blocks: list[LayoutBlock], page_width: float
    ) -> list[LayoutBlock]:
        mid = page_width / 2
        left_col = [b for b in blocks if b.bbox.x1 <= mid * 1.1]
        right_col = [b for b in blocks if b.bbox.x0 >= mid * 0.9]

        if len(left_col) >= 3 and len(right_col) >= 3:
            return (
                sorted(left_col, key=lambda b: b.bbox.y0)
                + sorted(right_col, key=lambda b: b.bbox.y0)
            )
        return sorted(blocks, key=lambda b: (b.bbox.y0, b.bbox.x0))
