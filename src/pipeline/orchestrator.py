"""Pipeline orchestrator - coordinates all stages."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import structlog

from src.core.config import Settings, get_settings
from src.core.exceptions import PipelineError, StageExecutionError
from src.core.models import (DocumentStatus, PipelineStage, PipelineState,
                             StageStatus)
from src.db.repositories.chunk_repo import ChunkRepository
from src.db.repositories.document_repo import DocumentRepository
from src.db.repositories.entity_repo import EntityRepository
from src.db.repositories.toc_repo import TOCRepository
from src.embeddings.openai_provider import OpenAIEmbeddingProvider
from src.llm.openai_client import OpenAIClient
from src.llm.vision_client import VisionClient
from src.ocr.extractor import PDFExtractor
from src.pipeline.stage0_extraction import Stage0Extraction, Stage0Input
from src.pipeline.stage1_segmentation import Stage1Input, Stage1Segmentation
from src.pipeline.stage2_headings import Stage2Headings, Stage2Input
from src.pipeline.stage3_toc_alignment import Stage3Input, Stage3TOCAlignment
from src.pipeline.stage4_toc_normalization import (Stage4Input,
                                                   Stage4TOCNormalization)
from src.pipeline.stage5_chunking import Stage5Chunking, Stage5Input
from src.pipeline.stage5b_entities import Stage5bEntities, Stage5bInput
from src.pipeline.stage6_vision import Stage6Input, Stage6Vision
from src.pipeline.stage7_embedding import Stage7Embedding, Stage7Input
from src.pipeline.state_manager import PipelineStateManager
from src.prompts.loader import PromptLoader

logger = structlog.get_logger()


@dataclass
class PipelineResult:
    """Result of pipeline execution."""

    document_id: str
    success: bool
    stages_completed: list[str]
    total_retrieval_chunks: int
    total_generation_chunks: int
    total_entities: int
    duration_seconds: float
    error: Optional[str] = None


class PipelineOrchestrator:
    """Orchestrates the 8-stage document processing pipeline."""

    STAGE_ORDER = [
        PipelineStage.STAGE_0_EXTRACTION,
        PipelineStage.STAGE_1_SEGMENTATION,
        PipelineStage.STAGE_2_HEADINGS,
        PipelineStage.STAGE_3_TOC_ALIGNMENT,
        PipelineStage.STAGE_4_TOC_NORMALIZATION,
        PipelineStage.STAGE_5_CHUNKING,
        PipelineStage.STAGE_5B_ENTITIES,
        PipelineStage.STAGE_6_VISION,
        PipelineStage.STAGE_7_EMBEDDING,
    ]

    def __init__(
        self,
        document_repo: DocumentRepository,
        toc_repo: TOCRepository,
        chunk_repo: ChunkRepository,
        entity_repo: EntityRepository,
        settings: Optional[Settings] = None,
    ):
        """Initialize orchestrator.

        Args:
            document_repo: Document repository
            toc_repo: TOC repository
            chunk_repo: Chunk repository
            entity_repo: Entity repository
            settings: Application settings
        """
        self.settings = settings or get_settings()
        self.document_repo = document_repo
        self.toc_repo = toc_repo
        self.chunk_repo = chunk_repo
        self.entity_repo = entity_repo

        # Initialize components
        self.state_manager = PipelineStateManager(self.settings)
        self.prompt_loader = PromptLoader()
        self.llm_client = OpenAIClient(self.settings)
        self.vision_client = VisionClient(self.settings)
        self.embedding_provider = OpenAIEmbeddingProvider(self.settings)
        self.pdf_extractor = PDFExtractor(self.settings)

        # Initialize stages
        self._init_stages()

        self.logger = logger.bind(component="PipelineOrchestrator")

    def _init_stages(self):
        """Initialize all pipeline stages."""
        self.stages = {
            PipelineStage.STAGE_0_EXTRACTION: Stage0Extraction(self.pdf_extractor),
            PipelineStage.STAGE_1_SEGMENTATION: Stage1Segmentation(
                self.llm_client, self.prompt_loader
            ),
            PipelineStage.STAGE_2_HEADINGS: Stage2Headings(
                self.llm_client, self.prompt_loader
            ),
            PipelineStage.STAGE_3_TOC_ALIGNMENT: Stage3TOCAlignment(
                self.llm_client, self.prompt_loader
            ),
            PipelineStage.STAGE_4_TOC_NORMALIZATION: Stage4TOCNormalization(
                self.llm_client, self.prompt_loader
            ),
            PipelineStage.STAGE_5_CHUNKING: Stage5Chunking(
                self.llm_client, self.prompt_loader
            ),
            PipelineStage.STAGE_5B_ENTITIES: Stage5bEntities(),
            PipelineStage.STAGE_6_VISION: Stage6Vision(self.vision_client),
            PipelineStage.STAGE_7_EMBEDDING: Stage7Embedding(self.embedding_provider),
        }

    async def run_pipeline(
        self,
        document_id: str,
        pdf_path: Path,
        skip_vision: bool = False,
        force_restart: bool = False,
    ) -> PipelineResult:
        """Run the full pipeline for a document.

        Args:
            document_id: Document ID
            pdf_path: Path to PDF file
            skip_vision: Skip Stage 6 vision processing
            force_restart: Ignore existing state and start fresh

        Returns:
            Pipeline result
        """
        self.logger.info(
            "Starting pipeline",
            document_id=document_id,
            pdf_path=str(pdf_path),
            skip_vision=skip_vision,
        )

        # Create or load state
        if force_restart:
            await self.state_manager.delete_state(document_id)

        state = await self.state_manager.load_state(document_id)
        if not state:
            state = await self.state_manager.create_state(
                document_id,
                config_snapshot={
                    "model": self.settings.openai_model,
                    "embedding_model": self.settings.embedding_model,
                },
            )

        # Update document status
        await self.document_repo.update_status(document_id, DocumentStatus.PROCESSING)

        # Determine starting point
        start_stage = await self.state_manager.get_resume_point(document_id)
        if not start_stage:
            start_stage = PipelineStage.STAGE_0_EXTRACTION

        start_idx = self.STAGE_ORDER.index(start_stage)

        # Track pipeline data
        pipeline_data: dict[str, Any] = {
            "document_id": document_id,
            "pdf_path": pdf_path,
        }

        stages_completed = []
        total_retrieval = 0
        total_generation = 0
        total_entities = 0

        try:
            for stage in self.STAGE_ORDER[start_idx:]:
                # Mark stage running
                await self.state_manager.mark_running(document_id, stage)

                # Skip vision if requested
                if stage == PipelineStage.STAGE_6_VISION and skip_vision:
                    await self._skip_stage(document_id, stage)
                    continue

                # Execute stage
                output, result = await self._execute_stage(
                    stage, pipeline_data, skip_vision
                )

                # Update state
                output_path = await self.state_manager.save_stage_output(
                    document_id, stage, output
                )
                await self.state_manager.update_stage(
                    document_id, stage, result, output_path
                )

                # Store output for next stage
                pipeline_data[stage.value] = output
                stages_completed.append(stage.value)

                # Persist to database at key stages
                if stage == PipelineStage.STAGE_0_EXTRACTION:
                    await self._persist_extraction(document_id, output)
                elif stage == PipelineStage.STAGE_4_TOC_NORMALIZATION:
                    await self._persist_toc(document_id, output)
                elif stage == PipelineStage.STAGE_5_CHUNKING:
                    await self._persist_chunks(document_id, output)
                    total_retrieval = len(output.retrieval_chunks)
                    total_generation = len(output.generation_chunks)
                elif stage == PipelineStage.STAGE_5B_ENTITIES:
                    await self._persist_entities(document_id, output)
                    total_entities = len(output.entities)
                elif stage == PipelineStage.STAGE_6_VISION:
                    await self._update_vision_entities(document_id, output)
                elif stage == PipelineStage.STAGE_7_EMBEDDING:
                    await self._update_embeddings(document_id, output)

            # Mark pipeline completed
            await self.state_manager.mark_completed(document_id)
            await self.document_repo.update_status(
                document_id, DocumentStatus.COMPLETED
            )

            state = await self.state_manager.load_state(document_id)

            self.logger.info(
                "Pipeline completed",
                document_id=document_id,
                stages=len(stages_completed),
            )

            return PipelineResult(
                document_id=document_id,
                success=True,
                stages_completed=stages_completed,
                total_retrieval_chunks=total_retrieval,
                total_generation_chunks=total_generation,
                total_entities=total_entities,
                duration_seconds=state.total_duration_seconds or 0,
            )

        except Exception as e:
            self.logger.error(
                "Pipeline failed",
                document_id=document_id,
                error=str(e),
            )

            # Mark error - reload state to get actual current stage
            error_state = await self.state_manager.load_state(document_id)
            current_stage = (
                error_state.current_stage
                if error_state and error_state.current_stage
                else PipelineStage.STAGE_0_EXTRACTION
            )
            await self.state_manager.mark_error(document_id, current_stage, str(e))
            await self.document_repo.update_status(
                document_id, DocumentStatus.FAILED, error_message=str(e)
            )

            return PipelineResult(
                document_id=document_id,
                success=False,
                stages_completed=stages_completed,
                total_retrieval_chunks=total_retrieval,
                total_generation_chunks=total_generation,
                total_entities=total_entities,
                duration_seconds=0,
                error=str(e),
            )

    async def _execute_stage(
        self,
        stage: PipelineStage,
        data: dict[str, Any],
        skip_vision: bool,
    ) -> tuple[Any, Any]:
        """Execute a single stage."""
        stage_handler = self.stages[stage]

        # Build input based on stage
        if stage == PipelineStage.STAGE_0_EXTRACTION:
            input_data = Stage0Input(
                document_id=data["document_id"],
                file_path=data["pdf_path"],
            )
        elif stage == PipelineStage.STAGE_1_SEGMENTATION:
            s0_output = data[PipelineStage.STAGE_0_EXTRACTION.value]
            input_data = Stage1Input(
                document_id=data["document_id"],
                raw_text=s0_output.raw_text,
                raw_text_by_page=s0_output.raw_text_by_page,
                page_count=s0_output.page_count,
            )
        elif stage == PipelineStage.STAGE_2_HEADINGS:
            s1_output = data[PipelineStage.STAGE_1_SEGMENTATION.value]
            input_data = Stage2Input(
                document_id=data["document_id"],
                segments=s1_output.segments,
            )
        elif stage == PipelineStage.STAGE_3_TOC_ALIGNMENT:
            s2_output = data[PipelineStage.STAGE_2_HEADINGS.value]
            input_data = Stage3Input(
                document_id=data["document_id"],
                segments_with_headings=s2_output.segments_with_headings,
            )
        elif stage == PipelineStage.STAGE_4_TOC_NORMALIZATION:
            s3_output = data[PipelineStage.STAGE_3_TOC_ALIGNMENT.value]
            input_data = Stage4Input(
                document_id=data["document_id"],
                toc_nodes=s3_output.toc_nodes,
                segment_to_toc_mapping=s3_output.segment_to_toc_mapping,
            )
        elif stage == PipelineStage.STAGE_5_CHUNKING:
            s1_output = data[PipelineStage.STAGE_1_SEGMENTATION.value]
            s3_output = data[PipelineStage.STAGE_3_TOC_ALIGNMENT.value]
            s4_output = data[PipelineStage.STAGE_4_TOC_NORMALIZATION.value]
            input_data = Stage5Input(
                document_id=data["document_id"],
                normalized_toc_nodes=s4_output.normalized_toc_nodes,
                segments=s1_output.segments,
                segment_to_toc_mapping=s3_output.segment_to_toc_mapping,
            )
        elif stage == PipelineStage.STAGE_5B_ENTITIES:
            s0_output = data[PipelineStage.STAGE_0_EXTRACTION.value]
            s4_output = data[PipelineStage.STAGE_4_TOC_NORMALIZATION.value]

            # Build page to TOC mapping
            page_mapping = self._build_page_toc_mapping(s4_output.normalized_toc_nodes)

            input_data = Stage5bInput(
                document_id=data["document_id"],
                tables=s0_output.tables,
                images=s0_output.images,
                toc_nodes=s4_output.normalized_toc_nodes,
                page_to_toc_mapping=page_mapping,
            )
        elif stage == PipelineStage.STAGE_6_VISION:
            s5b_output = data[PipelineStage.STAGE_5B_ENTITIES.value]
            input_data = Stage6Input(
                document_id=data["document_id"],
                entities=s5b_output.entities,
                skip_vision=skip_vision,
            )
        elif stage == PipelineStage.STAGE_7_EMBEDDING:
            s5_output = data[PipelineStage.STAGE_5_CHUNKING.value]
            input_data = Stage7Input(
                document_id=data["document_id"],
                retrieval_chunks=s5_output.retrieval_chunks,
            )
        else:
            raise PipelineError(f"Unknown stage: {stage}")

        return await stage_handler.run(input_data)

    async def _skip_stage(self, document_id: str, stage: PipelineStage):
        """Mark stage as skipped."""
        from datetime import datetime

        from src.core.models import StageResult

        result = StageResult(
            stage=stage,
            status=StageStatus.SKIPPED,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_seconds=0,
            output_summary={"reason": "skipped by user"},
        )
        await self.state_manager.update_stage(document_id, stage, result)

    def _build_page_toc_mapping(self, toc_nodes: list) -> dict[int, str]:
        """Build mapping from page numbers to TOC nodes."""
        mapping = {}

        for node in toc_nodes:
            if node.page_start:
                for page in range(
                    node.page_start, (node.page_end or node.page_start) + 1
                ):
                    if page not in mapping:
                        mapping[page] = node.id

        # If no page info, use first node for all
        if not mapping and toc_nodes:
            mapping[1] = toc_nodes[0].id

        return mapping

    async def _persist_extraction(self, document_id: str, output):
        """Persist extraction results."""
        await self.document_repo.set_raw_text(
            document_id,
            output.raw_text,
            output.raw_text_by_page,
        )

    async def _persist_toc(self, document_id: str, output):
        """Persist TOC nodes."""
        # Delete existing TOC
        await self.toc_repo.delete_by_document(document_id)
        # Insert new
        await self.toc_repo.bulk_insert(output.normalized_toc_nodes)

    async def _persist_chunks(self, document_id: str, output):
        """Persist chunks."""
        # Delete existing chunks
        await self.chunk_repo.delete_by_document(document_id)
        # Insert new
        await self.chunk_repo.insert_retrieval_chunks(output.retrieval_chunks)
        await self.chunk_repo.insert_generation_chunks(output.generation_chunks)

    async def _persist_entities(self, document_id: str, output):
        """Persist entities."""
        # Delete existing
        await self.entity_repo.delete_by_document(document_id)
        # Insert new
        await self.entity_repo.bulk_insert(output.entities)

    async def _update_vision_entities(self, document_id: str, output):
        """Update entities with vision descriptions after Stage 6."""
        for entity in output.enhanced_entities:
            if entity.vision_processed:
                updates = {"vision_processed": True}
                if entity.vision_description:
                    updates["vision_description"] = entity.vision_description
                if entity.ir_yaml:
                    updates["ir_yaml"] = entity.ir_yaml
                await self.entity_repo.update(entity.id, **updates)

    async def _update_embeddings(self, document_id: str, output):
        """Update embeddings in chunks."""
        for chunk in output.embedded_chunks:
            await self.chunk_repo.update_embedding(
                chunk.id,
                chunk.embedding,
                chunk.embedding_model,
            )

    async def get_status(self, document_id: str) -> dict[str, Any]:
        """Get pipeline status.

        Args:
            document_id: Document ID

        Returns:
            Status dictionary
        """
        return await self.state_manager.get_progress(document_id)

    async def cancel_pipeline(self, document_id: str) -> bool:
        """Cancel running pipeline.

        Args:
            document_id: Document ID

        Returns:
            True if cancelled
        """
        # Mark document as failed
        await self.document_repo.update_status(
            document_id,
            DocumentStatus.FAILED,
            error_message="Cancelled by user",
        )

        self.logger.info("Pipeline cancelled", document_id=document_id)
        return True
