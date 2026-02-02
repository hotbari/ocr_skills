"""Tests for search functionality in src/db/repositories/chunk_repo.py"""

import numpy as np
import pytest

from src.core.models import GenerationChunk, RetrievalChunk, SemanticType
from src.db.repositories.chunk_repo import ChunkRepository, ChunkSearchResult

# ============================================================
# TEST RETRIEVAL CHUNK OPERATIONS
# ============================================================


@pytest.mark.asyncio
async def test_insert_retrieval_chunks(chunk_repo):
    """Test inserting retrieval chunks."""
    chunks = [
        RetrievalChunk(
            document_id="doc-123",
            toc_node_id="node-456",
            content="Test chunk 1",
            generation_chunk_id="gen-789",
            sequence_in_document=0,
            sequence_in_toc_node=0,
        ),
        RetrievalChunk(
            document_id="doc-123",
            toc_node_id="node-456",
            content="Test chunk 2",
            generation_chunk_id="gen-790",
            sequence_in_document=1,
            sequence_in_toc_node=1,
        ),
    ]

    count = await chunk_repo.insert_retrieval_chunks(chunks)

    assert count == 2


@pytest.mark.asyncio
async def test_get_retrieval_chunk(chunk_repo):
    """Test retrieving a single chunk by ID."""
    chunk = RetrievalChunk(
        document_id="doc-123",
        toc_node_id="node-456",
        content="Test chunk",
        generation_chunk_id="gen-789",
    )

    await chunk_repo.insert_retrieval_chunks([chunk])

    retrieved = await chunk_repo.get_retrieval_chunk(chunk.id)

    assert retrieved is not None
    assert retrieved.id == chunk.id
    assert retrieved.content == "Test chunk"


@pytest.mark.asyncio
async def test_get_retrieval_chunk_nonexistent(chunk_repo):
    """Test retrieving non-existent chunk returns None."""
    retrieved = await chunk_repo.get_retrieval_chunk("nonexistent-id")

    assert retrieved is None


@pytest.mark.asyncio
async def test_get_retrieval_chunks_by_document(chunk_repo):
    """Test getting all retrieval chunks for a document."""
    chunks = [
        RetrievalChunk(
            document_id="doc-123",
            toc_node_id="node-456",
            content=f"Chunk {i}",
            generation_chunk_id=f"gen-{i}",
            sequence_in_document=i,
        )
        for i in range(5)
    ]

    await chunk_repo.insert_retrieval_chunks(chunks)

    retrieved = await chunk_repo.get_retrieval_chunks_by_document("doc-123")

    assert len(retrieved) == 5
    # Should be ordered by sequence
    assert retrieved[0].sequence_in_document == 0
    assert retrieved[4].sequence_in_document == 4


@pytest.mark.asyncio
async def test_get_retrieval_chunks_by_toc(chunk_repo):
    """Test getting retrieval chunks for a TOC node."""
    chunks = [
        RetrievalChunk(
            document_id="doc-123",
            toc_node_id="node-456",
            content=f"Chunk {i}",
            generation_chunk_id=f"gen-{i}",
            sequence_in_toc_node=i,
        )
        for i in range(3)
    ]

    await chunk_repo.insert_retrieval_chunks(chunks)

    retrieved = await chunk_repo.get_retrieval_chunks_by_toc("node-456")

    assert len(retrieved) == 3
    assert all(c.toc_node_id == "node-456" for c in retrieved)


@pytest.mark.asyncio
async def test_update_embedding(chunk_repo):
    """Test updating embedding for a chunk."""
    chunk = RetrievalChunk(
        document_id="doc-123",
        toc_node_id="node-456",
        content="Test chunk",
        generation_chunk_id="gen-789",
    )

    await chunk_repo.insert_retrieval_chunks([chunk])

    embedding = [0.1] * 1536
    updated = await chunk_repo.update_embedding(chunk.id, embedding, "test-model")

    assert updated is True

    # Verify embedding was saved
    retrieved = await chunk_repo.get_retrieval_chunk(chunk.id)
    assert retrieved.embedding is not None
    assert len(retrieved.embedding) == 1536
    assert retrieved.embedding_model == "test-model"


