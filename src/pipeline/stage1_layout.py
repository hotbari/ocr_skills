"""Stage 1: 레이아웃 분석 (PP-Structure / PyMuPDF fallback)."""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from src.ocr.layout_analyzer import LayoutAnalysisResult, LayoutAnalyzer
from src.pipeline.stage0_extract import Stage0Output

logger = structlog.get_logger()


@dataclass
class Stage1Output:
    document_id: str
    layout: LayoutAnalysisResult
    duration_seconds: float
    summary: dict[str, Any]


async def run_stage1(
    stage0: Stage0Output,
    pdf_path: Path,
    analyzer: LayoutAnalyzer,
) -> Stage1Output:
    """Stage 1 실행: 페이지별 레이아웃 블록 감지."""
    logger.info("Stage 1 시작", document_id=stage0.document_id)
    t0 = time.monotonic()

    layout = await analyzer.analyze(
        pdf_path=pdf_path,
        document_id=stage0.document_id,
        is_scanned=stage0.result.is_scanned,
    )

    # 블록 타입별 통계
    type_counts: dict[str, int] = {}
    for blocks in layout.blocks_by_page.values():
        for block in blocks:
            bt = block.block_type if isinstance(block.block_type, str) else block.block_type.value
            type_counts[bt] = type_counts.get(bt, 0) + 1

    duration = time.monotonic() - t0
    summary = {
        "total_blocks": layout.total_blocks,
        "page_count": layout.page_count,
        "block_type_counts": type_counts,
    }
    logger.info("Stage 1 완료", duration=f"{duration:.2f}s", **summary)

    return Stage1Output(
        document_id=stage0.document_id,
        layout=layout,
        duration_seconds=duration,
        summary=summary,
    )
