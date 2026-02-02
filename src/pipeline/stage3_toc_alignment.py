"""Stage 3: TOC Structure Alignment."""

from dataclasses import dataclass
from typing import Any

from src.core.models import PipelineStage, SegmentWithHeading
from src.core.models import Stage3Output as LLMStage3Output
from src.core.models import TOCLevel, TOCNode, generate_id
from src.llm.openai_client import OpenAIClient
from src.pipeline.base import BaseStage
from src.prompts.loader import PromptLoader


@dataclass
class Stage3Input:
    """Input for Stage 3."""

    document_id: str
    segments_with_headings: list[SegmentWithHeading]


@dataclass
class Stage3Output:
    """Output from Stage 3."""

    document_id: str
    toc_nodes: list[TOCNode]
    segment_to_toc_mapping: dict[int, str]  # segment_id -> toc_node_id


class Stage3TOCAlignment(BaseStage[Stage3Input, Stage3Output]):
    """Stage 3: Align segments into TOC structure."""

    stage = PipelineStage.STAGE_3_TOC_ALIGNMENT
    stage_name = "toc_alignment"

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

    def validate_input(self, input_data: Stage3Input) -> bool:
        """Validate input."""
        return bool(input_data.document_id and input_data.segments_with_headings)

    def validate_output(self, output_data: Stage3Output) -> bool:
        """Validate output."""
        return len(output_data.toc_nodes) > 0

    async def execute(self, input_data: Stage3Input) -> Stage3Output:
        """Align segments into TOC hierarchy.

        Args:
            input_data: Stage input

        Returns:
            TOC structure with mappings
        """
        self.logger.info(
            "Aligning TOC structure",
            document_id=input_data.document_id,
            segment_count=len(input_data.segments_with_headings),
        )

        system_prompt = self.prompt_loader.get_system_prompt("stage3_toc_alignment")

        # Build segment summary for LLM
        segment_summaries = []
        for swh in input_data.segments_with_headings:
            summary = {
                "segment_id": swh.segment.segment_id,
                "headings": swh.candidate_headings[:3],
                "level_hint": (
                    swh.heading_level.value
                    if swh.heading_level and hasattr(swh.heading_level, "value")
                    else (swh.heading_level or 2)
                ),
                "type": swh.segment.semantic_type,
                "preview": swh.segment.content[:200],
            }
            segment_summaries.append(summary)

        user_prompt = f"""Create a TOC structure for {len(segment_summaries)} segments.

Segments:
{self._format_segments(segment_summaries)}

Create a hierarchical TOC with L1/L2/L3 levels. Assign each segment to exactly one TOC node."""

        try:
            result = await self.llm_client.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_schema=LLMStage3Output,
            )

            # Convert LLM output to TOCNode objects
            toc_nodes = []
            segment_mapping = {}
            sequence = 0

            # Build ID mapping: LLM node_id -> actual UUID
            llm_to_real_id = {}

            for node_data in result.toc_nodes:
                # Always generate unique ID with document prefix to avoid conflicts
                real_id = f"{input_data.document_id[:8]}_{generate_id()[:8]}"
                llm_to_real_id[node_data.node_id] = real_id

                # Resolve parent_id using mapping
                real_parent_id = None
                if node_data.parent_node_id:
                    real_parent_id = llm_to_real_id.get(node_data.parent_node_id)

                toc_node = TOCNode(
                    id=real_id,
                    document_id=input_data.document_id,
                    level=self._parse_level(node_data.level),
                    title=node_data.title,
                    normalized_title=node_data.title.lower().strip(),
                    sequence_number=sequence,
                    parent_id=real_parent_id,
                )
                toc_nodes.append(toc_node)
                sequence += 1

                # Map segments to this node
                for seg_id in node_data.segment_ids:
                    segment_mapping[seg_id] = toc_node.id

            # Ensure all segments are mapped
            for swh in input_data.segments_with_headings:
                if swh.segment.segment_id not in segment_mapping:
                    # Assign to last node or create orphan node
                    if toc_nodes:
                        segment_mapping[swh.segment.segment_id] = toc_nodes[-1].id
                    else:
                        orphan_node = TOCNode(
                            id=generate_id(),
                            document_id=input_data.document_id,
                            level=TOCLevel.L1,
                            title="Miscellaneous",
                            normalized_title="miscellaneous",
                            sequence_number=sequence,
                        )
                        toc_nodes.append(orphan_node)
                        segment_mapping[swh.segment.segment_id] = orphan_node.id
                        sequence += 1

            return Stage3Output(
                document_id=input_data.document_id,
                toc_nodes=toc_nodes,
                segment_to_toc_mapping=segment_mapping,
            )

        except Exception as e:
            self.logger.error("TOC alignment failed", error=str(e))
            # Create fallback flat structure
            return self._create_fallback_toc(input_data)

    def _parse_level(self, level: int) -> TOCLevel:
        """Parse level integer to enum."""
        if level == 1:
            return TOCLevel.L1
        elif level == 3:
            return TOCLevel.L3
        return TOCLevel.L2

    def _format_segments(self, summaries: list[dict]) -> str:
        """Format segment summaries for prompt."""
        lines = []
        for s in summaries:
            line = f"[{s['segment_id']}] L{s['level_hint']} | {s['headings'][0] if s['headings'] else 'Untitled'} | {s['type']}"
            lines.append(line)
        return "\n".join(lines)

    def _create_fallback_toc(self, input_data: Stage3Input) -> Stage3Output:
        """Create simple fallback TOC structure."""
        self.logger.warning("Creating fallback TOC structure")

        toc_nodes = []
        segment_mapping = {}

        # Create one L1 node
        root_node = TOCNode(
            id=generate_id(),
            document_id=input_data.document_id,
            level=TOCLevel.L1,
            title="Document Content",
            normalized_title="document content",
            sequence_number=0,
        )
        toc_nodes.append(root_node)

        # Group segments by page into L2 nodes
        segments_by_page: dict[int, list[SegmentWithHeading]] = {}
        for swh in input_data.segments_with_headings:
            page = swh.segment.page_number
            if page not in segments_by_page:
                segments_by_page[page] = []
            segments_by_page[page].append(swh)

        sequence = 1
        for page_num, page_segments in sorted(segments_by_page.items()):
            page_node = TOCNode(
                id=generate_id(),
                document_id=input_data.document_id,
                level=TOCLevel.L2,
                title=f"Page {page_num}",
                normalized_title=f"page {page_num}",
                sequence_number=sequence,
                parent_id=root_node.id,
            )
            toc_nodes.append(page_node)
            root_node.children_ids.append(page_node.id)
            sequence += 1

            for swh in page_segments:
                segment_mapping[swh.segment.segment_id] = page_node.id

        return Stage3Output(
            document_id=input_data.document_id,
            toc_nodes=toc_nodes,
            segment_to_toc_mapping=segment_mapping,
        )

    def get_output_summary(self, output: Stage3Output) -> dict[str, Any]:
        """Get output summary."""
        level_counts = {1: 0, 2: 0, 3: 0}
        for node in output.toc_nodes:
            lvl = node.level.value if hasattr(node.level, "value") else node.level
            level_counts[lvl] = level_counts.get(lvl, 0) + 1

        return {
            "total_toc_nodes": len(output.toc_nodes),
            "by_level": level_counts,
            "segments_mapped": len(output.segment_to_toc_mapping),
        }
