"""Core Pydantic models for the RAG VectorDB PDF Pipeline."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def generate_id() -> str:
    """Generate a unique ID."""
    return str(uuid.uuid4())


# ============================================================
# ENUMS
# ============================================================


class DocumentStatus(str, Enum):
    """Document processing status."""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class PipelineStage(str, Enum):
    """Pipeline processing stages."""

    STAGE_0_EXTRACTION = "stage_0_extraction"
    STAGE_1_SEGMENTATION = "stage_1_segmentation"
    STAGE_2_HEADINGS = "stage_2_headings"
    STAGE_3_TOC_ALIGNMENT = "stage_3_toc_alignment"
    STAGE_4_TOC_NORMALIZATION = "stage_4_toc_normalization"
    STAGE_5_CHUNKING = "stage_5_chunking"
    STAGE_5B_ENTITIES = "stage_5b_entities"
    STAGE_6_VISION = "stage_6_vision"
    STAGE_7_EMBEDDING = "stage_7_embedding"


class StageStatus(str, Enum):
    """Individual stage status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class SemanticType(str, Enum):
    """Semantic type of content segments."""

    DEFINITION = "definition"
    PROCEDURE = "procedure"
    EXAMPLE = "example"
    EXPLANATION = "explanation"
    REFERENCE = "reference"
    LIST = "list"
    COMPARISON = "comparison"
    WARNING = "warning"
    NOTE = "note"
    CODE = "code"
    FORMULA = "formula"


class EntityType(str, Enum):
    """Type of extracted entity."""

    TABLE = "table"
    IMAGE = "image"
    DIAGRAM = "diagram"
    CHART = "chart"
    EQUATION = "equation"


class TOCLevel(int, Enum):
    """Table of Contents hierarchy level."""

    L1 = 1
    L2 = 2
    L3 = 3


class Language(str, Enum):
    """Detected document language."""

    KOREAN = "ko"
    ENGLISH = "en"
    MIXED = "mixed"
    UNKNOWN = "unknown"


# ============================================================
# DOCUMENT MODELS
# ============================================================


class DocumentMetadata(BaseModel):
    """Metadata extracted from PDF."""

    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    creator: Optional[str] = None
    page_count: int = 0
    file_size_bytes: int = 0
    detected_language: Language = Language.UNKNOWN


class Document(BaseModel):
    """Root document entity."""

    id: str = Field(default_factory=generate_id)
    filename: str
    original_filename: str
    file_path: str
    upload_timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: DocumentStatus = DocumentStatus.UPLOADED
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    raw_text: Optional[str] = None
    raw_text_by_page: list[str] = Field(default_factory=list)
    current_stage: Optional[PipelineStage] = None
    error_message: Optional[str] = None
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None

    class Config:
        use_enum_values = True


# ============================================================
# TOC MODELS
# ============================================================


class TOCNode(BaseModel):
    """Table of Contents node - hierarchical structure."""

    id: str = Field(default_factory=generate_id)
    document_id: str
    level: TOCLevel
    title: str
    normalized_title: str
    sequence_number: int
    parent_id: Optional[str] = None
    children_ids: list[str] = Field(default_factory=list)
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    retrieval_chunk_ids: list[str] = Field(default_factory=list)
    generation_chunk_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)

    class Config:
        use_enum_values = True


class TOCStructure(BaseModel):
    """Complete TOC for a document."""

    document_id: str
    root_nodes: list[str] = Field(default_factory=list)
    all_nodes: list[TOCNode] = Field(default_factory=list)
    total_l1: int = 0
    total_l2: int = 0
    total_l3: int = 0


# ============================================================
# SEGMENT MODELS
# ============================================================


class Segment(BaseModel):
    """Raw semantic segment from Stage 1."""

    segment_id: int
    content: str
    page_number: int
    position_in_page: int = 0
    semantic_type: SemanticType = SemanticType.EXPLANATION
    key_concepts: list[str] = Field(default_factory=list)
    reasoning: str = ""

    class Config:
        use_enum_values = True


