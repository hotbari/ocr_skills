"""FastAPI dependencies for dependency injection."""

from functools import lru_cache
from typing import AsyncGenerator

from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.config import Settings, get_settings
from src.db.mongodb import MongoDB
from src.db.repositories.chunk_repo import ChunkRepository
from src.db.repositories.document_repo import DocumentRepository
from src.db.repositories.entity_repo import EntityRepository
from src.db.repositories.toc_repo import TOCRepository
from src.embeddings.openai_provider import OpenAIEmbeddingProvider
from src.pipeline.orchestrator import PipelineOrchestrator


def get_db() -> AsyncIOMotorDatabase:
    """Get database instance."""
    return MongoDB.get_database()


def get_document_repo() -> DocumentRepository:
    """Get document repository."""
    return DocumentRepository(get_db())


def get_toc_repo() -> TOCRepository:
    """Get TOC repository."""
    return TOCRepository(get_db())


def get_chunk_repo() -> ChunkRepository:
    """Get chunk repository."""
    return ChunkRepository(get_db())


def get_entity_repo() -> EntityRepository:
    """Get entity repository."""
    return EntityRepository(get_db())


@lru_cache()
def get_embedding_provider() -> OpenAIEmbeddingProvider:
    """Get embedding provider (cached)."""
    return OpenAIEmbeddingProvider(get_settings())


def get_orchestrator() -> PipelineOrchestrator:
    """Get pipeline orchestrator."""
    return PipelineOrchestrator(
        document_repo=get_document_repo(),
        toc_repo=get_toc_repo(),
        chunk_repo=get_chunk_repo(),
        entity_repo=get_entity_repo(),
        settings=get_settings(),
    )
