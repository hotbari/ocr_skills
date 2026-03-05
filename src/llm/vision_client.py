"""Vision client for image analysis using GPT-4o."""

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import structlog
from openai import APIError, APITimeoutError, AsyncOpenAI, RateLimitError

from src.core.config import Settings, get_settings
from src.core.exceptions import LLMError, LLMRateLimitError, LLMTimeoutError

logger = structlog.get_logger()


@dataclass
class ImageDescription:
    """Result of image analysis."""

    description: str
    key_elements: list[str]
    image_type: str  # diagram, chart, photo, table, etc.
    data_extracted: Optional[dict] = None


@dataclass
class DiagramIR:
    """Intermediate representation for diagrams."""

    diagram_type: str  # flowchart, state_diagram, sequence, etc.
    nodes: list[dict]
    edges: list[dict]
    description: str


class VisionClient:
    """GPT-4o Vision client for image analysis."""

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize vision client.

        Args:
            settings: Application settings
        """
        self.settings = settings or get_settings()
        self.client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        self.logger = logger.bind(component="VisionClient")

    async def describe_image(
        self,
        image_path: Optional[Path] = None,
        image_base64: Optional[str] = None,
        context: str = "",
        detail: str = "high",
    ) -> ImageDescription:
        """Analyze and describe an image.

        Args:
            image_path: Path to image file
            image_base64: Base64 encoded image data
            context: Surrounding text context
            detail: Image detail level (low, high, auto)

        Returns:
            ImageDescription with analysis results

        Raises:
            LLMError: If analysis fails
        """
        if not image_path and not image_base64:
            raise ValueError("Either image_path or image_base64 must be provided")

        # Encode image
        if image_path:
            image_data = self._encode_image(image_path)
            image_format = image_path.suffix.lower().replace(".", "")
            if image_format == "jpg":
                image_format = "jpeg"
        else:
            image_data = image_base64
            image_format = "png"  # Assume PNG if not specified

        system_prompt = """You are an expert at analyzing images from technical documents.
Analyze the provided image and return a JSON response with:
1. description: A detailed description of what the image shows
2. key_elements: A list of important elements or concepts shown
3. image_type: The type of image (diagram, flowchart, chart, table, photo, illustration, etc.)
4. data_extracted: If the image contains data (like a chart or table), extract it as structured data

Be thorough but concise. Focus on information that would be useful for document understanding and retrieval."""

        user_content = []

        if context:
            user_content.append(
                {
                    "type": "text",
                    "text": f"Context from surrounding document text:\n{context}\n\nAnalyze this image:",
                }
            )

        user_content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/{image_format};base64,{image_data}",
                    "detail": detail,
                },
            }
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.settings.vision_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                max_tokens=1000,
            )

            content = response.choices[0].message.content

            if not content:
                raise LLMError("Empty response from vision model")

            import json

            data = json.loads(content)

            return ImageDescription(
                description=data.get("description", ""),
                key_elements=data.get("key_elements", []),
                image_type=data.get("image_type", "unknown"),
                data_extracted=data.get("data_extracted"),
            )

        except RateLimitError as e:
            raise LLMRateLimitError(f"Rate limit exceeded: {e}")
        except APITimeoutError as e:
            raise LLMTimeoutError(f"API timeout: {e}")
        except APIError as e:
            raise LLMError(f"Vision API error: {e}")

    async def extract_diagram_ir(
        self,
        image_path: Optional[Path] = None,
        image_base64: Optional[str] = None,
        context: str = "",
    ) -> DiagramIR:
        """Extract intermediate representation from a diagram.

        Args:
            image_path: Path to image file
            image_base64: Base64 encoded image data
            context: Surrounding text context

        Returns:
            DiagramIR with structured representation

        Raises:
            LLMError: If extraction fails
        """
        if not image_path and not image_base64:
            raise ValueError("Either image_path or image_base64 must be provided")

        if image_path:
            image_data = self._encode_image(image_path)
            image_format = image_path.suffix.lower().replace(".", "")
            if image_format == "jpg":
                image_format = "jpeg"
        else:
            image_data = image_base64
            image_format = "png"

        system_prompt = """You are an expert at analyzing diagrams and flowcharts.