class SegmentWithHeading(BaseModel):
    """Segment with candidate headings from Stage 2."""

    segment: Segment
    candidate_headings: list[str] = Field(default_factory=list)
    confidence_scores: list[float] = Field(default_factory=list)
    selected_heading: Optional[str] = None
    heading_level: Optional[TOCLevel] = None


# ============================================================
# CHUNK MODELS (DUAL-CHUNK SYSTEM)
# ============================================================


class RetrievalChunk(BaseModel):
    """Short chunk optimized for vector search (100-300 tokens)."""

    id: str = Field(default_factory=generate_id)
    document_id: str
    toc_node_id: str
    content: str
    semantic_type: SemanticType = SemanticType.EXPLANATION
    key_concepts: list[str] = Field(default_factory=list)
    page_numbers: list[int] = Field(default_factory=list)
    sequence_in_document: int = 0
    sequence_in_toc_node: int = 0
    generation_chunk_id: str
    embedding: Optional[list[float]] = None
    embedding_model: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    token_count: int = 0

    class Config:
        use_enum_values = True


class GenerationChunk(BaseModel):
    """Detailed chunk for answer generation (500-1500 tokens)."""

    id: str = Field(default_factory=generate_id)
    document_id: str
    toc_node_id: str
    content: str
    summary: str = ""
    semantic_type: SemanticType = SemanticType.EXPLANATION
    key_concepts: list[str] = Field(default_factory=list)
    context_path: str = ""
    parent_summary: Optional[str] = None
    page_numbers: list[int] = Field(default_factory=list)
    sequence_in_document: int = 0
    retrieval_chunk_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    token_count: int = 0

    class Config:
        use_enum_values = True


# ============================================================
# ENTITY MODELS
# ============================================================


class TableCell(BaseModel):
    """Single cell in a table."""

    row: int
    col: int
    content: str
    rowspan: int = 1
    colspan: int = 1
    is_header: bool = False


class TableStructure(BaseModel):
    """Canonical JSON representation of a table."""

    rows: int
    cols: int
    headers: list[str] = Field(default_factory=list)
    cells: list[TableCell] = Field(default_factory=list)
    has_merged_cells: bool = False


class BoundingBox(BaseModel):
    """Bounding box coordinates (normalized 0-1)."""

    x0: float
    y0: float
    x1: float
    y1: float


class Entity(BaseModel):
    """Entity for tables, images, diagrams."""

    id: str = Field(default_factory=generate_id)
    document_id: str
    toc_node_id: Optional[str] = None
    generation_chunk_id: Optional[str] = None
    entity_type: EntityType
    page_number: int
    sequence_in_page: int = 0
    bbox: Optional[BoundingBox] = None
    canonical_json: Optional[dict[str, Any]] = None
    markdown: Optional[str] = None
    ir_yaml: Optional[str] = None
    image_path: Optional[str] = None
    image_base64: Optional[str] = None
    vision_description: Optional[str] = None
    vision_processed: bool = False
    caption: Optional[str] = None
    surrounding_context: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True


# ============================================================
# PIPELINE STATE MODELS
# ============================================================


class StageResult(BaseModel):
    """Result of a single pipeline stage."""

    stage: PipelineStage
    status: StageStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    output_summary: Optional[dict[str, Any]] = None

    class Config:
        use_enum_values = True


class PipelineState(BaseModel):
    """Complete pipeline state for a document (for resume capability)."""

    id: str = Field(default_factory=generate_id)
    document_id: str
    stages: dict[str, StageResult] = Field(default_factory=dict)
    current_stage: Optional[PipelineStage] = None
    last_completed_stage: Optional[PipelineStage] = None
    stage_outputs: dict[str, str] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    total_duration_seconds: Optional[float] = None
    config_snapshot: Optional[dict[str, Any]] = None

    class Config:
        use_enum_values = True