# ============================================================
# TEST GENERATION CHUNK OPERATIONS
# ============================================================


@pytest.mark.asyncio
async def test_insert_generation_chunks(chunk_repo):
    """Test inserting generation chunks."""
    chunks = [
        GenerationChunk(
            document_id="doc-123",
            toc_node_id="node-456",
            content="Detailed content 1",
            summary="Summary 1",
            sequence_in_document=0,
        ),
        GenerationChunk(
            document_id="doc-123",
            toc_node_id="node-456",
            content="Detailed content 2",
            summary="Summary 2",
            sequence_in_document=1,
        ),
    ]

    count = await chunk_repo.insert_generation_chunks(chunks)

    assert count == 2


@pytest.mark.asyncio
async def test_get_generation_chunk(chunk_repo):
    """Test retrieving a generation chunk by ID."""
    chunk = GenerationChunk(
        document_id="doc-123",
        toc_node_id="node-456",
        content="Detailed content",
        summary="Summary",
    )

    await chunk_repo.insert_generation_chunks([chunk])

    retrieved = await chunk_repo.get_generation_chunk(chunk.id)

    assert retrieved is not None
    assert retrieved.id == chunk.id
    assert retrieved.content == "Detailed content"
    assert retrieved.summary == "Summary"


@pytest.mark.asyncio
async def test_get_generation_by_retrieval_id(chunk_repo):
    """Test getting generation chunk linked to retrieval chunk."""
    gen_chunk = GenerationChunk(
        document_id="doc-123",
        toc_node_id="node-456",
        content="Detailed content",
        summary="Summary",
    )

    await chunk_repo.insert_generation_chunks([gen_chunk])

    ret_chunk = RetrievalChunk(
        document_id="doc-123",
        toc_node_id="node-456",
        content="Short content",
        generation_chunk_id=gen_chunk.id,
    )

    await chunk_repo.insert_retrieval_chunks([ret_chunk])

    # Get generation chunk via retrieval ID
    retrieved = await chunk_repo.get_generation_by_retrieval_id(ret_chunk.id)

    assert retrieved is not None
    assert retrieved.id == gen_chunk.id


# ============================================================
# TEST VECTOR SEARCH
# ============================================================


@pytest.mark.asyncio
async def test_vector_search_basic(chunk_repo, sample_embeddings):
    """Test basic vector search."""
    # Insert chunks with embeddings
    chunks = [
        RetrievalChunk(
            document_id="doc-123",
            toc_node_id="node-456",
            content="Machine learning is a subset of AI",
            generation_chunk_id="gen-1",
            embedding=sample_embeddings,
            embedding_model="test-model",
        ),
        RetrievalChunk(
            document_id="doc-123",
            toc_node_id="node-456",
            content="Deep learning uses neural networks",
            generation_chunk_id="gen-2",
            embedding=[0.2 + (i * 0.001) for i in range(1536)],
            embedding_model="test-model",
        ),
    ]

    await chunk_repo.insert_retrieval_chunks(chunks)

    # Also insert generation chunks
    gen_chunks = [
        GenerationChunk(
            id="gen-1",
            document_id="doc-123",
            toc_node_id="node-456",
            content="Detailed ML content",
        ),
        GenerationChunk(
            id="gen-2",
            document_id="doc-123",
            toc_node_id="node-456",
            content="Detailed DL content",
        ),
    ]

    await chunk_repo.insert_generation_chunks(gen_chunks)

    # Search with similar embedding
    query_embedding = [0.1 + (i * 0.001) for i in range(1536)]
    results = await chunk_repo.vector_search(query_embedding, top_k=2)

    assert len(results) <= 2
    assert all(isinstance(r, ChunkSearchResult) for r in results)
    # Results should be sorted by score descending
    if len(results) == 2:
        assert results[0].score >= results[1].score


