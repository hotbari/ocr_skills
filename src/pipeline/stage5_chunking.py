"""Stage 5: Dual Chunking (Retrieval + Generation)."""

from dataclasses import dataclass
from typing import Any

from src.core.models import (GenerationChunk, PipelineStage, RetrievalChunk,
                             Segment, SemanticType)
from src.core.models import Stage5Output as LLMStage5Output
from src.core.models import TOCNode, generate_id
from src.llm.openai_client import OpenAIClient
from src.pipeline.base import BaseStage
from src.prompts.loader import PromptLoader


@dataclass
class Stage5Input:
    """Input for Stage 5."""

    document_id: str
    normalized_toc_nodes: list[TOCNode]
    segments: list[Segment]
    segment_to_toc_mapping: dict[int, str]


@dataclass
class Stage5Output:
    """Output from Stage 5."""

    document_id: str
    retrieval_chunks: list[RetrievalChunk]
    generation_chunks: list[GenerationChunk]


class Stage5Chunking(BaseStage[Stage5Input, Stage5Output]):
    """Stage 5: Create dual-chunk system."""

    stage = PipelineStage.STAGE_5_CHUNKING
    stage_name = "chunking"

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

    def validate_input(self, input_data: Stage5Input) -> bool:
        """Validate input."""
        return bool(
            input_data.document_id
            and input_data.normalized_toc_nodes
            and input_data.segments
        )

    def validate_output(self, output_data: Stage5Output) -> bool:
        """Validate output."""
        return (
            len(output_data.retrieval_chunks) > 0
            and len(output_data.generation_chunks) > 0
        )

    async def execute(self, input_data: Stage5Input) -> Stage5Output:
        """Create dual-chunk system.

        Args:
            input_data: Stage input

        Returns:
            Retrieval and generation chunks
        """
        self.logger.info(
            "Creating dual chunks",
            document_id=input_data.document_id,
            toc_nodes=len(input_data.normalized_toc_nodes),
            segments=len(input_data.segments),
        )

        # Build context paths for TOC nodes
        context_paths = self._build_context_paths(input_data.normalized_toc_nodes)

        # Group segments by TOC node
        segments_by_toc = self._group_segments_by_toc(
            input_data.segments,
            input_data.segment_to_toc_mapping,
        )

        all_retrieval_chunks = []
        all_generation_chunks = []
        ret_sequence = 0
        gen_sequence = 0

        system_prompt = self.prompt_loader.get_system_prompt("stage5_chunking")

        for toc_node in input_data.normalized_toc_nodes:
            node_segments = segments_by_toc.get(toc_node.id, [])

            if not node_segments:
                continue

            # Combine segment content
            combined_content = "\n\n".join(seg.content for seg in node_segments)
            all_concepts = list(
                set(concept for seg in node_segments for concept in seg.key_concepts)
            )
            page_numbers = list(set(seg.page_number for seg in node_segments))

            context_path = context_paths.get(toc_node.id, toc_node.title)

            # Try LLM chunking for non-trivial content
            if len(combined_content) > 500:
                try:
                    result = await self._llm_chunk(
                        system_prompt,
                        toc_node,
                        node_segments,
                        context_path,
                    )

                    # Process LLM results
                    for ret_data in result.retrieval_chunks:
                        gen_chunk_id = generate_id()

                        ret_chunk = RetrievalChunk(
                            id=generate_id(),  # Always use UUID to avoid duplicate key errors
                            document_id=input_data.document_id,
                            toc_node_id=toc_node.id,
                            content=ret_data.content,
                            semantic_type=self._parse_type(ret_data.semantic_type),
                            key_concepts=ret_data.key_concepts,
                            page_numbers=page_numbers,
                            sequence_in_document=ret_sequence,
                            sequence_in_toc_node=len(all_retrieval_chunks),
                            generation_chunk_id=gen_chunk_id,
                            token_count=len(ret_data.content.split()),
                        )
                        all_retrieval_chunks.append(ret_chunk)
                        ret_sequence += 1

                    for gen_data in result.generation_chunks:
                        gen_chunk = GenerationChunk(
                            id=generate_id(),  # Always use UUID to avoid duplicate key errors
                            document_id=input_data.document_id,
                            toc_node_id=toc_node.id,
                            content=gen_data.content,
                            summary=gen_data.summary,
                            semantic_type=self._parse_type("explanation"),
                            key_concepts=gen_data.key_concepts,
                            context_path=context_path,
                            page_numbers=page_numbers,
                            sequence_in_document=gen_sequence,
                            retrieval_chunk_ids=gen_data.linked_retrieval_ids,
                            token_count=len(gen_data.content.split()),
                        )
                        all_generation_chunks.append(gen_chunk)
                        gen_sequence += 1

                    continue

                except Exception as e:
                    self.logger.warning(
                        "LLM chunking failed, using fallback",
                        error=str(e),
                    )

            # Fallback: simple chunking
            gen_chunk_id = generate_id()

            # Create retrieval chunk (dense summary)
            ret_content = self._create_retrieval_content(node_segments)
            ret_chunk = RetrievalChunk(
                document_id=input_data.document_id,
                toc_node_id=toc_node.id,
                content=ret_content,
                semantic_type=(
                    node_segments[0].semantic_type
                    if node_segments
                    else SemanticType.EXPLANATION
                ),
                key_concepts=all_concepts[:5],
                page_numbers=page_numbers,
                sequence_in_document=ret_sequence,
                sequence_in_toc_node=0,
                generation_chunk_id=gen_chunk_id,
                token_count=len(ret_content.split()),
            )
            all_retrieval_chunks.append(ret_chunk)
            ret_sequence += 1

            # Create generation chunk (full content)
            gen_chunk = GenerationChunk(
                id=gen_chunk_id,
                document_id=input_data.document_id,
                toc_node_id=toc_node.id,
                content=combined_content,
                summary=self._create_summary(node_segments),
                semantic_type=(
                    node_segments[0].semantic_type
                    if node_segments
                    else SemanticType.EXPLANATION
                ),
                key_concepts=all_concepts,
                context_path=context_path,
                page_numbers=page_numbers,
                sequence_in_document=gen_sequence,
                retrieval_chunk_ids=[ret_chunk.id],
                token_count=len(combined_content.split()),
            )
            all_generation_chunks.append(gen_chunk)
            gen_sequence += 1

        return Stage5Output(
            document_id=input_data.document_id,
            retrieval_chunks=all_retrieval_chunks,
            generation_chunks=all_generation_chunks,
        )

    async def _llm_chunk(
        self,
        system_prompt: str,
        toc_node: TOCNode,
        segments: list[Segment],
        context_path: str,
    ) -> LLMStage5Output:
        """Use LLM for intelligent chunking."""
        combined_content = "\n\n".join(seg.content for seg in segments)

        level_val = (
            toc_node.level.value if hasattr(toc_node.level, "value") else toc_node.level
        )
        user_prompt = f"""TOC Node: {toc_node.title}
Context Path: {context_path}
Level: L{level_val}

Content to chunk:
{combined_content[:4000]}

Create retrieval chunks (100-300 tokens, dense) and generation chunks (500-1500 tokens, detailed)."""

        return await self.llm_client.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=LLMStage5Output,
        )

    def _build_context_paths(self, nodes: list[TOCNode]) -> dict[str, str]:
        """Build context paths for all nodes."""
        node_map = {n.id: n for n in nodes}
        paths = {}

        for node in nodes:
            path_parts = [node.title]
            current = node

            while current.parent_id:
                parent = node_map.get(current.parent_id)
                if parent:
                    path_parts.insert(0, parent.title)
                    current = parent
                else:
                    break

            paths[node.id] = " > ".join(path_parts)

        return paths

    def _group_segments_by_toc(
        self,
        segments: list[Segment],
        mapping: dict[int, str],
    ) -> dict[str, list[Segment]]:
        """Group segments by their TOC node."""
        grouped: dict[str, list[Segment]] = {}

        for segment in segments:
            toc_id = mapping.get(segment.segment_id)
            if toc_id:
                if toc_id not in grouped:
                    grouped[toc_id] = []
                grouped[toc_id].append(segment)

        return grouped

    def _create_retrieval_content(self, segments: list[Segment]) -> str:
        """Create dense retrieval content from segments."""
        # Extract key sentences and concepts
        key_parts = []

        for seg in segments[:3]:  # First 3 segments
            # Get first sentence or first 200 chars
            content = seg.content.strip()
            first_sentence = (
                content.split(".")[0] + "." if "." in content else content[:200]
            )
            key_parts.append(first_sentence)

            if seg.key_concepts:
                key_parts.append(f"Key concepts: {', '.join(seg.key_concepts[:3])}")

        return " ".join(key_parts)[:500]  # Cap at ~100 tokens

    def _create_summary(self, segments: list[Segment]) -> str:
        """Create summary for generation chunk."""
        if not segments:
            return ""

        # Use first segment's content as base
        first_content = segments[0].content[:200]

        # Add key concepts
        all_concepts = list(set(c for seg in segments for c in seg.key_concepts))[:5]

        if all_concepts:
            return f"{first_content}... Covers: {', '.join(all_concepts)}"

        return first_content + "..."

    def _parse_type(self, type_str: str) -> SemanticType:
        """Parse semantic type string."""
        try:
            return SemanticType(type_str.lower())
        except ValueError:
            return SemanticType.EXPLANATION

    def get_output_summary(self, output: Stage5Output) -> dict[str, Any]:
        """Get output summary."""
        return {
            "retrieval_chunks": len(output.retrieval_chunks),
            "generation_chunks": len(output.generation_chunks),
        }
