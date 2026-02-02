"""Stage 1: Semantic Segmentation."""

from dataclasses import dataclass
from typing import Any

from src.core.models import PipelineStage, Segment, SemanticType
from src.core.models import Stage1Output as LLMStage1Output
from src.llm.openai_client import OpenAIClient
from src.pipeline.base import BaseStage
from src.prompts.loader import PromptLoader


@dataclass
class Stage1Input:
    """Input for Stage 1."""

    document_id: str
    raw_text: str
    raw_text_by_page: list[str]
    page_count: int


@dataclass
class Stage1Output:
    """Output from Stage 1."""

    document_id: str
    segments: list[Segment]


class Stage1Segmentation(BaseStage[Stage1Input, Stage1Output]):
    """Stage 1: Segment raw text into semantic units."""

    stage = PipelineStage.STAGE_1_SEGMENTATION
    stage_name = "segmentation"

    # Maximum tokens per LLM call
    MAX_CHUNK_SIZE = 8000

    def __init__(
        self,
        llm_client: OpenAIClient,
        prompt_loader: PromptLoader,
    ):
        """Initialize stage.

        Args:
            llm_client: OpenAI client
            prompt_loader: Prompt template loader
        """
        super().__init__()
        self.llm_client = llm_client
        self.prompt_loader = prompt_loader

    def validate_input(self, input_data: Stage1Input) -> bool:
        """Validate input."""
        return bool(input_data.document_id and input_data.raw_text)

    def validate_output(self, output_data: Stage1Output) -> bool:
        """Validate output."""
        return len(output_data.segments) > 0

    async def execute(self, input_data: Stage1Input) -> Stage1Output:
        """Execute semantic segmentation.

        Args:
            input_data: Stage input

        Returns:
            Segmentation results
        """
        self.logger.info(
            "Segmenting text",
            document_id=input_data.document_id,
            text_length=len(input_data.raw_text),
        )

        system_prompt = self.prompt_loader.get_system_prompt("stage1_segmentation")

        all_segments = []
        segment_id_counter = 0

        # Process by page for better page number tracking
        for page_num, page_text in enumerate(input_data.raw_text_by_page, start=1):
            if not page_text.strip():
                continue

            # Build user prompt
            user_prompt = f"""Document page {page_num} of {input_data.page_count}:

{page_text}

Segment this page into semantic units. Assign page_number = {page_num} to all segments."""

            try:
                result = await self.llm_client.generate_structured(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_schema=LLMStage1Output,
                )

                # Convert to Segment objects
                for seg_data in result.segments:
                    segment = Segment(
                        segment_id=segment_id_counter,
                        content=seg_data.content,
                        page_number=page_num,
                        position_in_page=seg_data.segment_id,
                        semantic_type=self._parse_semantic_type(seg_data.semantic_type),
                        key_concepts=seg_data.key_concepts,
                        reasoning=seg_data.reasoning,
                    )
                    all_segments.append(segment)
                    segment_id_counter += 1

            except Exception as e:
                self.logger.warning(
                    "Failed to segment page",
                    page=page_num,
                    error=str(e),
                )
                # Create a fallback segment for this page
                fallback_segment = Segment(
                    segment_id=segment_id_counter,
                    content=page_text,
                    page_number=page_num,
                    position_in_page=0,
                    semantic_type=SemanticType.EXPLANATION,
                    key_concepts=[],
                    reasoning="Fallback segment due to LLM error",
                )
                all_segments.append(fallback_segment)
                segment_id_counter += 1

        return Stage1Output(
            document_id=input_data.document_id,
            segments=all_segments,
        )

    def _parse_semantic_type(self, type_str: str) -> SemanticType:
        """Parse semantic type string to enum."""
        try:
            return SemanticType(type_str.lower())
        except ValueError:
            return SemanticType.EXPLANATION

    def get_output_summary(self, output: Stage1Output) -> dict[str, Any]:
        """Get output summary."""
        type_counts = {}
        for seg in output.segments:
            t = (
                seg.semantic_type.value
                if hasattr(seg.semantic_type, "value")
                else seg.semantic_type
            )
            type_counts[t] = type_counts.get(t, 0) + 1

        return {
            "total_segments": len(output.segments),
            "segments_by_type": type_counts,
        }
