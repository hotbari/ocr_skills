"""Pytest fixtures for testing the RAG VectorDB PDF Pipeline."""

import asyncio
import json
import os
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from src.core.config import Settings, reset_settings
from src.core.models import (Document, DocumentMetadata, DocumentStatus,
                             Language, TOCLevel)
from src.db.repositories.chunk_repo import ChunkRepository
from src.db.repositories.document_repo import DocumentRepository
from src.db.repositories.entity_repo import EntityRepository
from src.db.repositories.toc_repo import TOCRepository
from src.embeddings.openai_provider import OpenAIEmbeddingProvider
from src.llm.openai_client import OpenAIClient
from src.llm.vision_client import VisionClient
from src.ocr.extractor import PDFExtractor

# ============================================================
# EVENT LOOP CONFIGURATION
# ============================================================


@pytest.fixture(scope="session")
def event_loop_policy():
    """Set event loop policy for Windows compatibility."""
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


@pytest.fixture(scope="session")
def event_loop(event_loop_policy):
    """Create event loop for tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ============================================================
# SETTINGS AND CONFIGURATION
# ============================================================


@pytest.fixture
def mock_settings(tmp_path: Path) -> Settings:
    """Create mock settings for testing."""
    reset_settings()

    # Create temp directories
    upload_dir = tmp_path / "uploads"
    pipeline_state_dir = tmp_path / "pipeline_state"
    upload_dir.mkdir()
    pipeline_state_dir.mkdir()

    settings = Settings(
        openai_api_key="test-key-123",
        openai_model="gpt-4o-mini",
        vision_model="gpt-4o",
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
        mongodb_uri="mongodb://localhost:27017",
        mongodb_database="test_rag_vectordb",
        max_chunk_tokens=1000,
        retrieval_chunk_min_tokens=100,
        retrieval_chunk_max_tokens=300,
        generation_chunk_min_tokens=500,
        generation_chunk_max_tokens=1500,
        pipeline_state_dir=pipeline_state_dir,
        upload_dir=upload_dir,
        api_host="0.0.0.0",
        api_port=8000,
        debug=True,
        max_file_size_mb=50,
        max_pages=500,
    )

    return settings


# ============================================================
# DATABASE FIXTURES
# ============================================================


@pytest_asyncio.fixture
async def mock_db() -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    """Create mock MongoDB database using mongomock."""
    # For this MVP, we'll use a real motor client with test database
    # In production tests, you could use mongomock-motor for mocking
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["test_rag_vectordb"]

    # Clean collections before test
    await db.documents.delete_many({})
    await db.toc_nodes.delete_many({})
    await db.retrieval_chunks.delete_many({})
    await db.generation_chunks.delete_many({})
    await db.entities.delete_many({})

    yield db

    # Cleanup after test
    await db.documents.delete_many({})
    await db.toc_nodes.delete_many({})
    await db.retrieval_chunks.delete_many({})
    await db.generation_chunks.delete_many({})
    await db.entities.delete_many({})

    client.close()


# ============================================================
# REPOSITORY FIXTURES
# ============================================================


@pytest_asyncio.fixture
async def mock_db_for_repos() -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    """Create mock MongoDB database for repository testing."""
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["test_rag_vectordb"]

    # Clean collections before test
    await db.documents.delete_many({})
    await db.toc_nodes.delete_many({})
    await db.retrieval_chunks.delete_many({})
    await db.generation_chunks.delete_many({})
    await db.entities.delete_many({})

    yield db

    # Cleanup after test
    await db.documents.delete_many({})
    await db.toc_nodes.delete_many({})
    await db.retrieval_chunks.delete_many({})
    await db.generation_chunks.delete_many({})
    await db.entities.delete_many({})

    client.close()


@pytest_asyncio.fixture
async def document_repo(mock_db_for_repos: AsyncIOMotorDatabase) -> DocumentRepository:
    """Create document repository with mock database."""
    return DocumentRepository(mock_db_for_repos)


@pytest_asyncio.fixture
async def toc_repo(mock_db_for_repos: AsyncIOMotorDatabase) -> TOCRepository:
    """Create TOC repository with mock database."""
    return TOCRepository(mock_db_for_repos)


@pytest_asyncio.fixture
async def chunk_repo(mock_db_for_repos: AsyncIOMotorDatabase) -> ChunkRepository:
    """Create chunk repository with mock database."""
    return ChunkRepository(mock_db_for_repos)


@pytest_asyncio.fixture
async def entity_repo(mock_db_for_repos: AsyncIOMotorDatabase) -> EntityRepository:
    """Create entity repository with mock database."""
    return EntityRepository(mock_db_for_repos)


# ============================================================
# MOCK CLIENTS
# ============================================================


@pytest.fixture
def mock_openai_client(mock_settings: Settings) -> OpenAIClient:
    """Create mock OpenAI client."""
    client = OpenAIClient(mock_settings)
    client.client = MagicMock()

    # Mock structured output call
    async def mock_parse(*args, **kwargs):
        mock_response = MagicMock()
        mock_response.parsed = MagicMock()
        return mock_response

    client.client.beta.chat.completions.parse = AsyncMock(side_effect=mock_parse)

    return client


@pytest.fixture
def mock_vision_client(mock_settings: Settings) -> VisionClient:
    """Create mock Vision client."""
    client = VisionClient(mock_settings)
    client.client = MagicMock()

    async def mock_describe(*args, **kwargs):
        return "A test image showing some content."

    client.describe_image = AsyncMock(side_effect=mock_describe)

    return client


@pytest.fixture
def mock_embedding_provider(mock_settings: Settings) -> OpenAIEmbeddingProvider:
    """Create mock embedding provider."""
    provider = OpenAIEmbeddingProvider(mock_settings)
    provider.client = MagicMock()

    async def mock_embed_query(text: str):
        # Return deterministic mock embedding based on text length
        return [0.1] * 1536

    async def mock_embed_batch(texts: list[str]):
        return [[0.1] * 1536 for _ in texts]

    provider.embed_query = AsyncMock(side_effect=mock_embed_query)
    provider.embed_batch = AsyncMock(side_effect=mock_embed_batch)

    return provider


# ============================================================
# PDF FIXTURES
# ============================================================


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Create a sample PDF file for testing."""
    pdf_path = tmp_path / "test_document.pdf"

    # Create simple PDF with reportlab
    c = canvas.Canvas(str(pdf_path), pagesize=letter)

    # Page 1
    c.drawString(100, 750, "Chapter 1: Introduction")
    c.drawString(100, 700, "This is the introduction section.")
    c.drawString(100, 650, "It contains some sample text for testing.")
    c.showPage()

    # Page 2
    c.drawString(100, 750, "Chapter 2: Methods")
    c.drawString(100, 700, "This section describes the methodology.")
    c.drawString(100, 650, "More detailed content goes here.")
    c.showPage()

    c.save()

    return pdf_path


