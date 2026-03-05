"""Stage 4: 태그/요약 생성 (LLM - 선택적).

각 섹션에 대해 키워드 태그와 요약을 생성합니다.
섹션 본문이 짧은 경우 건너뜁니다.
"""

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

import structlog
from openai import AsyncOpenAI

from src.core.models import Section
from src.pipeline.stage2_structure import Stage2Output
from src.pipeline.stage3_vision import Stage3Output

logger = structlog.get_logger()

MIN_CONTENT_LENGTH = 100  # 태그 생성 최소 글자 수
MAX_CONCURRENT = 5
TAGS_PROMPT = """다음 텍스트를 분석하여 JSON으로 응답하세요.

텍스트:
{content}

응답 형식:
{{
  "tags": ["태그1", "태그2", "태그3"],
  "summary": "1-2문장 요약"
}}

규칙:
- tags: 핵심 키워드 3-7개 (명사 중심)
- summary: 핵심 내용을 1-2문장으로 요약
- 한국어로 응답"""


@dataclass
class Stage4Output:
    document_id: str
    sections: list[Section]
    processed_count: int
    skipped_count: int
    duration_seconds: float
    summary: dict[str, Any]


async def run_stage4(
    stage2: Stage2Output,
    stage3: Stage3Output,
    api_key: str,
    model: str = "gpt-4o-mini",
    enabled: bool = True,
) -> Stage4Output:
    """Stage 4 실행: 섹션별 태그/요약 생성."""
    logger.info("Stage 4 시작", document_id=stage2.document_id, enabled=enabled)
    t0 = time.monotonic()

    sections = stage2.sections
    processed = 0
    skipped = 0

    if not enabled:
        logger.info("Stage 4 비활성화 - 건너뜀")
        skipped = len(sections)
    else:
        client = AsyncOpenAI(api_key=api_key)
        sem = asyncio.Semaphore(MAX_CONCURRENT)

        async def process_section(section: Section) -> None:
            nonlocal processed, skipped
            content = section.content.strip()
            if len(content) < MIN_CONTENT_LENGTH:
                skipped += 1
                return

            async with sem:
                result = await _generate_tags(client, model, content)
                if result:
                    section.tags = result.get("tags", [])
                    section.summary = result.get("summary")
                    processed += 1
                else:
                    skipped += 1

        await asyncio.gather(*[process_section(s) for s in sections])

    duration = time.monotonic() - t0
    summary = {
        "total_sections": len(sections),
        "processed": processed,
        "skipped": skipped,
    }
    logger.info("Stage 4 완료", duration=f"{duration:.2f}s", **summary)

    return Stage4Output(
        document_id=stage2.document_id,
        sections=sections,
        processed_count=processed,
        skipped_count=skipped,
        duration_seconds=duration,
        summary=summary,
    )


async def _generate_tags(
    client: AsyncOpenAI, model: str, content: str
) -> dict | None:
    """LLM으로 태그와 요약 생성."""
    # 너무 긴 내용은 앞부분만 사용
    truncated = content[:2000]
    prompt = TAGS_PROMPT.format(content=truncated)

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=300,
            temperature=0.3,
        )
        raw = response.choices[0].message.content or ""
        return json.loads(raw)
    except Exception as e:
        logger.warning("태그 생성 실패", error=str(e))
        return None
