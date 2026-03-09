"""Stage 2: 구조화 - 레이아웃 블록 → 섹션/테이블/이미지 엔티티.

LLM 없이 순수 로직으로 처리합니다.
- TITLE 블록 → 섹션 헤딩 (폰트 크기/위치로 레벨 추정)
- TEXT 블록 → 섹션 본문 누적
- TABLE 블록 → TableEntity 생성
- FIGURE 블록 → ImageEntity 생성 (Stage 0 이미지와 매칭)
"""

import re
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from src.core.models import (
    BlockType,
    BoundingBox,
    ImageEntity,
    LayoutBlock,
    Section,
    TableCell,
    TableEntity,
    TableStructure,
    TOCNode,
    TOCStructure,
)
from src.ocr.pdf_extractor import RawImage, RawTable
from src.pipeline.stage0_extract import Stage0Output
from src.pipeline.stage1_layout import Stage1Output

logger = structlog.get_logger()


def _collect_title_font_sizes(stage1: "Stage1Output") -> list[float]:
    """모든 TITLE 블록의 font_size를 수집해 내림차순으로 반환."""
    sizes = []
    for blocks in stage1.layout.blocks_by_page.values():
        for block in blocks:
            bt = block.block_type
            if not isinstance(bt, BlockType):
                bt = BlockType(bt)
            if bt == BlockType.TITLE and block.font_size:
                sizes.append(block.font_size)
    return sorted(set(sizes), reverse=True)


@dataclass
class Stage2Output:
    document_id: str
    toc: TOCStructure
    sections: list[Section]
    tables: list[TableEntity]
    images: list[ImageEntity]
    duration_seconds: float
    summary: dict[str, Any]


def run_stage2(stage0: Stage0Output, stage1: Stage1Output) -> Stage2Output:
    """Stage 2 실행: 레이아웃 블록을 구조화된 섹션/테이블/이미지로 변환."""
    logger.info("Stage 2 시작", document_id=stage0.document_id)
    t0 = time.monotonic()

    document_id = stage0.document_id

    # TITLE 블록의 폰트 크기 수집 → 레벨 임계값 계산
    title_font_sizes = _collect_title_font_sizes(stage1)
    builder = StructureBuilder(document_id, title_font_sizes=title_font_sizes)

    # 전체 페이지를 순서대로 처리
    all_pages = sorted(stage1.layout.blocks_by_page.keys())
    for page_num in all_pages:
        blocks = stage1.layout.blocks_by_page[page_num]
        # sequence_in_page 기준 정렬 (위→아래)
        blocks_sorted = sorted(blocks, key=lambda b: (b.bbox.y0, b.bbox.x0))
        for block in blocks_sorted:
            builder.process_block(block)

    # Stage 0에서 추출된 테이블/이미지를 보완
    builder.merge_stage0_tables(stage0.result.tables)
    builder.merge_stage0_images(stage0.result.images)

    sections = builder.finalize_sections()
    toc = builder.build_toc()
    tables = builder.tables
    images = builder.images

    duration = time.monotonic() - t0
    summary = {
        "sections": len(sections),
        "toc_nodes": len(toc.nodes),
        "toc_l1": toc.total_l1,
        "toc_l2": toc.total_l2,
        "toc_l3": toc.total_l3,
        "tables": len(tables),
        "images": len(images),
    }
    logger.info("Stage 2 완료", duration=f"{duration:.2f}s", **summary)

    return Stage2Output(
        document_id=document_id,
        toc=toc,
        sections=sections,
        tables=tables,
        images=images,
        duration_seconds=duration,
        summary=summary,
    )