@pytest.fixture
def empty_pdf(tmp_path: Path) -> Path:
    """Create an empty PDF file for testing."""
    pdf_path = tmp_path / "empty.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    c.showPage()
    c.save()
    return pdf_path


@pytest.fixture
def large_pdf(tmp_path: Path, mock_settings: Settings) -> Path:
    """Create a PDF that exceeds size limits."""
    pdf_path = tmp_path / "large.pdf"

    c = canvas.Canvas(str(pdf_path), pagesize=letter)

    # Create many pages to exceed limit
    for i in range(mock_settings.max_pages + 10):
        c.drawString(100, 750, f"Page {i + 1}")
        c.showPage()

    c.save()

    return pdf_path


# ============================================================
# SAMPLE DATA FIXTURES
# ============================================================


@pytest.fixture
def sample_document() -> Document:
    """Create a sample document for testing."""
    return Document(
        id="test-doc-123",
        filename="test.pdf",
        original_filename="test.pdf",
        file_path="/tmp/test.pdf",
        status=DocumentStatus.UPLOADED,
        metadata=DocumentMetadata(
            title="Test Document",
            author="Test Author",
            page_count=10,
            file_size_bytes=1024,
            detected_language=Language.ENGLISH,
        ),
    )


@pytest.fixture
def sample_raw_text() -> str:
    """Sample raw text extracted from PDF."""
    return """
Chapter 1: Introduction

This is the introduction section. It provides an overview of the document.
We will cover several important topics in the following chapters.

Key concepts:
- Concept A: This is an important concept.
- Concept B: Another crucial concept.
- Concept C: A third essential concept.

Chapter 2: Methodology

This section describes the approach used in this work.
We employ several techniques to achieve our goals.

The process consists of three main stages:
1. Data collection
2. Data processing
3. Analysis and interpretation

Chapter 3: Results

The results show significant improvements.
We observed the following outcomes:
- Result 1: Positive impact
- Result 2: Enhanced performance
- Result 3: Better accuracy
"""