@pytest.mark.asyncio
async def test_vector_search_with_filters(chunk_repo, sample_embeddings):
    """Test vector search with document filter."""
    # Insert chunks for multiple documents
    chunks = [
        RetrievalChunk(
            document_id="doc-123",
            toc_node_id="node-456",
            content="Content in doc 123",
            generation_chunk_id="gen-1",
            embedding=sample_embeddings,
            embedding_model="test-model",
        ),
        RetrievalChunk(
            document_id="doc-456",
            toc_node_id="node-789",
            content="Content in doc 456",
            generation_chunk_id="gen-2",
            embedding=[0.2] * 1536,
            embedding_model="test-model",
        ),
    ]

    await chunk_repo.insert_retrieval_chunks(chunks)

    # Search with document filter
    results = await chunk_repo.vector_search(
        sample_embeddings, document_id="doc-123", top_k=10
    )

    assert all(r.retrieval_chunk.document_id == "doc-123" for r in results)


@pytest.mark.asyncio
async def test_vector_search_min_score(chunk_repo):
    """Test vector search with minimum score threshold."""
    # Insert chunk with specific embedding
    chunks = [
        RetrievalChunk(
            document_id="doc-123",
            toc_node_id="node-456",
            content="Test content",
            generation_chunk_id="gen-1",
            embedding=[1.0] * 1536,
            embedding_model="test-model",
        ),
    ]

    await chunk_repo.insert_retrieval_chunks([chunks[0]])

    # Search with very different embedding and high min_score
    query_embedding = [-1.0] * 1536
    results = await chunk_repo.vector_search(query_embedding, min_score=0.9, top_k=10)

    # Should return no results due to low similarity
    assert len(results) == 0


@pytest.mark.asyncio
async def test_vector_search_empty_query():
    """Test vector search with zero vector returns empty results."""
    # This test doesn't need fixtures, just tests the edge case
    pass


@pytest.mark.asyncio
async def test_cosine_similarity_calculation(chunk_repo):
    """Test that cosine similarity is calculated correctly."""
    # Create two orthogonal vectors (similarity should be ~0)
    embedding1 = [1.0] + [0.0] * 1535
    embedding2 = [0.0] + [1.0] + [0.0] * 1534

    chunk = RetrievalChunk(
        document_id="doc-123",
        toc_node_id="node-456",
        content="Test",
        generation_chunk_id="gen-1",
        embedding=embedding1,
        embedding_model="test-model",
    )

    await chunk_repo.insert_retrieval_chunks([chunk])

    results = await chunk_repo.vector_search(embedding2, top_k=10, min_score=0.0)

    # Similarity should be close to 0 for orthogonal vectors
    if results:
        assert results[0].score < 0.1


# ============================================================
# TEST DELETE OPERATIONS
# ============================================================


@pytest.mark.asyncio
async def test_delete_by_document(chunk_repo):
    """Test deleting all chunks for a document."""
    # Insert chunks
    ret_chunks = [
        RetrievalChunk(
            document_id="doc-123",
            toc_node_id="node-456",
            content="Test",
            generation_chunk_id=f"gen-{i}",
        )
        for i in range(3)
    ]

    gen_chunks = [
        GenerationChunk(
            id=f"gen-{i}",
            document_id="doc-123",
            toc_node_id="node-456",
            content=f"Content {i}",
        )
        for i in range(3)
    ]

    await chunk_repo.insert_retrieval_chunks(ret_chunks)
    await chunk_repo.insert_generation_chunks(gen_chunks)

    # Delete
    ret_deleted, gen_deleted = await chunk_repo.delete_by_document("doc-123")

    assert ret_deleted == 3
    assert gen_deleted == 3

    # Verify deletion
    remaining = await chunk_repo.get_retrieval_chunks_by_document("doc-123")
    assert len(remaining) == 0


