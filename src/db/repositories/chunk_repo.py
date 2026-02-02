"""Chunk repository for dual-chunk system with vector search."""

from dataclasses import dataclass
from typing import Optional

import numpy as np
import structlog
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.exceptions import StorageError
from src.core.models import GenerationChunk, RetrievalChunk
from src.db.mongodb import Collections

logger = structlog.get_logger()


@dataclass
class ChunkSearchResult:
    """Result from chunk search."""

    retrieval_chunk: RetrievalChunk
    generation_chunk: Optional[GenerationChunk]
    score: float


class ChunkRepository:
    """Repository for retrieval and generation chunks."""

    def __init__(self, database: AsyncIOMotorDatabase):
        """Initialize repository.

        Args:
            database: MongoDB database instance
        """
        self.retrieval_collection = database[Collections.RETRIEVAL_CHUNKS]
        self.generation_collection = database[Collections.GENERATION_CHUNKS]
        self.logger = logger.bind(component="ChunkRepository")

    # ============================================================
    # RETRIEVAL CHUNK OPERATIONS
    # ============================================================

    async def insert_retrieval_chunks(self, chunks: list[RetrievalChunk]) -> int:
        """Insert multiple retrieval chunks.

        Args:
            chunks: List of retrieval chunks

        Returns:
            Number of chunks inserted
        """
        if not chunks:
            return 0

        try:
            docs = []
            for chunk in chunks:
                doc = chunk.model_dump()
                doc["_id"] = chunk.id
                docs.append(doc)

            result = await self.retrieval_collection.insert_many(docs)

            self.logger.info(
                "Retrieval chunks inserted",
                count=len(result.inserted_ids),
            )

            return len(result.inserted_ids)

        except Exception as e:
            self.logger.error("Failed to insert retrieval chunks", error=str(e))
            raise StorageError(f"Failed to insert retrieval chunks: {e}")

    async def get_retrieval_chunk(self, chunk_id: str) -> Optional[RetrievalChunk]:
        """Get retrieval chunk by ID.

        Args:
            chunk_id: Chunk ID

        Returns:
            RetrievalChunk or None
        """
        doc = await self.retrieval_collection.find_one({"_id": chunk_id})

        if doc:
            doc["id"] = doc.pop("_id")
            return RetrievalChunk.model_validate(doc)

        return None

    async def get_retrieval_chunks_by_document(
        self,
        document_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[RetrievalChunk]:
        """Get all retrieval chunks for a document.

        Args:
            document_id: Document ID
            skip: Number to skip
            limit: Maximum to return

        Returns:
            List of retrieval chunks
        """
        cursor = (
            self.retrieval_collection.find({"document_id": document_id})
            .sort("sequence_in_document", 1)
            .skip(skip)
            .limit(limit)
        )

        chunks = []
        async for doc in cursor:
            doc["id"] = doc.pop("_id")
            chunks.append(RetrievalChunk.model_validate(doc))

        return chunks

    async def get_retrieval_chunks_by_toc(
        self,
        toc_node_id: str,
    ) -> list[RetrievalChunk]:
        """Get retrieval chunks for a TOC node.

        Args:
            toc_node_id: TOC node ID

        Returns:
            List of retrieval chunks
        """
        cursor = self.retrieval_collection.find({"toc_node_id": toc_node_id}).sort(
            "sequence_in_toc_node", 1
        )

        chunks = []
        async for doc in cursor:
            doc["id"] = doc.pop("_id")
            chunks.append(RetrievalChunk.model_validate(doc))

        return chunks

    async def update_embedding(
        self,
        chunk_id: str,
        embedding: list[float],
        model: str,
    ) -> bool:
        """Update embedding for a retrieval chunk.

        Args:
            chunk_id: Chunk ID
            embedding: Embedding vector
            model: Model used for embedding

        Returns:
            True if updated
        """
        result = await self.retrieval_collection.update_one(
            {"_id": chunk_id},
            {"$set": {"embedding": embedding, "embedding_model": model}},
        )

        return result.modified_count > 0

    # ============================================================
    # GENERATION CHUNK OPERATIONS
    # ============================================================

    async def insert_generation_chunks(self, chunks: list[GenerationChunk]) -> int:
        """Insert multiple generation chunks.

        Args:
            chunks: List of generation chunks

        Returns:
            Number of chunks inserted
        """
        if not chunks:
            return 0

        try:
            docs = []
            for chunk in chunks:
                doc = chunk.model_dump()
                doc["_id"] = chunk.id
                docs.append(doc)

            result = await self.generation_collection.insert_many(docs)

            self.logger.info(
                "Generation chunks inserted",
                count=len(result.inserted_ids),
            )

            return len(result.inserted_ids)

        except Exception as e:
            self.logger.error("Failed to insert generation chunks", error=str(e))
            raise StorageError(f"Failed to insert generation chunks: {e}")

    async def get_generation_chunk(self, chunk_id: str) -> Optional[GenerationChunk]:
        """Get generation chunk by ID.

        Args:
            chunk_id: Chunk ID

        Returns:
            GenerationChunk or None
        """
        doc = await self.generation_collection.find_one({"_id": chunk_id})

        if doc:
            doc["id"] = doc.pop("_id")
            return GenerationChunk.model_validate(doc)

        return None

    async def get_generation_chunks_by_document(
        self,
        document_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[GenerationChunk]:
        """Get all generation chunks for a document.

        Args:
            document_id: Document ID
            skip: Number to skip
            limit: Maximum to return

        Returns:
            List of generation chunks
        """
        cursor = (
            self.generation_collection.find({"document_id": document_id})
            .sort("sequence_in_document", 1)
            .skip(skip)
            .limit(limit)
        )

        chunks = []
        async for doc in cursor:
            doc["id"] = doc.pop("_id")
            chunks.append(GenerationChunk.model_validate(doc))

        return chunks

    async def get_generation_by_retrieval_id(
        self,
        retrieval_chunk_id: str,
    ) -> Optional[GenerationChunk]:
        """Get generation chunk linked to a retrieval chunk.

        Args:
            retrieval_chunk_id: Retrieval chunk ID

        Returns:
            Linked generation chunk or None
        """
        # First get the retrieval chunk to find linked generation ID
        ret_chunk = await self.get_retrieval_chunk(retrieval_chunk_id)

        if ret_chunk and ret_chunk.generation_chunk_id:
            return await self.get_generation_chunk(ret_chunk.generation_chunk_id)

        return None

    # ============================================================
    # VECTOR SEARCH (MVP: In-Memory Cosine Similarity)
    # ============================================================

    async def vector_search(
        self,
        query_embedding: list[float],
        document_id: Optional[str] = None,
        toc_node_id: Optional[str] = None,
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[ChunkSearchResult]:
        """Search retrieval chunks by vector similarity.

        Args:
            query_embedding: Query embedding vector
            document_id: Optional document filter
            toc_node_id: Optional TOC node filter
            top_k: Number of results
            min_score: Minimum similarity score

        Returns:
            List of search results with scores
        """
        # Build query
        query = {"embedding": {"$exists": True, "$ne": None}}

        if document_id:
            query["document_id"] = document_id

        if toc_node_id:
            query["toc_node_id"] = toc_node_id

        # Load all matching chunks with embeddings
        cursor = self.retrieval_collection.find(query)

        chunks_with_scores = []
        query_vec = np.array(query_embedding)
        query_norm = np.linalg.norm(query_vec)

        if query_norm == 0:
            return []

        async for doc in cursor:
            embedding = doc.get("embedding")

            if not embedding:
                continue

            # Calculate cosine similarity
            emb_vec = np.array(embedding)
            emb_norm = np.linalg.norm(emb_vec)

            if emb_norm == 0:
                continue

            similarity = float(np.dot(query_vec, emb_vec) / (query_norm * emb_norm))

            if similarity >= min_score:
                doc["id"] = doc.pop("_id")
                chunk = RetrievalChunk.model_validate(doc)
                chunks_with_scores.append((chunk, similarity))

        # Sort by score descending
        chunks_with_scores.sort(key=lambda x: x[1], reverse=True)

        # Get top_k results with generation chunks
        results = []

        for chunk, score in chunks_with_scores[:top_k]:
            gen_chunk = await self.get_generation_chunk(chunk.generation_chunk_id)

            results.append(
                ChunkSearchResult(
                    retrieval_chunk=chunk,
                    generation_chunk=gen_chunk,
                    score=score,
                )
            )

        self.logger.info(
            "Vector search complete",
            query_length=len(query_embedding),
            results=len(results),
            top_score=results[0].score if results else 0,
        )

        return results

    # ============================================================
    # DELETE OPERATIONS
    # ============================================================

    async def delete_by_document(self, document_id: str) -> tuple[int, int]:
        """Delete all chunks for a document.

        Args:
            document_id: Document ID

        Returns:
            Tuple of (retrieval_deleted, generation_deleted)
        """
        ret_result = await self.retrieval_collection.delete_many(
            {"document_id": document_id}
        )
        gen_result = await self.generation_collection.delete_many(
            {"document_id": document_id}
        )

        self.logger.info(
            "Chunks deleted",
            document_id=document_id,
            retrieval=ret_result.deleted_count,
            generation=gen_result.deleted_count,
        )

        return ret_result.deleted_count, gen_result.deleted_count

    # ============================================================
    # COUNT OPERATIONS
    # ============================================================

    async def count_by_document(self, document_id: str) -> dict[str, int]:
        """Count chunks for a document.

        Args:
            document_id: Document ID

        Returns:
            Dictionary with retrieval and generation counts
        """
        ret_count = await self.retrieval_collection.count_documents(
            {"document_id": document_id}
        )
        gen_count = await self.generation_collection.count_documents(
            {"document_id": document_id}
        )

        return {
            "retrieval": ret_count,
            "generation": gen_count,
        }
