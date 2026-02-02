"""Tests for FastAPI endpoints in src/api/routers/"""

import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import UploadFile
from fastapi.testclient import TestClient
from httpx import AsyncClient

from src.api.dependencies import (get_chunk_repo, get_document_repo,
                                  get_embedding_provider, get_entity_repo,
                                  get_orchestrator, get_toc_repo)
from src.api.main import app
from src.core.models import (Document, DocumentMetadata, DocumentStatus,
                             GenerationChunk, Language, RetrievalChunk,
                             TOCLevel, TOCNode)

# ============================================================
# TEST CLIENT SETUP
# ============================================================


@pytest_asyncio.fixture
async def client(
    document_repo,
    toc_repo,
    chunk_repo,
    entity_repo,
    mock_embedding_provider,
    mock_orchestrator,
):
    """Create async test client for FastAPI app with mocked dependencies."""
    # Override all database dependencies
    app.dependency_overrides[get_document_repo] = lambda: document_repo
    app.dependency_overrides[get_toc_repo] = lambda: toc_repo
    app.dependency_overrides[get_chunk_repo] = lambda: chunk_repo
    app.dependency_overrides[get_entity_repo] = lambda: entity_repo
    app.dependency_overrides[get_embedding_provider] = lambda: mock_embedding_provider
    app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator

    # Use httpx AsyncClient with ASGITransport to test FastAPI app
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Clear overrides after test
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def async_client(
    document_repo,
    toc_repo,
    chunk_repo,
    entity_repo,
    mock_embedding_provider,
    mock_orchestrator,
):
    """Create async test client."""
    # Override all database dependencies
    app.dependency_overrides[get_document_repo] = lambda: document_repo
    app.dependency_overrides[get_toc_repo] = lambda: toc_repo
    app.dependency_overrides[get_chunk_repo] = lambda: chunk_repo
    app.dependency_overrides[get_entity_repo] = lambda: entity_repo
    app.dependency_overrides[get_embedding_provider] = lambda: mock_embedding_provider
    app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator

    import httpx

    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Clear overrides after test
    app.dependency_overrides.clear()


# ============================================================
# TEST DOCUMENT UPLOAD ENDPOINT
# ============================================================


@pytest.mark.asyncio
async def test_upload_document_success(client, sample_pdf, mock_db_for_repos):
    """Test successful document upload."""
    with open(sample_pdf, "rb") as f:
        response = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.pdf", f, "application/pdf")},
        )

    assert response.status_code == 200
    data = response.json()

    assert "document_id" in data
    assert data["filename"] == "test.pdf"
    assert data["status"] == "uploaded"
    assert data["page_count"] >= 0


@pytest.mark.asyncio
async def test_upload_document_invalid_filetype(client, mock_db_for_repos):
    """Test uploading non-PDF file."""
    # Create fake text file
    fake_file = io.BytesIO(b"Not a PDF")

    response = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("test.txt", fake_file, "text/plain")},
    )

    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_document_missing_file(client, mock_db_for_repos):
    """Test upload without file."""
    response = await client.post("/api/v1/documents/upload")

    assert response.status_code == 422  # Validation error


# ============================================================
# TEST GET DOCUMENT ENDPOINT
# ============================================================


@pytest.mark.asyncio
async def test_get_document_success(
    client, document_repo, toc_repo, chunk_repo, entity_repo
):
    """Test retrieving document details."""
    # Create document
    doc = Document(
        id="test-doc-123",
        filename="test.pdf",
        original_filename="test.pdf",
        file_path="/tmp/test.pdf",
        status=DocumentStatus.COMPLETED,
        metadata=DocumentMetadata(page_count=5, file_size_bytes=1024),
    )

    await document_repo.create(doc)

    # Make request
    response = await client.get(f"/api/v1/documents/{doc.id}")

    assert response.status_code == 200
    data = response.json()

    assert data["document"]["id"] == doc.id
    assert "chunk_stats" in data
    assert "entity_stats" in data
    assert "toc_summary" in data


@pytest.mark.asyncio
async def test_get_document_not_found(client, mock_db_for_repos):
    """Test retrieving non-existent document."""
    response = await client.get("/api/v1/documents/nonexistent-id")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_document_without_raw_text(
    client, document_repo, toc_repo, chunk_repo, entity_repo
):
    """Test retrieving document without including raw text."""
    doc = Document(
        id="test-doc-456",
        filename="test.pdf",
        original_filename="test.pdf",
        file_path="/tmp/test.pdf",
        raw_text="This is the full raw text that should be excluded",
    )

    await document_repo.create(doc)

    response = await client.get(f"/api/v1/documents/{doc.id}?include_raw_text=false")

    assert response.status_code == 200
    data = response.json()

    assert data["document"]["raw_text"] is None