class StructureBuilder:
    """블록 스트림을 섹션 트리로 조립."""

    def __init__(self, document_id: str, title_font_sizes: list[float] | None = None):
        self.document_id = document_id
        self.sections: list[Section] = []
        self.tables: list[TableEntity] = []
        self.images: list[ImageEntity] = []

        self._current_section: Section | None = None
        self._section_seq = 0
        self._table_seq: dict[int, int] = {}   # page → seq
        self._image_seq: dict[int, int] = {}   # page → seq
        self._pending_caption: str | None = None  # FIGURE/TABLE_CAPTION 임시 저장
        self._last_block_type: BlockType | None = None

        # 폰트 크기 기반 레벨 임계값: 상위 크기순 [L1 min, L2 min]
        sizes = title_font_sizes or []
        if len(sizes) >= 3:
            # 상위 크기 → L1, 중간 → L2, 나머지 → L3
            self._l1_min = sizes[0]          # 가장 큰 폰트
            self._l2_min = sizes[len(sizes) // 2]  # 중간 폰트
        elif len(sizes) == 2:
            self._l1_min = sizes[0]
            self._l2_min = sizes[1]
        else:
            self._l1_min = None
            self._l2_min = None

    def process_block(self, block: LayoutBlock) -> None:
        bt = block.block_type if isinstance(block.block_type, str) else block.block_type.value
        bt = BlockType(bt) if not isinstance(bt, BlockType) else bt

        if bt in (BlockType.HEADER, BlockType.FOOTER, BlockType.REFERENCE):
            return  # 무시

        if bt == BlockType.TITLE:
            self._start_new_section(block)

        elif bt == BlockType.TEXT:
            text = (block.text or "").strip()
            if not text:
                return
            if self._current_section is None:
                self._ensure_default_section(block.page_number)
            self._current_section.content += ("\n\n" if self._current_section.content else "") + text

        elif bt == BlockType.TABLE:
            self._create_table_from_block(block)

        elif bt == BlockType.FIGURE:
            self._create_image_from_block(block)

        elif bt in (BlockType.FIGURE_CAPTION, BlockType.TABLE_CAPTION):
            self._pending_caption = (block.text or "").strip()
            # 바로 직전 엔티티에 캡션 적용
            self._apply_pending_caption(bt)

        elif bt == BlockType.EQUATION:
            if self._current_section:
                eq = (block.text or "").strip()
                if eq:
                    self._current_section.content += f"\n\n[수식] {eq}"

        self._last_block_type = bt

    def _start_new_section(self, block: LayoutBlock) -> None:
        heading = (block.text or "").strip()
        if not heading:
            return

        level = self._infer_heading_level(heading, block.bbox, font_size=block.font_size)
        self._section_seq += 1

        section = Section(
            document_id=self.document_id,
            heading=heading,
            heading_level=level,
            content="",
            page_start=block.page_number,
            page_end=block.page_number,
            sequence_number=self._section_seq,
        )
        self.sections.append(section)
        self._current_section = section

    def _ensure_default_section(self, page_number: int) -> None:
        """섹션이 없으면 기본 섹션 생성."""
        self._section_seq += 1
        section = Section(
            document_id=self.document_id,
            heading=None,
            heading_level=1,
            content="",
            page_start=page_number,
            page_end=page_number,
            sequence_number=self._section_seq,
        )
        self.sections.append(section)
        self._current_section = section

    def _infer_heading_level(self, text: str, bbox: BoundingBox, font_size: float | None = None) -> int:
        """헤딩 레벨 추정 (폰트 크기 우선, 텍스트 패턴 보조).

        폰트 크기 정보가 있으면 문서 내 상대적 크기로 레벨 결정.
        없으면 텍스트 패턴/길이로 추정.
        """
        # 패턴 기반 우선 (숫자 넘버링)
        if re.match(r"^(제\s*\d+\s*[장편절]|chapter\s+\d+)", text, re.IGNORECASE):
            return 1
        if re.match(r"^\d+\.\d+\.\d+", text):
            return 3
        if re.match(r"^\d+\.\d+\s", text):
            return 2
        if re.match(r"^\d+\.\s", text):
            return 1

        # 폰트 크기 기반
        if font_size and self._l1_min and self._l2_min:
            if font_size >= self._l1_min:
                return 1
            if font_size >= self._l2_min:
                return 2
            return 3

        # fallback: 첫 페이지 제목은 L1, 이후는 텍스트 길이 기반
        if bbox.y0 < 100 and len(text) > 10:  # 페이지 상단 큰 제목
            return 1
        if len(text) <= 15:
            return 1
        if len(text) <= 30:
            return 2
        return 3

    def _create_table_from_block(self, block: LayoutBlock) -> None:
        seq = self._table_seq.get(block.page_number, 0)
        self._table_seq[block.page_number] = seq + 1

        table = TableEntity(
            document_id=self.document_id,
            section_id=self._current_section.id if self._current_section else None,
            page_number=block.page_number,
            sequence_in_page=seq,
            bbox=block.bbox,
            markdown=block.text or "",
            caption=self._pending_caption,
        )
        self._pending_caption = None
        self.tables.append(table)

        if self._current_section:
            self._current_section.entity_ids.append(table.id)
            self._current_section.page_end = max(
                self._current_section.page_end, block.page_number
            )

    def _create_image_from_block(self, block: LayoutBlock) -> None:
        seq = self._image_seq.get(block.page_number, 0)
        self._image_seq[block.page_number] = seq + 1

        image = ImageEntity(
            document_id=self.document_id,
            section_id=self._current_section.id if self._current_section else None,
            page_number=block.page_number,
            sequence_in_page=seq,
            bbox=block.bbox,
            caption=self._pending_caption,
            surrounding_context=self._get_surrounding_context(),
        )
        self._pending_caption = None
        self.images.append(image)

        if self._current_section:
            self._current_section.entity_ids.append(image.id)
            self._current_section.page_end = max(
                self._current_section.page_end, block.page_number
            )

    def _apply_pending_caption(self, caption_type: BlockType) -> None:
        caption = self._pending_caption
        if not caption:
            return
        if caption_type == BlockType.TABLE_CAPTION and self.tables:
            self.tables[-1].caption = caption
            self._pending_caption = None
        elif caption_type == BlockType.FIGURE_CAPTION and self.images:
            self.images[-1].caption = caption
            self._pending_caption = None

    def _get_surrounding_context(self) -> str | None:
        """현재 섹션의 마지막 200자를 주변 컨텍스트로 반환."""
        if self._current_section and self._current_section.content:
            return self._current_section.content[-200:]
        return None

    def merge_stage0_tables(self, raw_tables: list[RawTable]) -> None:
        """Stage 0 PyMuPDF 테이블 데이터와 병합 (레이아웃 감지된 것과 매칭)."""
        for raw in raw_tables:
            # 이미 같은 페이지에 레이아웃 감지된 테이블이 있으면 구조 보완
            matched = self._find_matching_table(raw.page_number, raw.bbox)
            if matched:
                if not matched.structure:
                    matched.structure = self._build_table_structure(raw.rows)
                if not matched.markdown and raw.markdown:
                    matched.markdown = raw.markdown
            else:
                # 새 테이블 추가 (레이아웃 미감지)
                seq = self._table_seq.get(raw.page_number, 0)
                self._table_seq[raw.page_number] = seq + 1
                table = TableEntity(
                    document_id=self.document_id,
                    page_number=raw.page_number,
                    sequence_in_page=seq,
                    bbox=raw.bbox,
                    structure=self._build_table_structure(raw.rows),
                    markdown=raw.markdown,
                )
                self.tables.append(table)

    def merge_stage0_images(self, raw_images: list[RawImage]) -> None:
        """Stage 0 PyMuPDF 이미지와 병합 (파일 경로 보완)."""
        for raw in raw_images:
            matched = self._find_matching_image(raw.page_number, raw.bbox)
            if matched:
                if not matched.image_path:
                    matched.image_path = raw.image_path
            else:
                seq = self._image_seq.get(raw.page_number, 0)
                self._image_seq[raw.page_number] = seq + 1
                image = ImageEntity(
                    document_id=self.document_id,
                    page_number=raw.page_number,
                    sequence_in_page=seq,
                    bbox=raw.bbox,
                    image_path=raw.image_path,
                )
                self.images.append(image)

    def _find_matching_table(self, page: int, bbox: BoundingBox) -> TableEntity | None:
        for t in self.tables:
            if t.page_number == page and t.bbox and self._bbox_overlap(t.bbox, bbox):
                return t
        return None

    def _find_matching_image(self, page: int, bbox: BoundingBox) -> ImageEntity | None:
        for img in self.images:
            if img.page_number == page and img.bbox and self._bbox_overlap(img.bbox, bbox):
                return img
        return None

    def _bbox_overlap(self, a: BoundingBox, b: BoundingBox, threshold: float = 0.3) -> bool:
        """두 바운딩 박스의 겹침 여부 확인."""
        ix0 = max(a.x0, b.x0)
        iy0 = max(a.y0, b.y0)
        ix1 = min(a.x1, b.x1)
        iy1 = min(a.y1, b.y1)
        if ix1 <= ix0 or iy1 <= iy0:
            return False
        intersection = (ix1 - ix0) * (iy1 - iy0)
        area_a = (a.x1 - a.x0) * (a.y1 - a.y0)
        area_b = (b.x1 - b.x0) * (b.y1 - b.y0)
        smaller = min(area_a, area_b)
        return smaller > 0 and (intersection / smaller) > threshold

    def _build_table_structure(self, rows: list[list[str]]) -> TableStructure:
        if not rows:
            return TableStructure(rows=0, cols=0)
        headers = rows[0]
        cells = []
        for r_idx, row in enumerate(rows):
            for c_idx, cell_text in enumerate(row):
                cells.append(TableCell(
                    row=r_idx,
                    col=c_idx,
                    content=cell_text,
                    is_header=(r_idx == 0),
                ))
        return TableStructure(
            rows=len(rows),
            cols=len(headers),
            headers=headers,
            cells=cells,
        )

    def finalize_sections(self) -> list[Section]:
        """섹션 계층 구조 설정 (parent_id / children_ids)."""
        self._build_hierarchy()
        return self.sections

    def build_toc(self) -> TOCStructure:
        """섹션 목록으로 TOC 트리 생성.

        헤딩이 있는 섹션만 TOC 노드로 등록하고,
        Section ↔ TOCNode를 양방향으로 연결합니다.
        """
        nodes: list[TOCNode] = []
        # section_id → TOCNode 매핑 (entity_ids 복사용)
        section_to_toc: dict[str, TOCNode] = {}

        seq = 0
        for section in self.sections:
            if not section.heading:
                continue  # 제목 없는 섹션은 TOC 미포함

            toc_node = TOCNode(
                document_id=self.document_id,
                level=section.heading_level,
                title=section.heading,
                page_start=section.page_start,
                page_end=section.page_end,
                sequence_number=seq,
                parent_id=None,       # 아래에서 설정
                children_ids=[],
                section_id=section.id,
                entity_ids=list(section.entity_ids),
            )
            nodes.append(toc_node)
            section_to_toc[section.id] = toc_node
            # 섹션에 toc_node_id 역참조
            section.toc_node_id = toc_node.id
            seq += 1

        # 부모-자식 관계 설정 (섹션 hierarchy와 동일 로직)
        stack: list[TOCNode] = []
        for node in nodes:
            while stack and stack[-1].level >= node.level:
                stack.pop()
            if stack:
                node.parent_id = stack[-1].id
                stack[-1].children_ids.append(node.id)
            stack.append(node)

        total_l1 = sum(1 for n in nodes if n.level == 1)
        total_l2 = sum(1 for n in nodes if n.level == 2)
        total_l3 = sum(1 for n in nodes if n.level >= 3)

        return TOCStructure(
            document_id=self.document_id,
            nodes=nodes,
            total_l1=total_l1,
            total_l2=total_l2,
            total_l3=total_l3,
        )

    def _build_hierarchy(self) -> None:
        """레벨 기반으로 부모-자식 관계 설정."""
        stack: list[Section] = []

        for section in self.sections:
            level = section.heading_level

            while stack and stack[-1].heading_level >= level:
                stack.pop()

            if stack:
                parent = stack[-1]
                section.parent_id = parent.id
                parent.children_ids.append(section.id)

            stack.append(section)
