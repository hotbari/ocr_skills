# Data Models Reference

Complete reference for all Pydantic models used in the OCR pipeline.

## Table of Contents
- [Enums](#enums)
- [Document Models](#document-models)
- [TOC Models](#toc-models)
- [Segment Models](#segment-models)
- [Chunk Models](#chunk-models)
- [Entity Models](#entity-models)
- [Pipeline State Models](#pipeline-state-models)
- [Search Models](#search-models)

---

## Enums

### DocumentStatus
```python
class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"      # Document uploaded, not processed
    PROCESSING = "processing"  # Pipeline running
    COMPLETED = "completed"    # Pipeline finished successfully
    FAILED = "failed"          # Pipeline failed
    PARTIAL = "partial"        # Partially processed
```

### PipelineStage
```python
class PipelineStage(str, Enum):
    STAGE_0_EXTRACTION = "stage_0_extraction"
    STAGE_1_SEGMENTATION = "stage_1_segmentation"
    STAGE_2_HEADINGS = "stage_2_headings"
    STAGE_3_TOC_ALIGNMENT = "stage_3_toc_alignment"
    STAGE_4_TOC_NORMALIZATION = "stage_4_toc_normalization"
    STAGE_5_CHUNKING = "stage_5_chunking"
    STAGE_5B_ENTITIES = "stage_5b_entities"
    STAGE_6_VISION = "stage_6_vision"
    STAGE_7_EMBEDDING = "stage_7_embedding"
```

### StageStatus
```python
class StageStatus(str, Enum):
    PENDING = "pending"      # Not started
    RUNNING = "running"      # Currently executing
    COMPLETED = "completed"  # Finished successfully
    FAILED = "failed"        # Failed with error
    SKIPPED = "skipped"      # Intentionally skipped
```

### SemanticType
```python
class SemanticType(str, Enum):
    DEFINITION = "definition"    # Term definitions
    PROCEDURE = "procedure"      # Step-by-step instructions
    EXAMPLE = "example"          # Examples and illustrations
    EXPLANATION = "explanation"  # General explanations
    REFERENCE = "reference"      # Citations and references
    LIST = "list"                # Lists and enumerations
    COMPARISON = "comparison"    # Comparative content
    WARNING = "warning"          # Warnings and cautions
    NOTE = "note"                # Notes and remarks
    CODE = "code"                # Code snippets
    FORMULA = "formula"          # Mathematical formulas
```

### EntityType
```python
class EntityType(str, Enum):
    TABLE = "table"
    IMAGE = "image"
    DIAGRAM = "diagram"
    CHART = "chart"
    EQUATION = "equation"
```

### TOCLevel
```python
class TOCLevel(int, Enum):
    L1 = 1  # Top-level (Chapter)
    L2 = 2  # Second-level (Section)
    L3 = 3  # Third-level (Subsection)
```

### Language
```python
class Language(str, Enum):
    KOREAN = "ko"
    ENGLISH = "en"
    MIXED = "mixed"
    UNKNOWN = "unknown"
```

---

## Document Models

### DocumentMetadata
```python
class DocumentMetadata(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    creator: Optional[str] = None
    page_count: int = 0
    file_size_bytes: int = 0
    detected_language: Language = Language.UNKNOWN
```

### Document
```python
class Document(BaseModel):
    id: str                                    # UUID
    filename: str                              # Stored filename
    original_filename: str                     # Original upload name
    file_path: str                             # Path to PDF
    upload_timestamp: datetime
    status: DocumentStatus = DocumentStatus.UPLOADED
    metadata: DocumentMetadata
    raw_text: Optional[str] = None             # Full text (Stage 0)
    raw_text_by_page: list[str] = []           # Text per page
    current_stage: Optional[PipelineStage] = None
    error_message: Optional[str] = None
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None
```

---

## TOC Models

### TOCNode
```python
class TOCNode(BaseModel):
    id: str                                    # UUID
    document_id: str
    level: TOCLevel                            # L1, L2, L3
    title: str                                 # Original title
    normalized_title: str                      # Standardized title
    sequence_number: int                       # Order in document
    parent_id: Optional[str] = None            # Parent node ID
    children_ids: list[str] = []               # Child node IDs
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    retrieval_chunk_ids: list[str] = []        # Linked retrieval chunks
    generation_chunk_ids: list[str] = []       # Linked generation chunks
    entity_ids: list[str] = []                 # Linked entities
```

### TOCStructure
```python
class TOCStructure(BaseModel):
    document_id: str
    root_nodes: list[str] = []                 # Top-level node IDs
    all_nodes: list[TOCNode] = []
    total_l1: int = 0
    total_l2: int = 0
    total_l3: int = 0
```

---

## Segment Models

### Segment
```python
class Segment(BaseModel):
    segment_id: int
    content: str
    page_number: int
    position_in_page: int = 0
    semantic_type: SemanticType = SemanticType.EXPLANATION
    key_concepts: list[str] = []
    reasoning: str = ""                        # LLM reasoning for classification
```

### SegmentWithHeading
```python
class SegmentWithHeading(BaseModel):
    segment: Segment
    candidate_headings: list[str] = []         # Possible headings
    confidence_scores: list[float] = []        # Per-heading confidence
    selected_heading: Optional[str] = None     # Best match
    heading_level: Optional[TOCLevel] = None   # L1, L2, L3
```

---

## Chunk Models

### RetrievalChunk
Optimized for vector search (100-300 tokens).

```python
class RetrievalChunk(BaseModel):
    id: str                                    # UUID
    document_id: str
    toc_node_id: str                           # Parent TOC node
    content: str                               # Dense searchable content
    semantic_type: SemanticType
    key_concepts: list[str] = []
    page_numbers: list[int] = []
    sequence_in_document: int = 0              # Global order
    sequence_in_toc_node: int = 0              # Order within TOC node
    generation_chunk_id: str                   # Linked generation chunk
    embedding: Optional[list[float]] = None   # Vector embedding
    embedding_model: Optional[str] = None     # Model used
    created_at: datetime
    token_count: int = 0
```

### GenerationChunk
Detailed content for answer generation (500-1500 tokens).

```python
class GenerationChunk(BaseModel):
    id: str                                    # UUID
    document_id: str
    toc_node_id: str                           # Parent TOC node
    content: str                               # Full detailed content
    summary: str = ""                          # Brief summary
    semantic_type: SemanticType
    key_concepts: list[str] = []
    context_path: str = ""                     # "Chapter > Section > Topic"
    parent_summary: Optional[str] = None
    page_numbers: list[int] = []
    sequence_in_document: int = 0
    retrieval_chunk_ids: list[str] = []        # Linked retrieval chunks
    entity_ids: list[str] = []                 # Linked entities
    created_at: datetime
    token_count: int = 0
```

---

## Entity Models

### TableCell
```python
class TableCell(BaseModel):
    row: int
    col: int
    content: str
    rowspan: int = 1
    colspan: int = 1
    is_header: bool = False
```

### TableStructure
```python
class TableStructure(BaseModel):
    rows: int
    cols: int
    headers: list[str] = []
    cells: list[TableCell] = []
    has_merged_cells: bool = False
```

### BoundingBox
```python
class BoundingBox(BaseModel):
    x0: float  # Normalized 0-1
    y0: float
    x1: float
    y1: float
```

### Entity
```python
class Entity(BaseModel):
    id: str                                    # UUID
    document_id: str
    toc_node_id: Optional[str] = None          # Parent TOC node
    generation_chunk_id: Optional[str] = None  # Linked chunk
    entity_type: EntityType                    # table, image, etc.
    page_number: int
    sequence_in_page: int = 0
    bbox: Optional[BoundingBox] = None
    canonical_json: Optional[dict] = None      # Structured data
    markdown: Optional[str] = None             # Markdown representation
    ir_yaml: Optional[str] = None              # Intermediate representation
    image_path: Optional[str] = None
    image_base64: Optional[str] = None
    vision_description: Optional[str] = None   # From vision model
    vision_processed: bool = False
    caption: Optional[str] = None
    surrounding_context: Optional[str] = None
    created_at: datetime
```

---

## Pipeline State Models

### StageResult
```python
class StageResult(BaseModel):
    stage: PipelineStage
    status: StageStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    output_summary: Optional[dict] = None
```

### PipelineState
```python
class PipelineState(BaseModel):
    id: str                                    # UUID
    document_id: str
    stages: dict[str, StageResult] = {}        # stage_name -> result
    current_stage: Optional[PipelineStage] = None
    last_completed_stage: Optional[PipelineStage] = None
    stage_outputs: dict[str, str] = {}         # stage_name -> output path
    started_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    total_duration_seconds: Optional[float] = None
    config_snapshot: Optional[dict] = None     # Settings at execution time
```

---

## Search Models

### SearchQuery
```python
class SearchQuery(BaseModel):
    query: str
    document_ids: Optional[list[str]] = None   # Filter by documents
    top_k: int = 10                            # Max results (1-100)
    min_score: float = 0.0                     # Score threshold (0-1)
    include_entities: bool = True
```

### SearchResult
```python
class SearchResult(BaseModel):
    retrieval_chunk: RetrievalChunk
    generation_chunk: GenerationChunk
    toc_node: TOCNode
    entities: list[Entity] = []
    score: float                               # Similarity score
    context_path: str                          # Navigation path
```

### SearchResponse
```python
class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total_found: int
    processing_time_ms: float
```
