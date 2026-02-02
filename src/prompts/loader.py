"""Prompt template loader."""

from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger()


class PromptLoader:
    """Loads and formats prompt templates."""

    def __init__(self, template_dir: Optional[Path] = None):
        """Initialize prompt loader.

        Args:
            template_dir: Directory containing prompt templates
        """
        if template_dir is None:
            # Default to src/prompts/templates
            template_dir = Path(__file__).parent / "templates"

        self.template_dir = template_dir
        self.logger = logger.bind(component="PromptLoader")
        self._cache: dict[str, str] = {}

    def load(self, template_name: str, **kwargs) -> str:
        """Load and format a template.

        Args:
            template_name: Template filename (without .txt extension)
            **kwargs: Variables to substitute in template

        Returns:
            Formatted template string

        Raises:
            FileNotFoundError: If template doesn't exist
        """
        # Check cache
        if template_name not in self._cache:
            template_path = self.template_dir / f"{template_name}.txt"

            if not template_path.exists():
                raise FileNotFoundError(f"Template not found: {template_path}")

            with open(template_path, "r", encoding="utf-8") as f:
                self._cache[template_name] = f.read()

        template = self._cache[template_name]

        # Format with kwargs
        if kwargs:
            try:
                template = template.format(**kwargs)
            except KeyError as e:
                self.logger.warning(
                    "Missing template variable",
                    template=template_name,
                    missing=str(e),
                )

        return template

    def get_system_prompt(self, stage: str) -> str:
        """Get system prompt for a pipeline stage.

        Args:
            stage: Stage name (e.g., "stage1_segmentation")

        Returns:
            System prompt string
        """
        return self.load(stage)

    def get_user_prompt(self, stage: str, **data) -> str:
        """Get user prompt for a pipeline stage.

        Args:
            stage: Stage name
            **data: Data to include in prompt

        Returns:
            User prompt string
        """
        template_name = f"{stage}_user"

        try:
            return self.load(template_name, **data)
        except FileNotFoundError:
            # If no separate user template, format data directly
            return self._format_data_for_prompt(data)

    def _format_data_for_prompt(self, data: dict) -> str:
        """Format data dictionary as prompt text.

        Args:
            data: Data dictionary

        Returns:
            Formatted string
        """
        parts = []

        for key, value in data.items():
            if isinstance(value, list):
                if value and isinstance(value[0], dict):
                    # List of dicts - format as numbered items
                    items = []
                    for i, item in enumerate(value):
                        item_str = ", ".join(f"{k}: {v}" for k, v in item.items())
                        items.append(f"{i + 1}. {item_str}")
                    parts.append(f"{key}:\n" + "\n".join(items))
                else:
                    parts.append(f"{key}: {', '.join(str(v) for v in value)}")
            elif isinstance(value, dict):
                items = [f"  {k}: {v}" for k, v in value.items()]
                parts.append(f"{key}:\n" + "\n".join(items))
            else:
                parts.append(f"{key}: {value}")

        return "\n\n".join(parts)

    def clear_cache(self) -> None:
        """Clear template cache."""
        self._cache.clear()


# Singleton instance
_loader: Optional[PromptLoader] = None


def get_prompt_loader() -> PromptLoader:
    """Get cached prompt loader instance."""
    global _loader
    if _loader is None:
        _loader = PromptLoader()
    return _loader
