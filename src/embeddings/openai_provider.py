"""OpenAI embedding provider."""

from typing import Optional

import numpy as np
import structlog
from openai import APIError, APITimeoutError, AsyncOpenAI, RateLimitError
from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                      wait_exponential)

from src.core.config import Settings, get_settings
from src.core.exceptions import EmbeddingError, LLMRateLimitError

logger = structlog.get_logger()


class OpenAIEmbeddingProvider:
    """OpenAI embedding provider using text-embedding-3-small."""

    BATCH_SIZE = 100  # Process in batches to avoid rate limits

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize embedding provider.

        Args:
            settings: Application settings
        """
        self.settings = settings or get_settings()
        self.client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        self.model = self.settings.embedding_model
        self.dimensions = self.settings.embedding_dimensions
        self.logger = logger.bind(component="EmbeddingProvider")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((LLMRateLimitError,)),
    )
    async def embed_single(self, text: str) -> list[float]:
        """Generate embedding for single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector

        Raises:
            EmbeddingError: If embedding fails
        """
        if not text.strip():
            # Return zero vector for empty text
            return [0.0] * self.dimensions

        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=text,
                dimensions=self.dimensions,
            )

            return response.data[0].embedding

        except RateLimitError as e:
            raise LLMRateLimitError(f"Rate limit exceeded: {e}")
        except APITimeoutError as e:
            raise EmbeddingError(f"API timeout: {e}")
        except APIError as e:
            raise EmbeddingError(f"Embedding API error: {e}")

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors

        Raises:
            EmbeddingError: If embedding fails
        """
        if not texts:
            return []

        self.logger.info("Embedding batch", count=len(texts))

        all_embeddings = []

        # Process in batches
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]

            # Filter empty texts and track indices
            non_empty_texts = []
            non_empty_indices = []
            empty_indices = []

            for j, text in enumerate(batch):
                if text.strip():
                    non_empty_texts.append(text)
                    non_empty_indices.append(j)
                else:
                    empty_indices.append(j)

            # Get embeddings for non-empty texts
            batch_embeddings = [None] * len(batch)

            if non_empty_texts:
                try:
                    response = await self.client.embeddings.create(
                        model=self.model,
                        input=non_empty_texts,
                        dimensions=self.dimensions,
                    )

                    for idx, emb_data in zip(non_empty_indices, response.data):
                        batch_embeddings[idx] = emb_data.embedding

                except RateLimitError as e:
                    raise LLMRateLimitError(f"Rate limit exceeded: {e}")
                except APIError as e:
                    raise EmbeddingError(f"Embedding API error: {e}")

            # Fill empty texts with zero vectors
            zero_vector = [0.0] * self.dimensions
            for idx in empty_indices:
                batch_embeddings[idx] = zero_vector

            all_embeddings.extend(batch_embeddings)

            self.logger.debug(
                "Batch complete",
                batch_num=i // self.BATCH_SIZE + 1,
                total_batches=(len(texts) + self.BATCH_SIZE - 1) // self.BATCH_SIZE,
            )

        return all_embeddings

    async def embed_query(self, query: str) -> list[float]:
        """Embed search query.

        This is the same as embed_single but semantically distinct
        for potential future query-specific optimizations.

        Args:
            query: Search query

        Returns:
            Query embedding vector
        """
        return await self.embed_single(query)

    def cosine_similarity(
        self, embedding1: list[float], embedding2: list[float]
    ) -> float:
        """Calculate cosine similarity between two embeddings.

        Args:
            embedding1: First embedding
            embedding2: Second embedding

        Returns:
            Cosine similarity score (0-1)
        """
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)

        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))

    def find_similar(
        self,
        query_embedding: list[float],
        embeddings: list[list[float]],
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[tuple[int, float]]:
        """Find most similar embeddings to query.

        Args:
            query_embedding: Query embedding vector
            embeddings: List of embeddings to search
            top_k: Number of results to return
            min_score: Minimum similarity score threshold

        Returns:
            List of (index, score) tuples, sorted by score descending
        """
        if not embeddings:
            return []

        query_vec = np.array(query_embedding)
        query_norm = np.linalg.norm(query_vec)

        if query_norm == 0:
            return []

        scores = []

        for i, embedding in enumerate(embeddings):
            emb_vec = np.array(embedding)
            emb_norm = np.linalg.norm(emb_vec)

            if emb_norm == 0:
                continue

            similarity = float(np.dot(query_vec, emb_vec) / (query_norm * emb_norm))

            if similarity >= min_score:
                scores.append((i, similarity))

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)

        return scores[:top_k]

    async def get_token_count(self, text: str) -> int:
        """Estimate token count for text.

        Args:
            text: Text to count

        Returns:
            Estimated token count
        """
        import tiktoken

        try:
            encoding = tiktoken.encoding_for_model(self.model)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")

        return len(encoding.encode(text))
