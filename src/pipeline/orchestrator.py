"""파이프라인 오케스트레이터 - 4단계 순차 실행 및 MongoDB 저장."""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from src.core.config import Settings
from src.core.models import (
    Document,
    DocumentStatus,
    ImageEntity,
    PipelineStage,
    PipelineState,
    Section,
    StageResult,
    StageStatus,
    TableEntity,
)
from src.db.repositories.document_repo import DocumentRepository
from src.db.repositories.image_repo import ImageRepository
from src.db.repositories.section_repo import SectionRepository
from src.db.repositories.table_repo import TableRepository
from src.db.repositories.toc_repo import TOCRepository
from src.llm.vision_client import VisionClient
from src.ocr.layout_analyzer import LayoutAnalyzer
from src.ocr.pdf_extractor import PDFExtractor
from src.pipeline.stage0_extract import run_stage0
from src.pipeline.stage1_layout import run_stage1
from src.pipeline.stage2_structure import run_stage2
from src.pipeline.stage3_vision import run_stage3
from src.pipeline.stage4_tags import run_stage4

logger = structlog.get_logger()

STAGE_ORDER = [
    PipelineStage.STAGE_0_EXTRACT,
    PipelineStage.STAGE_1_LAYOUT,
    PipelineStage.STAGE_2_STRUCTURE,
    PipelineStage.STAGE_3_VISION,
    PipelineStage.STAGE_4_TAGS,
]

TOTAL_STAGES = len(STAGE_ORDER)