# ============================================================
# SEARCH MODELS
# ============================================================


class SearchQuery(BaseModel):
    """User search query."""

    query: str
    document_ids: Optional[list[str]] = None
    top_k: int = Field(default=10, ge=1, le=100)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    include_entities: bool = True


class SearchResult(BaseModel):
    """Single search result."""

    retrieval_chunk: RetrievalChunk
    generation_chunk: GenerationChunk
    toc_node: TOCNode
    entities: list[Entity] = Field(default_factory=list)
    score: float
    context_path: str


class SearchResponse(BaseModel):
    """Complete search response."""

    query: str
    results: list[SearchResult]
    total_found: int
    processing_time_ms: float


# ============================================================
# LLM OUTPUT SCHEMAS (for structured output)
# ============================================================


class Stage1SegmentOutput(BaseModel):
    """Single segment from Stage 1 LLM output."""

    segment_id: int
    content: str
    page_number: int
    semantic_type: str
    key_concepts: list[str]
    reasoning: str


class Stage1Output(BaseModel):
    """Stage 1 LLM output - segmentation results."""

    segments: list[Stage1SegmentOutput]


class Stage2HeadingOutput(BaseModel):
    """Single heading assignment from Stage 2 LLM output."""

    segment_id: int
    candidate_headings: list[str]
    confidence_scores: list[float]
    recommended_level: int


class Stage2Output(BaseModel):
    """Stage 2 LLM output - heading generation results."""

    headings: list[Stage2HeadingOutput]


class Stage3TOCNodeOutput(BaseModel):
    """Single TOC node from Stage 3 LLM output."""

    node_id: str
    title: str
    level: int
    parent_node_id: Optional[str]
    segment_ids: list[int]


class Stage3Output(BaseModel):
    """Stage 3 LLM output - TOC alignment results."""

    toc_nodes: list[Stage3TOCNodeOutput]


class Stage4NormalizedNode(BaseModel):
    """Single normalized TOC node from Stage 4 LLM output."""

    node_id: str
    title: str
    normalized_title: str
    level: int
    parent_node_id: Optional[str]
    segment_ids: list[int]


class Stage4Output(BaseModel):
    """Stage 4 LLM output - TOC normalization results."""

    normalized_nodes: list[Stage4NormalizedNode]
    validation_passed: bool
    issues_fixed: list[str]


class Stage5RetrievalChunkOutput(BaseModel):
    """Single retrieval chunk from Stage 5 LLM output."""

    chunk_id: str
    toc_node_id: str
    content: str
    key_concepts: list[str]
    semantic_type: str


class Stage5GenerationChunkOutput(BaseModel):
    """Single generation chunk from Stage 5 LLM output."""

    chunk_id: str
    toc_node_id: str
    content: str
    summary: str
    key_concepts: list[str]
    linked_retrieval_ids: list[str]


class Stage5Output(BaseModel):
    """Stage 5 LLM output - dual chunking results."""

    retrieval_chunks: list[Stage5RetrievalChunkOutput]
    generation_chunks: list[Stage5GenerationChunkOutput]


# ============================================================
# API RESPONSE MODELS
# ============================================================


class DocumentUploadResponse(BaseModel):
    """Response after document upload."""

    document_id: str
    filename: str
    status: DocumentStatus
    message: str
    page_count: int
    file_size_bytes: int


class DocumentListResponse(BaseModel):
    """Paginated document list response."""

    documents: list[Document]
    total: int
    page: int
    page_size: int
    total_pages: int


class PipelineStatusResponse(BaseModel):
    """Current pipeline status response."""

    document_id: str
    overall_status: DocumentStatus
    current_stage: Optional[PipelineStage]
    stages: list[StageResult]
    progress_percent: float
    error_message: Optional[str]


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str
    detail: Optional[Any] = None
    code: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
