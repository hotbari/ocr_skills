"""Stage 7: Embedding Generation."""

from dataclasses import dataclass
from typing import Any

from src.core.models import PipelineStage, RetrievalChunk
from src.embeddings.openai_provider import OpenAIEmbeddingProvider
from src.pipeline.base import BaseStage


@dataclass
class Stage7Input:
    """Input for Stage 7."""

    document_id: str
    retrieval_chunks: list[RetrievalChunk]


@dataclass
class Stage7Output:
    """Output from Stage 7."""

    document_id: str
    embedded_chunks: list[RetrievalChunk]
    total_embedded: int
    embedding_model: str


class Stage7Embedding(BaseStage[Stage7Input, Stage7Output]):
    """Stage 7: Generate embeddings for retrieval chunks."""

    stage = PipelineStage.STAGE_7_EMBEDDING
    stage_name = "embedding"

    def __init__(self, embedding_provider: OpenAIEmbeddingProvider):
        """Initialize stage.

        Args:
            embedding_provider: Embedding provider
        """
        super().__init__()
        self.embedding_provider = embedding_provider

    def validate_input(self, input_data: Stage7Input) -> bool:
        """Validate input."""
        return bool(input_data.document_id and input_data.retrieval_chunks)

    def validate_output(self, output_data: Stage7Output) -> bool:
        """Validate output."""
        return output_data.total_embedded > 0

    async def execute(self, input_data: Stage7Input) -> Stage7Output:
        """Generate embeddings for all retrieval chunks.

        Args:
            input_data: Stage input

        Returns:
            Chunks with embeddings
        """
        self.logger.info(
            "Generating embeddings",
            document_id=input_data.document_id,
            chunk_count=len(input_data.retrieval_chunks),
        )

        # Extract texts for batch embedding
        texts = [chunk.content for chunk in input_data.retrieval_chunks]

        # Generate embeddings in batch
        embeddings = await self.embedding_provider.embed_batch(texts)

        # Attach embeddings to chunks
        embedded_chunks = []
        for chunk, embedding in zip(input_data.retrieval_chunks, embeddings):
            chunk.embedding = embedding
            chunk.embedding_model = self.embedding_provider.model
            embedded_chunks.append(chunk)

        return Stage7Output(
            document_id=input_data.document_id,
            embedded_chunks=embedded_chunks,
            total_embedded=len(embedded_chunks),
            embedding_model=self.embedding_provider.model,
        )

    def get_output_summary(self, output: Stage7Output) -> dict[str, Any]:
        """Get output summary."""
        return {
            "total_embedded": output.total_embedded,
            "embedding_model": output.embedding_model,
            "embedding_dimensions": (
                len(output.embedded_chunks[0].embedding)
                if output.embedded_chunks and output.embedded_chunks[0].embedding
                else 0
            ),
        }