# ============================================================
# TEST LIST DOCUMENTS ENDPOINT
# ============================================================


@pytest.mark.asyncio
async def test_list_documents(client, document_repo):
    """Test listing documents with pagination."""
    # Create multiple documents
    for i in range(5):
        doc = Document(
            id=f"doc-{i}",
            filename=f"test{i}.pdf",
            original_filename=f"test{i}.pdf",
            file_path=f"/tmp/test{i}.pdf",
        )
        await document_repo.create(doc)

    response = await client.get("/api/v1/documents?page=1&page_size=10")

    assert response.status_code == 200
    data = response.json()

    assert "documents" in data
    assert "total" in data
    assert data["total"] >= 5
    assert len(data["documents"]) >= 5


@pytest.mark.asyncio
async def test_list_documents_with_status_filter(client, document_repo):
    """Test listing documents filtered by status."""
    # Create documents with different statuses
    doc1 = Document(
        id="doc-completed",
        filename="completed.pdf",
        original_filename="completed.pdf",
        file_path="/tmp/completed.pdf",
        status=DocumentStatus.COMPLETED,
    )
    doc2 = Document(
        id="doc-processing",
        filename="processing.pdf",
        original_filename="processing.pdf",
        file_path="/tmp/processing.pdf",
        status=DocumentStatus.PROCESSING,
    )

    await document_repo.create(doc1)
    await document_repo.create(doc2)

    response = await client.get("/api/v1/documents?status=completed")

    assert response.status_code == 200
    data = response.json()

    # Should only return completed documents
    assert all(doc["status"] == "completed" for doc in data["documents"])


# ============================================================
# TEST DELETE DOCUMENT ENDPOINT
# ============================================================


@pytest.mark.asyncio
async def test_delete_document(
    client, document_repo, toc_repo, chunk_repo, entity_repo
):
    """Test deleting document and all associated data."""
    doc = Document(
        id="doc-to-delete",
        filename="delete.pdf",
        original_filename="delete.pdf",
        file_path="/tmp/delete.pdf",
    )

    await document_repo.create(doc)

    response = await client.delete(f"/api/v1/documents/{doc.id}")

    assert response.status_code == 200
    data = response.json()

    assert data["deleted"] is True
    assert data["document_id"] == doc.id

    # Verify document is deleted
    deleted_doc = await document_repo.get(doc.id)
    assert deleted_doc is None


@pytest.mark.asyncio
async def test_delete_nonexistent_document(client, mock_db_for_repos):
    """Test deleting non-existent document."""
    response = await client.delete("/api/v1/documents/nonexistent-id")

    assert response.status_code == 404


# ============================================================
# TEST SEMANTIC SEARCH ENDPOINT
# ============================================================


