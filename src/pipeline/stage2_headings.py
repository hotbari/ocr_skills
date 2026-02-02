"""Stage 2: Heading Generation."""

from dataclasses import dataclass
from typing import Any

from src.core.models import PipelineStage, Segment, SegmentWithHeading
from src.core.models import Stage2Output as LLMStage2Output
from src.core.models import TOCLevel
from src.llm.openai_client import OpenAIClient
from src.pipeline.base import BaseStage
from src.prompts.loader import PromptLoader


@dataclass
class Stage2Input:
    """Input for Stage 2."""

    document_id: str
    segments: list[Segment]


@dataclass
class Stage2Output:
    """Output from Stage 2."""

    document_id: str
    segments_with_headings: list[SegmentWithHeading]


class Stage2Headings(BaseStage[Stage2Input, Stage2Output]):
    """Stage 2: Generate candidate headings for segments."""

    stage = PipelineStage.STAGE_2_HEADINGS
    stage_name = "headings"

    # Process segments in batches
    BATCH_SIZE = 10

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

    def validate_input(self, input_data: Stage2Input) -> bool:
        """Validate input."""
        return bool(input_data.document_id and input_data.segments)

    def validate_output(self, output_data: Stage2Output) -> bool:
        """Validate output."""
        return len(output_data.segments_with_headings) > 0

    async def execute(self, input_data: Stage2Input) -> Stage2Output:
        """Generate candidate headings.

        Args:
            input_data: Stage input

        Returns:
            Segments with headings
        """
        self.logger.info(
            "Generating headings",
            document_id=input_data.document_id,
            segment_count=len(input_data.segments),
        )

        system_prompt = self.prompt_loader.get_system_prompt("stage2_headings")

        all_segments_with_headings = []

        # Process in batches
        for i in range(0, len(input_data.segments), self.BATCH_SIZE):
            batch = input_data.segments[i : i + self.BATCH_SIZE]

            # Build user prompt
            segments_text = []
            for seg in batch:
                seg_text = f"""Segment ID: {seg.segment_id}
Content: {seg.content[:500]}...
Semantic Type: {seg.semantic_type}
Key Concepts: {', '.join(seg.key_concepts)}
"""
                segments_text.append(seg_text)

            user_prompt = f"""Analyze these {len(batch)} segments and generate candidate headings:

{chr(10).join(segments_text)}"""

            try:
                result = await self.llm_client.generate_structured(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_schema=LLMStage2Output,
                )

                # Map results back to segments
                heading_map = {h.segment_id: h for h in result.headings}

                for seg in batch:
                    heading_data = heading_map.get(seg.segment_id)

                    if heading_data:
                        swh = SegmentWithHeading(
                            segment=seg,
                            candidate_headings=heading_data.candidate_headings,
                            confidence_scores=heading_data.confidence_scores,
                            selected_heading=(
                                heading_data.candidate_headings[0]
                                if heading_data.candidate_headings
                                else None
                            ),
                            heading_level=self._parse_level(
                                heading_data.recommended_level
                            ),
                        )
                    else:
                        # Fallback
                        swh = SegmentWithHeading(
                            segment=seg,
                            candidate_headings=[f"Section {seg.segment_id}"],
                            confidence_scores=[0.5],
                            selected_heading=f"Section {seg.segment_id}",
                            heading_level=TOCLevel.L2,
                        )

                    all_segments_with_headings.append(swh)

            except Exception as e:
                self.logger.warning(
                    "Failed to generate headings for batch",
                    batch_start=i,
                    error=str(e),
                )
                # Create fallback headings
                for seg in batch:
                    swh = SegmentWithHeading(
                        segment=seg,
                        candidate_headings=[f"Section {seg.segment_id}"],
                        confidence_scores=[0.5],
                        selected_heading=f"Section {seg.segment_id}",
                        heading_level=TOCLevel.L2,
                    )
                    all_segments_with_headings.append(swh)

        return Stage2Output(
            document_id=input_data.document_id,
            segments_with_headings=all_segments_with_headings,
        )

    def _parse_level(self, level: int) -> TOCLevel:
        """Parse level integer to enum."""
        if level == 1:
            return TOCLevel.L1
        elif level == 3:
            return TOCLevel.L3
        return TOCLevel.L2

    def get_output_summary(self, output: Stage2Output) -> dict[str, Any]:
        """Get output summary."""
        level_counts = {1: 0, 2: 0, 3: 0}
        for swh in output.segments_with_headings:
            if swh.heading_level:
                val = (
                    swh.heading_level.value
                    if hasattr(swh.heading_level, "value")
                    else swh.heading_level
                )
                level_counts[val] = level_counts.get(val, 0) + 1

        return {
            "total_segments": len(output.segments_with_headings),
            "by_level": level_counts,
        }
