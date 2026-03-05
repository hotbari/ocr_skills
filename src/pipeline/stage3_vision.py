"""Stage 3: 이미지 캡셔닝 (gpt-4o Vision).

각 ImageEntity의 image_path를 gpt-4o로 분석하여
vision_description을 채웁니다.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import structlog

from src.core.models import ImageEntity
from src.llm.vision_client import VisionClient
from src.pipeline.stage2_structure import Stage2Output

logger = structlog.get_logger()

MAX_CONCURRENT = 3  # 동시 Vision API 호출 수


@dataclass
class Stage3Output:
    document_id: str
    images: list[ImageEntity]
    processed_count: int
    skipped_count: int
    duration_seconds: float
    summary: dict[str, Any]


async def run_stage3(
    stage2: Stage2Output,
    vision_client: VisionClient,
    enabled: bool = True,
) -> Stage3Output:
    """Stage 3 실행: 이미지 캡셔닝."""
    logger.info("Stage 3 시작", document_id=stage2.document_id, enabled=enabled)
    t0 = time.monotonic()

    images = stage2.images
    processed = 0
    skipped = 0

    if not enabled:
        logger.info("Stage 3 비활성화 - 건너뜀")
        skipped = len(images)
    else:
        sem = asyncio.Semaphore(MAX_CONCURRENT)

        async def process_image(img: ImageEntity) -> None:
            nonlocal processed, skipped
            if not img.image_path:
                skipped += 1
                return
            async with sem:
                description = await vision_client.caption_image(img.image_path)
                if description:
                    img.vision_description = description
                    img.vision_processed = True
                    processed += 1
                    logger.debug("이미지 캡셔닝 완료", image_id=img.id, page=img.page_number)
                else:
                    skipped += 1

        await asyncio.gather(*[process_image(img) for img in images])

    duration = time.monotonic() - t0
    summary = {
        "total_images": len(images),
        "processed": processed,
        "skipped": skipped,
    }
    logger.info("Stage 3 완료", duration=f"{duration:.2f}s", **summary)

    return Stage3Output(
        document_id=stage2.document_id,
        images=images,
        processed_count=processed,
        skipped_count=skipped,
        duration_seconds=duration,
        summary=summary,
    )
