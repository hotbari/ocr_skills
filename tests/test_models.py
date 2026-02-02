"""Tests for Pydantic models in src/core/models.py"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.core.models import (BoundingBox, Document, DocumentMetadata,
                             DocumentStatus, Entity, EntityType,
                             GenerationChunk, Language, PipelineStage,
                             PipelineState, RetrievalChunk, SearchQuery,
                             SearchResponse, SearchResult, Segment,
                             SegmentWithHeading, SemanticType, StageResult,
                             StageStatus, TOCLevel, TOCNode, TOCStructure,
                             generate_id)

# ============================================================
# TEST ID GENERATION
# ============================================================


def test_generate_id():
    """Test ID generation produces valid UUIDs."""
    id1 = generate_id()
    id2 = generate_id()

    assert isinstance(id1, str)
    assert isinstance(id2, str)
    assert id1 != id2
    assert len(id1) == 36  # UUID format


# ============================================================
# TEST ENUMS
# ============================================================


def test_document_status_enum():
    """Test DocumentStatus enum values."""
    assert DocumentStatus.UPLOADED.value == "uploaded"
    assert DocumentStatus.PROCESSING.value == "processing"
    assert DocumentStatus.COMPLETED.value == "completed"
    assert DocumentStatus.FAILED.value == "failed"
    assert DocumentStatus.PARTIAL.value == "partial"


def test_pipeline_stage_enum():
    """Test PipelineStage enum values."""
    assert PipelineStage.STAGE_0_EXTRACTION.value == "stage_0_extraction"
    assert PipelineStage.STAGE_7_EMBEDDING.value == "stage_7_embedding"


def test_stage_status_enum():
    """Test StageStatus enum values."""
    assert StageStatus.PENDING.value == "pending"
    assert StageStatus.RUNNING.value == "running"
    assert StageStatus.COMPLETED.value == "completed"
    assert StageStatus.FAILED.value == "failed"
    assert StageStatus.SKIPPED.value == "skipped"


def test_semantic_type_enum():
    """Test SemanticType enum values."""
    assert SemanticType.DEFINITION.value == "definition"
    assert SemanticType.PROCEDURE.value == "procedure"
    assert SemanticType.EXAMPLE.value == "example"


def test_entity_type_enum():
    """Test EntityType enum values."""
    assert EntityType.TABLE.value == "table"
    assert EntityType.IMAGE.value == "image"
    assert EntityType.DIAGRAM.value == "diagram"


def test_toc_level_enum():
    """Test TOCLevel enum values."""
    assert TOCLevel.L1.value == 1
    assert TOCLevel.L2.value == 2
    assert TOCLevel.L3.value == 3


def test_language_enum():
    """Test Language enum values."""
    assert Language.KOREAN.value == "ko"
    assert Language.ENGLISH.value == "en"
    assert Language.MIXED.value == "mixed"
    assert Language.UNKNOWN.value == "unknown"


# ============================================================
# TEST DOCUMENT MODELS
# ============================================================


def test_document_metadata_creation():
    """Test DocumentMetadata creation with defaults."""
    metadata = DocumentMetadata()

    assert metadata.title is None
    assert metadata.author is None
    assert metadata.page_count == 0
    assert metadata.file_size_bytes == 0
    assert metadata.detected_language == Language.UNKNOWN


def test_document_metadata_with_values():
    """Test DocumentMetadata with specific values."""
    metadata = DocumentMetadata(
        title="Test Document",
        author="Test Author",
        subject="Testing",
        creator="Test Creator",
        page_count=10,
        file_size_bytes=1024,
        detected_language=Language.ENGLISH,
    )

    assert metadata.title == "Test Document"
    assert metadata.author == "Test Author"
    assert metadata.page_count == 10
    assert metadata.detected_language == Language.ENGLISH


def test_document_creation():
    """Test Document model creation."""
    doc = Document(
        filename="test.pdf",
        original_filename="test.pdf",
        file_path="/tmp/test.pdf",
    )

    assert doc.id is not None
    assert doc.filename == "test.pdf"
    assert doc.status == DocumentStatus.UPLOADED
    assert isinstance(doc.upload_timestamp, datetime)
    assert doc.metadata is not None
    assert doc.raw_text is None


def test_document_with_custom_id():
    """Test Document with custom ID."""
    doc = Document(
        id="custom-id-123",
        filename="test.pdf",
        original_filename="test.pdf",
        file_path="/tmp/test.pdf",
    )

    assert doc.id == "custom-id-123"


def test_document_enum_serialization():
    """Test that enums are serialized as values with Config."""
    doc = Document(
        filename="test.pdf",
        original_filename="test.pdf",
        file_path="/tmp/test.pdf",
        status=DocumentStatus.PROCESSING,
    )

    doc_dict = doc.model_dump()
    assert doc_dict["status"] == "processing"


# ============================================================
# TEST TOC MODELS
# ============================================================


def test_toc_node_creation():
    """Test TOCNode creation."""
    node = TOCNode(
        document_id="doc-123",
        level=TOCLevel.L1,
        title="Chapter 1",
        normalized_title="chapter 1",
        sequence_number=1,
    )

    assert node.id is not None
    assert node.document_id == "doc-123"
    assert node.level == TOCLevel.L1
    assert node.title == "Chapter 1"
    assert node.parent_id is None
    assert node.children_ids == []


def test_toc_node_hierarchy():
    """Test TOCNode parent-child relationships."""
    parent = TOCNode(
        document_id="doc-123",
        level=TOCLevel.L1,
        title="Chapter 1",
        normalized_title="chapter 1",
        sequence_number=1,
    )

    child = TOCNode(
        document_id="doc-123",
        level=TOCLevel.L2,
        title="Section 1.1",
        normalized_title="section 1.1",
        sequence_number=1,
        parent_id=parent.id,
    )

    parent.children_ids.append(child.id)

    assert child.parent_id == parent.id
    assert child.id in parent.children_ids


def test_toc_structure():
    """Test TOCStructure model."""
    structure = TOCStructure(
        document_id="doc-123",
        root_nodes=["node-1", "node-2"],
        total_l1=2,
        total_l2=5,
        total_l3=10,
    )

    assert structure.document_id == "doc-123"
    assert len(structure.root_nodes) == 2
    assert structure.total_l1 == 2


# ============================================================
# TEST SEGMENT MODELS
# ============================================================


def test_segment_creation():
    """Test Segment creation."""
    segment = Segment(
        segment_id=1,
        content="This is a test segment.",
        page_number=1,
        semantic_type=SemanticType.EXPLANATION,
        key_concepts=["test", "segment"],
        reasoning="Test reasoning",
    )

    assert segment.segment_id == 1
    assert segment.content == "This is a test segment."
    assert segment.semantic_type == SemanticType.EXPLANATION
    assert len(segment.key_concepts) == 2


def test_segment_with_defaults():
    """Test Segment with default values."""
    segment = Segment(
        segment_id=1,
        content="Test content",
        page_number=1,
    )

    assert segment.position_in_page == 0
    assert segment.semantic_type == SemanticType.EXPLANATION
    assert segment.key_concepts == []
    assert segment.reasoning == ""


def test_segment_with_heading():
    """Test SegmentWithHeading model."""
    segment = Segment(
        segment_id=1,
        content="Test content",
        page_number=1,
    )

    segment_with_heading = SegmentWithHeading(
        segment=segment,
        candidate_headings=["Heading 1", "Heading 2"],
        confidence_scores=[0.9, 0.8],
        selected_heading="Heading 1",
        heading_level=TOCLevel.L1,
    )

    assert segment_with_heading.segment == segment
    assert len(segment_with_heading.candidate_headings) == 2
    assert segment_with_heading.selected_heading == "Heading 1"


# ============================================================
# TEST CHUNK MODELS
# ============================================================


def test_retrieval_chunk_creation():
    """Test RetrievalChunk creation."""
    chunk = RetrievalChunk(
        document_id="doc-123",
        toc_node_id="node-456",
        content="This is a retrieval chunk.",
        semantic_type=SemanticType.DEFINITION,
        key_concepts=["concept A"],
        page_numbers=[1, 2],
        sequence_in_document=0,
        sequence_in_toc_node=0,
        generation_chunk_id="gen-789",
        token_count=10,
    )

    assert chunk.id is not None
    assert chunk.document_id == "doc-123"
    assert chunk.content == "This is a retrieval chunk."
    assert chunk.embedding is None
    assert chunk.token_count == 10


def test_retrieval_chunk_with_embedding():
    """Test RetrievalChunk with embedding."""
    chunk = RetrievalChunk(
        document_id="doc-123",
        toc_node_id="node-456",
        content="Test content",
        generation_chunk_id="gen-789",
        embedding=[0.1] * 1536,
        embedding_model="text-embedding-3-small",
    )

    assert chunk.embedding is not None
    assert len(chunk.embedding) == 1536
    assert chunk.embedding_model == "text-embedding-3-small"


def test_generation_chunk_creation():
    """Test GenerationChunk creation."""
    chunk = GenerationChunk(
        document_id="doc-123",
        toc_node_id="node-456",
        content="This is a generation chunk with detailed content.",
        summary="Detailed content summary",
        semantic_type=SemanticType.EXPLANATION,
        key_concepts=["concept A", "concept B"],
        context_path="Chapter 1 > Section 1.1",
        page_numbers=[1, 2, 3],
        sequence_in_document=0,
        retrieval_chunk_ids=["ret-1", "ret-2"],
        entity_ids=["ent-1"],
        token_count=50,
    )

    assert chunk.id is not None
    assert chunk.document_id == "doc-123"
    assert chunk.summary == "Detailed content summary"
    assert len(chunk.retrieval_chunk_ids) == 2
    assert len(chunk.entity_ids) == 1


# ============================================================
# TEST ENTITY MODELS
# ============================================================


def test_bounding_box():
    """Test BoundingBox model."""
    bbox = BoundingBox(x0=0.1, y0=0.2, x1=0.8, y1=0.9)

    assert bbox.x0 == 0.1
    assert bbox.y0 == 0.2
    assert bbox.x1 == 0.8
    assert bbox.y1 == 0.9


def test_entity_creation():
    """Test Entity creation."""
    entity = Entity(
        document_id="doc-123",
        entity_type=EntityType.TABLE,
        page_number=5,
        sequence_in_page=1,
        bbox=BoundingBox(x0=0.1, y0=0.2, x1=0.8, y1=0.9),
    )

    assert entity.id is not None
    assert entity.document_id == "doc-123"
    assert entity.entity_type == EntityType.TABLE
    assert entity.page_number == 5
    assert entity.vision_processed is False


def test_entity_with_vision_description():
    """Test Entity with vision description."""
    entity = Entity(
        document_id="doc-123",
        entity_type=EntityType.IMAGE,
        page_number=3,
        vision_description="An image showing a graph.",
        vision_processed=True,
    )

    assert entity.vision_description == "An image showing a graph."
    assert entity.vision_processed is True


# ============================================================
# TEST PIPELINE STATE MODELS
# ============================================================


def test_stage_result():
    """Test StageResult model."""
    result = StageResult(
        stage=PipelineStage.STAGE_0_EXTRACTION,
        status=StageStatus.COMPLETED,
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        duration_seconds=5.5,
    )

    assert result.stage == PipelineStage.STAGE_0_EXTRACTION
    assert result.status == StageStatus.COMPLETED
    assert result.duration_seconds == 5.5
    assert result.error_message is None


def test_stage_result_with_error():
    """Test StageResult with error."""
    result = StageResult(
        stage=PipelineStage.STAGE_1_SEGMENTATION,
        status=StageStatus.FAILED,
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        error_message="Segmentation failed",
    )

    assert result.status == StageStatus.FAILED
    assert result.error_message == "Segmentation failed"


def test_pipeline_state_creation():
    """Test PipelineState creation."""
    state = PipelineState(
        document_id="doc-123",
    )

    assert state.id is not None
    assert state.document_id == "doc-123"
    assert state.stages == {}
    assert state.current_stage is None
    assert isinstance(state.started_at, datetime)
    assert state.completed_at is None


def test_pipeline_state_with_stages():
    """Test PipelineState with stage results."""
    result = StageResult(
        stage=PipelineStage.STAGE_0_EXTRACTION,
        status=StageStatus.COMPLETED,
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
    )

    state = PipelineState(
        document_id="doc-123",
        current_stage=PipelineStage.STAGE_1_SEGMENTATION,
        last_completed_stage=PipelineStage.STAGE_0_EXTRACTION,
    )

    state.stages[PipelineStage.STAGE_0_EXTRACTION.value] = result

    assert state.current_stage == PipelineStage.STAGE_1_SEGMENTATION
    assert state.last_completed_stage == PipelineStage.STAGE_0_EXTRACTION
    assert len(state.stages) == 1


# ============================================================
# TEST SEARCH MODELS
# ============================================================


def test_search_query_validation():
    """Test SearchQuery validation."""
    query = SearchQuery(
        query="test query",
        top_k=5,
        min_score=0.7,
    )

    assert query.query == "test query"
    assert query.top_k == 5
    assert query.min_score == 0.7
    assert query.include_entities is True


def test_search_query_validation_limits():
    """Test SearchQuery field validation."""
    # Valid query
    query = SearchQuery(query="test", top_k=10, min_score=0.5)
    assert query.top_k == 10

    # top_k exceeds max
    with pytest.raises(ValidationError):
        SearchQuery(query="test", top_k=200)

    # min_score exceeds max
    with pytest.raises(ValidationError):
        SearchQuery(query="test", min_score=1.5)

    # min_score below min
    with pytest.raises(ValidationError):
        SearchQuery(query="test", min_score=-0.1)


def test_search_result():
    """Test SearchResult model."""
    retrieval_chunk = RetrievalChunk(
        document_id="doc-123",
        toc_node_id="node-456",
        content="Test content",
        generation_chunk_id="gen-789",
    )

    generation_chunk = GenerationChunk(
        document_id="doc-123",
        toc_node_id="node-456",
        content="Detailed content",
    )

    toc_node = TOCNode(
        document_id="doc-123",
        level=TOCLevel.L1,
        title="Chapter 1",
        normalized_title="chapter 1",
        sequence_number=1,
    )

    result = SearchResult(
        retrieval_chunk=retrieval_chunk,
        generation_chunk=generation_chunk,
        toc_node=toc_node,
        score=0.85,
        context_path="Chapter 1",
    )

    assert result.score == 0.85
    assert result.context_path == "Chapter 1"
    assert result.retrieval_chunk.content == "Test content"


def test_search_response():
    """Test SearchResponse model."""
    response = SearchResponse(
        query="test query",
        results=[],
        total_found=0,
        processing_time_ms=15.5,
    )

    assert response.query == "test query"
    assert response.total_found == 0
    assert response.processing_time_ms == 15.5
    assert len(response.results) == 0


# ============================================================
# TEST MODEL SERIALIZATION
# ============================================================


def test_document_json_serialization():
    """Test Document serialization to JSON."""
    doc = Document(
        filename="test.pdf",
        original_filename="test.pdf",
        file_path="/tmp/test.pdf",
        status=DocumentStatus.PROCESSING,
    )

    doc_dict = doc.model_dump(mode="json")

    assert doc_dict["status"] == "processing"
    assert "upload_timestamp" in doc_dict
    assert isinstance(doc_dict["upload_timestamp"], str)


def test_retrieval_chunk_json_serialization():
    """Test RetrievalChunk serialization."""
    chunk = RetrievalChunk(
        document_id="doc-123",
        toc_node_id="node-456",
        content="Test",
        generation_chunk_id="gen-789",
        semantic_type=SemanticType.DEFINITION,
    )

    chunk_dict = chunk.model_dump(mode="json")

    assert chunk_dict["semantic_type"] == "definition"
    assert "created_at" in chunk_dict