class PipelineOrchestrator:
    """4단계 OCR 파이프라인 오케스트레이터."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.extractor = PDFExtractor(upload_dir=settings.upload_dir)
        self.layout_analyzer = LayoutAnalyzer(use_gpu=False)
        self.vision_client = VisionClient(
            api_key=settings.openai_api_key,
            model=settings.vision_model,
        )
        self.doc_repo = DocumentRepository()
        self.toc_repo = TOCRepository()
        self.section_repo = SectionRepository()
        self.table_repo = TableRepository()
        self.image_repo = ImageRepository()

    async def run(self, document: Document) -> PipelineState:
        """전체 파이프라인 실행."""
        document_id = document.id
        pdf_path = Path(document.file_path)

        logger.info("파이프라인 시작", document_id=document_id)
        pipeline_state = self._init_state(document_id)

        # 처리 중 상태 업데이트
        await self.doc_repo.update_status(
            document_id, DocumentStatus.PROCESSING, PipelineStage.STAGE_0_EXTRACT
        )

        try:
            # ── Stage 0: PDF 추출 ──────────────────────────────────────────
            pipeline_state = self._mark_running(pipeline_state, PipelineStage.STAGE_0_EXTRACT)
            stage0 = await run_stage0(document_id, pdf_path, self.extractor)
            pipeline_state = self._mark_completed(
                pipeline_state, PipelineStage.STAGE_0_EXTRACT,
                stage0.duration_seconds, stage0.summary
            )

            # 문서 메타데이터 업데이트
            await self.doc_repo.update_metadata(document_id, {
                "page_count": stage0.result.page_count,
                "detected_language": stage0.result.detected_language,
                "is_scanned": stage0.result.is_scanned,
                "file_size_bytes": pdf_path.stat().st_size,
                "title": stage0.result.metadata.get("title"),
                "author": stage0.result.metadata.get("author"),
            })

            # ── Stage 1: 레이아웃 분석 ──────────────────────────────────────
            await self.doc_repo.update_status(
                document_id, DocumentStatus.PROCESSING, PipelineStage.STAGE_1_LAYOUT
            )
            pipeline_state = self._mark_running(pipeline_state, PipelineStage.STAGE_1_LAYOUT)
            stage1 = await run_stage1(stage0, pdf_path, self.layout_analyzer)
            pipeline_state = self._mark_completed(
                pipeline_state, PipelineStage.STAGE_1_LAYOUT,
                stage1.duration_seconds, stage1.summary
            )

            # ── Stage 2: 구조화 ─────────────────────────────────────────────
            await self.doc_repo.update_status(
                document_id, DocumentStatus.PROCESSING, PipelineStage.STAGE_2_STRUCTURE
            )
            pipeline_state = self._mark_running(pipeline_state, PipelineStage.STAGE_2_STRUCTURE)
            stage2 = run_stage2(stage0, stage1)
            pipeline_state = self._mark_completed(
                pipeline_state, PipelineStage.STAGE_2_STRUCTURE,
                stage2.duration_seconds, stage2.summary
            )

            # Stage 2 결과 MongoDB 저장
            await self._save_stage2_results(
                stage2.toc, stage2.sections, stage2.tables, stage2.images
            )

            # ── Stage 3: 이미지 캡셔닝 ──────────────────────────────────────
            await self.doc_repo.update_status(
                document_id, DocumentStatus.PROCESSING, PipelineStage.STAGE_3_VISION
            )
            pipeline_state = self._mark_running(pipeline_state, PipelineStage.STAGE_3_VISION)
            stage3 = await run_stage3(
                stage2,
                self.vision_client,
                enabled=self.settings.enable_vision_captioning,
            )
            pipeline_state = self._mark_completed(
                pipeline_state, PipelineStage.STAGE_3_VISION,
                stage3.duration_seconds, stage3.summary
            )

            # Stage 3 이미지 캡션 업데이트
            for img in stage3.images:
                if img.vision_processed:
                    await self.image_repo.update_vision_description(
                        img.id, img.vision_description or ""
                    )

            # ── Stage 4: 태그/요약 ───────────────────────────────────────────
            await self.doc_repo.update_status(
                document_id, DocumentStatus.PROCESSING, PipelineStage.STAGE_4_TAGS
            )
            pipeline_state = self._mark_running(pipeline_state, PipelineStage.STAGE_4_TAGS)
            stage4 = await run_stage4(
                stage2,
                stage3,
                api_key=self.settings.openai_api_key,
                model=self.settings.llm_model,
                enabled=self.settings.enable_tag_generation,
            )
            pipeline_state = self._mark_completed(
                pipeline_state, PipelineStage.STAGE_4_TAGS,
                stage4.duration_seconds, stage4.summary
            )

            # Stage 4 태그/요약 업데이트
            for section in stage4.sections:
                if section.tags or section.summary:
                    await self.section_repo.update_tags(
                        section.id, section.tags, section.summary
                    )

            # ── 완료 ────────────────────────────────────────────────────────
            pipeline_state.completed_at = datetime.utcnow()
            pipeline_state.total_duration_seconds = sum(
                r.duration_seconds or 0 for r in pipeline_state.stages.values()
            )

            await self.doc_repo.update_status(document_id, DocumentStatus.COMPLETED)
            logger.info(
                "파이프라인 완료",
                document_id=document_id,
                duration=f"{pipeline_state.total_duration_seconds:.1f}s",
            )

        except Exception as e:
            logger.exception("파이프라인 실패", document_id=document_id, error=str(e))
            pipeline_state = self._mark_failed(
                pipeline_state,
                pipeline_state.current_stage or PipelineStage.STAGE_0_EXTRACT,
                str(e),
            )
            await self.doc_repo.update_status(
                document_id, DocumentStatus.FAILED, error_message=str(e)
            )

        return pipeline_state

    async def _save_stage2_results(
        self,
        toc,
        sections: list[Section],
        tables: list[TableEntity],
        images: list[ImageEntity],
    ) -> None:
        await self.toc_repo.upsert_many(toc.nodes)
        for section in sections:
            await self.section_repo.upsert(section)
        for table in tables:
            await self.table_repo.upsert(table)
        for image in images:
            await self.image_repo.upsert(image)

    # ── State helpers ─────────────────────────────────────────────────────

    def _init_state(self, document_id: str) -> PipelineState:
        stages = {
            stage.value: StageResult(stage=stage, status=StageStatus.PENDING)
            for stage in STAGE_ORDER
        }
        return PipelineState(document_id=document_id, stages=stages)

    def _mark_running(self, state: PipelineState, stage: PipelineStage) -> PipelineState:
        state.current_stage = stage
        state.stages[stage.value] = StageResult(
            stage=stage,
            status=StageStatus.RUNNING,
            started_at=datetime.utcnow(),
        )
        state.updated_at = datetime.utcnow()
        return state

    def _mark_completed(
        self,
        state: PipelineState,
        stage: PipelineStage,
        duration: float,
        output_summary: dict,
    ) -> PipelineState:
        now = datetime.utcnow()
        state.stages[stage.value] = StageResult(
            stage=stage,
            status=StageStatus.COMPLETED,
            started_at=state.stages[stage.value].started_at,
            completed_at=now,
            duration_seconds=duration,
            output_summary=output_summary,
        )
        state.last_completed_stage = stage
        state.updated_at = now
        return state

    def _mark_failed(
        self, state: PipelineState, stage: PipelineStage, error: str
    ) -> PipelineState:
        now = datetime.utcnow()
        existing = state.stages.get(stage.value)
        state.stages[stage.value] = StageResult(
            stage=stage,
            status=StageStatus.FAILED,
            started_at=existing.started_at if existing else now,
            completed_at=now,
            error_message=error,
        )
        state.updated_at = now
        return state

    def get_progress_percent(self, state: PipelineState) -> float:
        completed = sum(
            1 for r in state.stages.values()
            if r.status == StageStatus.COMPLETED
        )
        return round(completed / TOTAL_STAGES * 100, 1)