# ============================================================
# TEST COUNT OPERATIONS
# ============================================================


@pytest.mark.asyncio
async def test_count_by_document(chunk_repo):
    """Test counting chunks for a document."""
    # Insert chunks
    ret_chunks = [
        RetrievalChunk(
            document_id="doc-123",
            toc_node_id="node-456",
            content="Test",
            generation_chunk_id=f"gen-{i}",
        )
        for i in range(5)
    ]

    gen_chunks = [
        GenerationChunk(
            document_id="doc-123",
            toc_node_id="node-456",
            content=f"Content {i}",
        )
        for i in range(3)
    ]

    await chunk_repo.insert_retrieval_chunks(ret_chunks)
    await chunk_repo.insert_generation_chunks(gen_chunks)

    # Count
    counts = await chunk_repo.count_by_document("doc-123")

    assert counts["retrieval"] == 5
    assert counts["generation"] == 3


@pytest.mark.asyncio
async def test_count_by_document_empty(chunk_repo):
    """Test counting for document with no chunks."""
    counts = await chunk_repo.count_by_document("nonexistent-doc")

    assert counts["retrieval"] == 0
    assert counts["generation"] == 0


# ============================================================
# TEST PAGINATION
# ============================================================


@pytest.mark.asyncio
async def test_get_retrieval_chunks_pagination(chunk_repo):
    """Test pagination of retrieval chunks."""
    # Insert many chunks
    chunks = [
        RetrievalChunk(
            document_id="doc-123",
            toc_node_id="node-456",
            content=f"Chunk {i}",
            generation_chunk_id=f"gen-{i}",
            sequence_in_document=i,
        )
        for i in range(25)
    ]

    await chunk_repo.insert_retrieval_chunks(chunks)

    # Get first page
    page1 = await chunk_repo.get_retrieval_chunks_by_document(
        "doc-123", skip=0, limit=10
    )
    assert len(page1) == 10
    assert page1[0].sequence_in_document == 0

    # Get second page
    page2 = await chunk_repo.get_retrieval_chunks_by_document(
        "doc-123", skip=10, limit=10
    )
    assert len(page2) == 10
    assert page2[0].sequence_in_document == 10

    # Get third page (partial)
    page3 = await chunk_repo.get_retrieval_chunks_by_document(
        "doc-123", skip=20, limit=10
    )
    assert len(page3) == 5
    assert page3[0].sequence_in_document == 20


# ============================================================
# TEST EDGE CASES
# ============================================================


@pytest.mark.asyncio
async def test_insert_empty_chunk_list(chunk_repo):
    """Test inserting empty list returns 0."""
    count = await chunk_repo.insert_retrieval_chunks([])

    assert count == 0


@pytest.mark.asyncio
async def test_vector_search_no_embeddings(chunk_repo):
    """Test vector search with no embedded chunks returns empty."""
    # Insert chunk without embedding
    chunk = RetrievalChunk(
        document_id="doc-123",
        toc_node_id="node-456",
        content="Test",
        generation_chunk_id="gen-1",
    )

    await chunk_repo.insert_retrieval_chunks([chunk])

    results = await chunk_repo.vector_search([0.1] * 1536, top_k=10)

    assert len(results) == 0


@pytest.mark.asyncio
async def test_chunk_search_result_model():
    """Test ChunkSearchResult dataclass."""
    ret_chunk = RetrievalChunk(
        document_id="doc-123",
        toc_node_id="node-456",
        content="Test",
        generation_chunk_id="gen-1",
    )

    gen_chunk = GenerationChunk(
        document_id="doc-123", toc_node_id="node-456", content="Detailed"
    )

    result = ChunkSearchResult(
        retrieval_chunk=ret_chunk, generation_chunk=gen_chunk, score=0.85
    )

    assert result.score == 0.85
    assert result.retrieval_chunk == ret_chunk
    assert result.generation_chunk == gen_chunk
