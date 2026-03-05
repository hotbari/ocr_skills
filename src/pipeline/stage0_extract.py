"""Stage 0: PDF 추출 (PyMuPDF)."""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from src.core.models import Language
from src.ocr.pdf_extractor import ExtractionResult, PDFExtractor

logger = structlog.get_logger()


@dataclass
class Stage0Output:
    document_id: str
    result: ExtractionResult
    duration_seconds: float
    summary: dict[str, Any]


async def run_stage0(
    document_id: str,
    pdf_path: Path,
    extractor: PDFExtractor,
) -> Stage0Output:
    """Stage 0 실행: PDF에서 텍스트/이미지/테이블 추출."""
    logger.info("Stage 0 시작", document_id=document_id)
    t0 = time.monotonic()

    result = await extractor.extract(pdf_path, document_id)

    duration = time.monotonic() - t0
    summary = {
        "page_count": result.page_count,
        "text_length": len(result.raw_text),
        "image_count": len(result.images),
        "table_count": len(result.tables),
        "language": result.detected_language.value if hasattr(result.detected_language, "value") else result.detected_language,
        "is_scanned": result.is_scanned,
    }
    logger.info("Stage 0 완료", duration=f"{duration:.2f}s", **summary)

    return Stage0Output(
        document_id=document_id,
        result=result,
        duration_seconds=duration,
        summary=summary,
    )