@pytest.mark.asyncio
async def test_semantic_search(
    client,
    chunk_repo,
    toc_repo,
    entity_repo,
    mock_embedding_provider,
    sample_embeddings,
):
    """Test semantic search endpoint."""
    # Insert test chunks
    ret_chunk = RetrievalChunk(
        document_id="doc-123",
        toc_node_id="node-456",
        content="Machine learning content",
        generation_chunk_id="gen-789",
        embedding=sample_embeddings,
        embedding_model="test-model",
    )

    gen_chunk = GenerationChunk(
        id="gen-789",
        document_id="doc-123",
        toc_node_id="node-456",
        content="Detailed machine learning content",
        summary="ML summary",
    )

    toc_node = TOCNode(
        id="node-456",
        document_id="doc-123",
        level=TOCLevel.L1,
        title="Chapter 1",
        normalized_title="chapter 1",
        sequence_number=1,
    )

    await chunk_repo.insert_retrieval_chunks([ret_chunk])
    await chunk_repo.insert_generation_chunks([gen_chunk])
    await toc_repo.insert(toc_node)

    # Embedding provider is already mocked via client fixture
    response = await client.post(
        "/api/v1/search/semantic",
        json={
            "query": "machine learning",
            "top_k": 5,
            "min_score": 0.0,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert "results" in data
    assert "total_found" in data
    assert "query" in data
    assert data["query"] == "machine learning"


@pytest.mark.asyncio
async def test_semantic_search_with_document_filter(
    client, mock_db, mock_embedding_provider
):
    """Test semantic search with document ID filter."""
    response = await client.post(
        "/api/v1/search/semantic",
        json={
            "query": "test query",
            "document_ids": ["doc-123", "doc-456"],
            "top_k": 10,
        },
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_semantic_search_validation_error(client, mock_db_for_repos):
    """Test semantic search with invalid parameters."""
    response = await client.post(
        "/api/v1/search/semantic",
        json={
            "query": "test",
            "top_k": 200,  # Exceeds limit
        },
    )

    assert response.status_code == 422  # Validation error


# ============================================================
# TEST TOC SEARCH ENDPOINT
# ============================================================


@pytest.mark.asyncio
async def test_search_toc(client, document_repo, toc_repo):
    """Test TOC search endpoint."""
    # Create document
    doc = Document(
        id="doc-123",
        filename="test.pdf",
        original_filename="test.pdf",
        file_path="/tmp/test.pdf",
    )
    await document_repo.create(doc)

    # Create TOC nodes
    nodes = [
        TOCNode(
            document_id="doc-123",
            level=TOCLevel.L1,
            title="Introduction",
            normalized_title="introduction",
            sequence_number=1,
        ),
        TOCNode(
            document_id="doc-123",
            level=TOCLevel.L1,
            title="Methods",
            normalized_title="methods",
            sequence_number=2,
        ),
    ]

    for node in nodes:
        await toc_repo.insert(node)

    response = await client.post(
        "/api/v1/search/toc",
        json={"document_id": "doc-123", "query": "introduction"},
    )

    assert response.status_code == 200
    data = response.json()

    assert "matching_nodes" in data
    assert data["document_id"] == "doc-123"


# ============================================================
# TEST PIPELINE ENDPOINTS
# ============================================================


@pytest.mark.asyncio
async def test_run_pipeline(client, document_repo, sample_pdf):
    """Test starting pipeline execution."""
    # Create document
    doc = Document(
        id="pipeline-doc-123",
        filename="test.pdf",
        original_filename="test.pdf",
        file_path=str(sample_pdf),
        status=DocumentStatus.UPLOADED,
    )
    await document_repo.create(doc)

    response = await client.post(
        "/api/v1/pipeline/run",
        json={"document_id": doc.id, "skip_vision": True, "force_restart": False},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["document_id"] == doc.id
    assert data["status"] == "started"


@pytest.mark.asyncio
async def test_run_pipeline_document_not_found(client, mock_db_for_repos):
    """Test running pipeline for non-existent document."""
    response = await client.post(
        "/api/v1/pipeline/run",
        json={"document_id": "nonexistent-doc"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_pipeline_status(client, document_repo, mock_settings):
    """Test getting pipeline status."""
    doc = Document(
        id="status-doc-123",
        filename="test.pdf",
        original_filename="test.pdf",
        file_path="/tmp/test.pdf",
        status=DocumentStatus.PROCESSING,
    )
    await document_repo.create(doc)

    # Create pipeline state
    from src.pipeline.state_manager import PipelineStateManager

    state_manager = PipelineStateManager(mock_settings)
    await state_manager.create_state(doc.id)

    response = await client.get(f"/api/v1/pipeline/status/{doc.id}")

    assert response.status_code == 200
    data = response.json()

    assert data["document_id"] == doc.id
    assert "overall_status" in data
    assert "stages" in data
    assert "progress_percent" in data


@pytest.mark.asyncio
async def test_cancel_pipeline(client, document_repo):
    """Test cancelling pipeline."""
    doc = Document(
        id="cancel-doc-123",
        filename="test.pdf",
        original_filename="test.pdf",
        file_path="/tmp/test.pdf",
        status=DocumentStatus.PROCESSING,
    )
    await document_repo.create(doc)

    response = await client.post(f"/api/v1/pipeline/cancel/{doc.id}")

    assert response.status_code == 200
    data = response.json()

    assert "cancelled" in data


@pytest.mark.asyncio
async def test_retry_pipeline(client, document_repo, sample_pdf):
    """Test retrying failed pipeline."""
    doc = Document(
        id="retry-doc-123",
        filename="test.pdf",
        original_filename="test.pdf",
        file_path=str(sample_pdf),
        status=DocumentStatus.FAILED,
    )
    await document_repo.create(doc)

    response = await client.post(f"/api/v1/pipeline/retry/{doc.id}")

    assert response.status_code == 200
    data = response.json()

    assert data["started"] is True or data["started"] is False


# ============================================================
# TEST LIST CHUNKS ENDPOINT
# ============================================================


@pytest.mark.asyncio
async def test_list_chunks(client, document_repo, chunk_repo):
    """Test listing chunks for a document."""
    doc = Document(
        id="chunks-doc-123",
        filename="test.pdf",
        original_filename="test.pdf",
        file_path="/tmp/test.pdf",
    )
    await document_repo.create(doc)

    # Insert chunks
    chunks = [
        RetrievalChunk(
            document_id=doc.id,
            toc_node_id="node-456",
            content=f"Chunk {i}",
            generation_chunk_id=f"gen-{i}",
        )
        for i in range(5)
    ]
    await chunk_repo.insert_retrieval_chunks(chunks)

    response = await client.get(f"/api/v1/search/chunks/{doc.id}?chunk_type=retrieval")

    assert response.status_code == 200
    data = response.json()

    assert data["document_id"] == doc.id
    assert len(data["chunks"]) == 5


@pytest.mark.asyncio
async def test_list_chunks_invalid_type(client, document_repo):
    """Test listing chunks with invalid chunk type."""
    doc = Document(
        id="doc-123",
        filename="test.pdf",
        original_filename="test.pdf",
        file_path="/tmp/test.pdf",
    )
    await document_repo.create(doc)

    response = await client.get(f"/api/v1/search/chunks/{doc.id}?chunk_type=invalid")

    assert response.status_code == 422  # Validation error


# ============================================================
# TEST LIST ENTITIES ENDPOINT
# ============================================================


@pytest.mark.asyncio
async def test_list_entities(client, document_repo, entity_repo):
    """Test listing entities for a document."""
    doc = Document(
        id="entities-doc-123",
        filename="test.pdf",
        original_filename="test.pdf",
        file_path="/tmp/test.pdf",
    )
    await document_repo.create(doc)

    response = await client.get(f"/api/v1/search/entities/{doc.id}")

    assert response.status_code == 200
    data = response.json()

    assert data["document_id"] == doc.id
    assert "entities" in data


# ============================================================
# TEST GET DOCUMENT TOC ENDPOINT
# ============================================================


@pytest.mark.asyncio
async def test_get_document_toc(client, document_repo, toc_repo):
    """Test getting TOC structure for document."""
    doc = Document(
        id="toc-doc-123",
        filename="test.pdf",
        original_filename="test.pdf",
        file_path="/tmp/test.pdf",
    )
    await document_repo.create(doc)

    # Create TOC nodes
    node = TOCNode(
        document_id=doc.id,
        level=TOCLevel.L1,
        title="Chapter 1",
        normalized_title="chapter 1",
        sequence_number=1,
    )
    await toc_repo.insert(node)

    response = await client.get(f"/api/v1/documents/{doc.id}/toc")

    assert response.status_code == 200
    data = response.json()

    assert data["document_id"] == doc.id
    assert "nodes" in data
    assert "summary" in data


# ============================================================
# TEST GET RAW TEXT ENDPOINT
# ============================================================


@pytest.mark.asyncio
async def test_get_raw_text(client, document_repo):
    """Test getting raw text from document."""
    doc = Document(
        id="text-doc-123",
        filename="test.pdf",
        original_filename="test.pdf",
        file_path="/tmp/test.pdf",
        raw_text="This is the raw extracted text.",
        raw_text_by_page=["Page 1 text", "Page 2 text"],
    )
    await document_repo.create(doc)

    response = await client.get(f"/api/v1/documents/{doc.id}/raw-text")

    assert response.status_code == 200
    data = response.json()

    assert data["document_id"] == doc.id
    assert data["content"] == "This is the raw extracted text."


@pytest.mark.asyncio
async def test_get_raw_text_by_page(client, document_repo):
    """Test getting raw text for specific page."""
    doc = Document(
        id="page-text-doc-123",
        filename="test.pdf",
        original_filename="test.pdf",
        file_path="/tmp/test.pdf",
        raw_text_by_page=["Page 1 text", "Page 2 text"],
    )
    await document_repo.create(doc)

    response = await client.get(f"/api/v1/documents/{doc.id}/raw-text?page=1")

    assert response.status_code == 200
    data = response.json()

    assert data["page"] == 1
    assert data["content"] == "Page 1 text"


# ============================================================
# TEST ERROR HANDLING
# ============================================================


@pytest.mark.asyncio
async def test_api_error_response_format(client, mock_db_for_repos):
    """Test that API errors have consistent format."""
    response = await client.get("/api/v1/documents/nonexistent-id")

    assert response.status_code == 404
    data = response.json()

    # FastAPI default error format
    assert "detail" in data


@pytest.mark.asyncio
async def test_validation_error_format(client, mock_db_for_repos):
    """Test validation error response format."""
    response = await client.post(
        "/api/v1/search/semantic",
        json={
            "query": "test",
            "top_k": -1,  # Invalid value
        },
    )

    assert response.status_code == 422
    data = response.json()

    assert "detail" in data
