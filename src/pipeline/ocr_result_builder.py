"""Stage2~4 출력을 PRD 형식 OCRResult로 변환."""

from pathlib import Path
from typing import Optional

from src.core.ocr_result import (
    OCRResult,
    OCRResultImage,
    OCRResultPage,
    OCRResultSection,
    OCRResultTable,
)
from src.pipeline.stage2_structure import Stage2Output
from src.pipeline.stage3_vision import Stage3Output
from src.pipeline.stage4_tags import Stage4Output


def build_ocr_result(
    document_id: str,
    stage2: Stage2Output,
    stage3: Optional[Stage3Output] = None,
    stage4: Optional[Stage4Output] = None,
) -> OCRResult:
    """파이프라인 출력을 PRD 형식 OCRResult로 변환."""

    # ── Stage 3: image_id → vision_description 매핑 ─────────────────
    vision_map: dict[str, str] = {}
    if stage3:
        for img in stage3.images:
            if img.vision_description:
                vision_map[img.id] = img.vision_description

    # ── Stage 4: section heading → (tags, summary) 매핑 ────────────
    tag_map: dict[str, list[str]] = {}
    summary_map: dict[str, str] = {}
    if stage4:
        for s in stage4.sections:
            key = s.heading or ""
            tag_map[key] = s.tags or []
            if s.summary:
                summary_map[key] = s.summary

    # ── 페이지 집합 수집 ──────────────────────────────────────────────
    all_pages: set[int] = set()
    for s in stage2.sections:
        for p in range(s.page_start, s.page_end + 1):
            all_pages.add(p)
    for t in stage2.tables:
        all_pages.add(t.page_number)
    for img in stage2.images:
        all_pages.add(img.page_number)

    # ── 페이지별 빌드 ─────────────────────────────────────────────────
    pages: list[OCRResultPage] = []
    for page_num in sorted(all_pages):
        # 섹션 (page_start 기준으로 할당)
        sections_on_page = [
            s for s in stage2.sections if s.page_start == page_num
        ]
        # 테이블
        tables_on_page = [
            t for t in stage2.tables if t.page_number == page_num
        ]
        # 이미지
        images_on_page = [
            img for img in stage2.images if img.page_number == page_num
        ]

        # 페이지 내 sequence_id 부여 (섹션 seq → 이미지 → 테이블 순)
        seq = 0
        ocr_sections: list[OCRResultSection] = []
        for s in sorted(sections_on_page, key=lambda x: x.sequence_number):
            tags = tag_map.get(s.heading or "", [])
            keyword = ", ".join(tags) if tags else None
            ocr_sections.append(OCRResultSection(
                section_id=f"SEC-{s.sequence_number:04d}",
                title=s.heading,
                content=s.content,
                page_number=page_num,
                keyword=keyword,
                sequence_id=seq,
            ))
            seq += 1

        ocr_images: list[OCRResultImage] = []
        for img in sorted(images_on_page, key=lambda x: x.sequence_in_page):
            img_path = img.image_path or ""
            ext = Path(img_path).suffix.lstrip(".") if img_path else "png"
            name = Path(img_path).name if img_path else f"image_p{page_num}_{img.sequence_in_page}"
            vision_desc = vision_map.get(img.id)
            ocr_images.append(OCRResultImage(
                name=name,
                description=vision_desc or img.caption,
                ext=ext or "png",
                image_url=img_path,
                tag=list(img.caption.split() if img.caption else []),
                type="image",
                sequence_id=seq,
            ))
            seq += 1

        ocr_tables: list[OCRResultTable] = []
        for t in sorted(tables_on_page, key=lambda x: x.sequence_in_page):
            name = t.caption or f"테이블 p.{page_num}-{t.sequence_in_page + 1}"
            ocr_tables.append(OCRResultTable(
                name=name,
                table_md=t.markdown or "",
                sequence_id=seq,
            ))
            seq += 1

        pages.append(OCRResultPage(
            page_num=page_num,
            sections=ocr_sections,
            images=ocr_images,
            table=ocr_tables,
        ))

    return OCRResult(
        ref_document_id=document_id,
        page=pages,
    )