Extract a structured representation of the diagram and return a JSON object with:
1. diagram_type: The type (flowchart, state_diagram, sequence_diagram, entity_relationship, process_flow, etc.)
2. nodes: List of nodes/boxes with {id, label, type}
3. edges: List of connections with {from, to, label, condition}
4. description: A text description of what the diagram represents

This will be used to create a searchable text representation of the diagram."""

        user_content = []

        if context:
            user_content.append(
                {
                    "type": "text",
                    "text": f"Context:\n{context}\n\nExtract structure from this diagram:",
                }
            )

        user_content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/{image_format};base64,{image_data}",
                    "detail": "high",
                },
            }
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.settings.vision_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                max_tokens=2000,
            )

            content = response.choices[0].message.content

            if not content:
                raise LLMError("Empty response from vision model")

            import json

            data = json.loads(content)

            return DiagramIR(
                diagram_type=data.get("diagram_type", "unknown"),
                nodes=data.get("nodes", []),
                edges=data.get("edges", []),
                description=data.get("description", ""),
            )

        except RateLimitError as e:
            raise LLMRateLimitError(f"Rate limit exceeded: {e}")
        except APITimeoutError as e:
            raise LLMTimeoutError(f"API timeout: {e}")
        except APIError as e:
            raise LLMError(f"Vision API error: {e}")

    async def classify_image(
        self,
        image_path: Optional[Path] = None,
        image_base64: Optional[str] = None,
    ) -> str:
        """Classify image type.

        Args:
            image_path: Path to image file
            image_base64: Base64 encoded image data

        Returns:
            Image type classification

        Raises:
            LLMError: If classification fails
        """
        if not image_path and not image_base64:
            raise ValueError("Either image_path or image_base64 must be provided")

        if image_path:
            image_data = self._encode_image(image_path)
            image_format = image_path.suffix.lower().replace(".", "")
            if image_format == "jpg":
                image_format = "jpeg"
        else:
            image_data = image_base64
            image_format = "png"

        system_prompt = """Classify this image into one of these categories:
- flowchart: Process flows, decision trees
- state_diagram: State machines, transitions
- sequence_diagram: Sequence of interactions
- entity_relationship: ER diagrams, data models
- architecture: System architecture, component diagrams
- chart: Bar charts, line charts, pie charts
- table: Tabular data
- photo: Photographs
- illustration: Drawings, icons, decorative images
- screenshot: UI screenshots
- other: Anything else

Respond with just the category name."""

        user_content = [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/{image_format};base64,{image_data}",
                    "detail": "low",
                },
            }
        ]

        try:
            response = await self.client.chat.completions.create(
                model=self.settings.vision_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=50,
            )

            content = response.choices[0].message.content
            return content.strip().lower() if content else "other"

        except Exception as e:
            self.logger.warning("Image classification failed", error=str(e))
            return "other"

    def _encode_image(self, image_path: Path) -> str:
        """Encode image file to base64.

        Args:
            image_path: Path to image file

        Returns:
            Base64 encoded string
        """
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def diagram_ir_to_yaml(self, ir: DiagramIR) -> str:
        """Convert DiagramIR to YAML string.

        Args:
            ir: Diagram intermediate representation

        Returns:
            YAML formatted string
        """
        import yaml

        data = {
            "type": ir.diagram_type,
            "description": ir.description,
            "nodes": ir.nodes,
            "edges": ir.edges,
        }

        return yaml.dump(data, default_flow_style=False, allow_unicode=True)

    def diagram_ir_to_text(self, ir: DiagramIR) -> str:
        """Convert DiagramIR to searchable text.

        Args:
            ir: Diagram intermediate representation

        Returns:
            Plain text description for search
        """
        parts = [f"Diagram type: {ir.diagram_type}", ir.description]

        if ir.nodes:
            node_labels = [n.get("label", "") for n in ir.nodes if n.get("label")]
            if node_labels:
                parts.append(f"Components: {', '.join(node_labels)}")

        if ir.edges:
            transitions = []
            for edge in ir.edges:
                from_node = edge.get("from", "")
                to_node = edge.get("to", "")
                label = edge.get("label", "")
                condition = edge.get("condition", "")

                t = f"{from_node} → {to_node}"
                if label:
                    t += f" ({label})"
                if condition:
                    t += f" when {condition}"
                transitions.append(t)

            if transitions:
                parts.append("Transitions: " + "; ".join(transitions))

        return ". ".join(parts)
