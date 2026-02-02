"""Stage 4: TOC Normalization."""

from dataclasses import dataclass
from typing import Any

from src.core.models import PipelineStage
from src.core.models import Stage4Output as LLMStage4Output
from src.core.models import TOCLevel, TOCNode
from src.llm.openai_client import OpenAIClient
from src.pipeline.base import BaseStage
from src.prompts.loader import PromptLoader


@dataclass
class Stage4Input:
    """Input for Stage 4."""

    document_id: str
    toc_nodes: list[TOCNode]
    segment_to_toc_mapping: dict[int, str]


@dataclass
class Stage4Output:
    """Output from Stage 4."""

    document_id: str
    normalized_toc_nodes: list[TOCNode]
    validation_passed: bool
    issues_fixed: list[str]


class Stage4TOCNormalization(BaseStage[Stage4Input, Stage4Output]):
    """Stage 4: Normalize and validate TOC structure."""

    stage = PipelineStage.STAGE_4_TOC_NORMALIZATION
    stage_name = "toc_normalization"

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

    def validate_input(self, input_data: Stage4Input) -> bool:
        """Validate input."""
        return bool(input_data.document_id and input_data.toc_nodes)

    def validate_output(self, output_data: Stage4Output) -> bool:
        """Validate output."""
        return len(output_data.normalized_toc_nodes) > 0

    async def execute(self, input_data: Stage4Input) -> Stage4Output:
        """Normalize TOC structure.

        Args:
            input_data: Stage input

        Returns:
            Normalized TOC
        """
        self.logger.info(
            "Normalizing TOC",
            document_id=input_data.document_id,
            node_count=len(input_data.toc_nodes),
        )

        # First, perform local validation and fixes
        normalized_nodes, local_issues = self._local_normalization(
            input_data.toc_nodes,
            input_data.document_id,
        )

        # If structure is simple enough, skip LLM
        if self._is_structure_valid(normalized_nodes):
            return Stage4Output(
                document_id=input_data.document_id,
                normalized_toc_nodes=normalized_nodes,
                validation_passed=True,
                issues_fixed=local_issues,
            )

        # Use LLM for complex normalization
        system_prompt = self.prompt_loader.get_system_prompt("stage4_toc_normalization")

        toc_summary = self._format_toc_for_prompt(normalized_nodes)

        user_prompt = f"""Normalize this TOC structure:

{toc_summary}

Apply the validation checklist and fix any issues."""

        try:
            result = await self.llm_client.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_schema=LLMStage4Output,
            )

            # Apply LLM suggestions
            final_nodes = []
            for node_data in result.normalized_nodes:
                # Find original node
                original = next(
                    (n for n in normalized_nodes if n.id == node_data.node_id),
                    None,
                )

                if original:
                    # Update with normalized data
                    original.title = node_data.title
                    original.normalized_title = node_data.normalized_title
                    original.level = self._parse_level(node_data.level)
                    original.parent_id = node_data.parent_node_id
                    final_nodes.append(original)

            all_issues = local_issues + result.issues_fixed

            return Stage4Output(
                document_id=input_data.document_id,
                normalized_toc_nodes=final_nodes if final_nodes else normalized_nodes,
                validation_passed=result.validation_passed,
                issues_fixed=all_issues,
            )

        except Exception as e:
            self.logger.warning("LLM normalization failed", error=str(e))
            return Stage4Output(
                document_id=input_data.document_id,
                normalized_toc_nodes=normalized_nodes,
                validation_passed=len(local_issues) == 0,
                issues_fixed=local_issues,
            )

    def _local_normalization(
        self,
        nodes: list[TOCNode],
        document_id: str,
    ) -> tuple[list[TOCNode], list[str]]:
        """Perform local normalization without LLM."""
        issues = []
        normalized = []

        # Check for L1 nodes
        l1_nodes = [n for n in nodes if n.level == TOCLevel.L1]
        if not l1_nodes:
            # Create root L1 node
            root = TOCNode(
                document_id=document_id,
                level=TOCLevel.L1,
                title="Document",
                normalized_title="document",
                sequence_number=0,
            )
            normalized.append(root)
            issues.append("Created root L1 node")

            # Re-parent orphan nodes
            for node in nodes:
                if node.level != TOCLevel.L1:
                    if not node.parent_id:
                        node.parent_id = root.id
                        issues.append(f"Re-parented orphan node: {node.title}")
                    normalized.append(node)
        else:
            normalized = nodes.copy()

        # Normalize titles
        for node in normalized:
            if not node.normalized_title:
                node.normalized_title = node.title.lower().strip()

        # Fix parent-child relationships
        node_map = {n.id: n for n in normalized}
        for node in normalized:
            if node.parent_id and node.parent_id not in node_map:
                node.parent_id = None
                issues.append(f"Cleared invalid parent for: {node.title}")

        # Update children_ids
        for node in normalized:
            children = [n for n in normalized if n.parent_id == node.id]
            node.children_ids = [c.id for c in children]

        # Re-sequence
        for i, node in enumerate(normalized):
            node.sequence_number = i

        return normalized, issues

    def _is_structure_valid(self, nodes: list[TOCNode]) -> bool:
        """Check if TOC structure is valid."""
        # Has at least one L1
        if not any(n.level == TOCLevel.L1 for n in nodes):
            return False

        # All L2 have L1 parent
        node_map = {n.id: n for n in nodes}
        for node in nodes:
            if node.level == TOCLevel.L2 and node.parent_id:
                parent = node_map.get(node.parent_id)
                if not parent or parent.level != TOCLevel.L1:
                    return False

        # All L3 have L2 parent
        for node in nodes:
            if node.level == TOCLevel.L3 and node.parent_id:
                parent = node_map.get(node.parent_id)
                if not parent or parent.level != TOCLevel.L2:
                    return False

        return True

    def _format_toc_for_prompt(self, nodes: list[TOCNode]) -> str:
        """Format TOC for LLM prompt."""
        lines = []
        for node in nodes:
            indent = "  " * (node.level.value - 1)
            parent_info = f" (parent: {node.parent_id})" if node.parent_id else ""
            lines.append(
                f"{indent}[{node.id}] L{node.level.value}: {node.title}{parent_info}"
            )
        return "\n".join(lines)

    def _parse_level(self, level: int) -> TOCLevel:
        """Parse level integer to enum."""
        if level == 1:
            return TOCLevel.L1
        elif level == 3:
            return TOCLevel.L3
        return TOCLevel.L2

    def get_output_summary(self, output: Stage4Output) -> dict[str, Any]:
        """Get output summary."""
        return {
            "total_nodes": len(output.normalized_toc_nodes),
            "validation_passed": output.validation_passed,
            "issues_fixed": len(output.issues_fixed),
        }