@pytest.fixture
def sample_segments() -> list[dict]:
    """Sample segments from Stage 1 segmentation."""
    return [
        {
            "segment_id": 1,
            "content": "This is the introduction section.",
            "page_number": 1,
            "semantic_type": "explanation",
            "key_concepts": ["introduction", "overview"],
            "reasoning": "Introductory paragraph",
        },
        {
            "segment_id": 2,
            "content": "Concept A: This is an important concept.",
            "page_number": 1,
            "semantic_type": "definition",
            "key_concepts": ["concept A", "definition"],
            "reasoning": "Defines a key concept",
        },
        {
            "segment_id": 3,
            "content": "This section describes the approach.",
            "page_number": 2,
            "semantic_type": "explanation",
            "key_concepts": ["methodology", "approach"],
            "reasoning": "Explains methodology",
        },
    ]


@pytest.fixture
def sample_embeddings() -> list[float]:
    """Sample embedding vector for testing."""
    # Return 1536-dimensional embedding
    return [0.1 + (i * 0.001) for i in range(1536)]


# ============================================================
# MOCK PDF EXTRACTOR
# ============================================================


@pytest.fixture
def mock_pdf_extractor(mock_settings: Settings) -> PDFExtractor:
    """Create mock PDF extractor."""
    from src.ocr.extractor import ExtractionResult

    extractor = PDFExtractor(mock_settings)

    async def mock_extract(pdf_path: Path, document_id: str):
        return ExtractionResult(
            document_id=document_id,
            raw_text="Test extracted text from PDF.",
            page_count=2,
            text_by_page=[
                MagicMock(page_number=1, content="Page 1 text", char_count=11),
                MagicMock(page_number=2, content="Page 2 text", char_count=11),
            ],
            tables=[],
            images=[],
            metadata={"title": "Test PDF", "page_count": 2},
            detected_language=Language.ENGLISH,
            is_scanned=False,
        )

    extractor.extract = AsyncMock(side_effect=mock_extract)

    return extractor


# ============================================================
# MOCK ORCHESTRATOR
# ============================================================


@pytest.fixture
def mock_orchestrator(
    mock_settings: Settings, document_repo, toc_repo, chunk_repo, entity_repo
):
    """Create mock pipeline orchestrator."""
    from src.pipeline.orchestrator import PipelineOrchestrator

    orchestrator = PipelineOrchestrator(
        document_repo=document_repo,
        toc_repo=toc_repo,
        chunk_repo=chunk_repo,
        entity_repo=entity_repo,
        settings=mock_settings,
    )

    # Mock the run_pipeline method
    async def mock_run_pipeline(
        document_id: str,
        pdf_path: Path,
        skip_vision: bool = False,
        force_restart: bool = False,
    ):
        """Mock pipeline execution."""
        # Update document status to processing
        doc = await document_repo.get(document_id)
        if doc:
            doc.status = DocumentStatus.PROCESSING
            await document_repo.update(doc)

    orchestrator.run_pipeline = AsyncMock(side_effect=mock_run_pipeline)

    return orchestrator


# ============================================================
# CLEANUP FIXTURES
# ============================================================


@pytest.fixture(autouse=True)
def cleanup_test_files(tmp_path: Path):
    """Automatically cleanup test files after each test."""
    yield
    # Cleanup happens automatically with tmp_path
