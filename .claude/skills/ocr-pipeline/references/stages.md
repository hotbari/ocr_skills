# Pipeline Stages Reference

Detailed documentation for each pipeline stage implementation.

## Table of Contents
- [Stage 0: Extraction](#stage-0-extraction)
- [Stage 1: Segmentation](#stage-1-segmentation)
- [Stage 2: Headings](#stage-2-headings)
- [Stage 3: TOC Alignment](#stage-3-toc-alignment)
- [Stage 4: TOC Normalization](#stage-4-toc-normalization)
- [Stage 5: Chunking](#stage-5-chunking)
- [Stage 5B: Entities](#stage-5b-entities)
- [Stage 6: Vision](#stage-6-vision)
- [Stage 7: Embedding](#stage-7-embedding)

---

## Stage 0: Extraction

**File**: `src/pipeline/stage0_extraction.py`

**Purpose**: Extract raw content from PDF files including text, tables, and images.

**Input**:
```python
@dataclass
class Stage0Input:
    document_id: str
    file_path: Path
```

**Output**:
```python
@dataclass
class Stage0Output:
    document_id: str
    raw_text: str                    # Full document text
    raw_text_by_page: list[str]      # Text per page
    page_count: int
    tables: list[TableData]          # Extracted tables
    images: list[ImageData]          # Extracted images
    detected_language: Language      # ko, en, mixed, unknown
    is_scanned: bool                 # OCR needed?
```

**Key Features**:
- Uses PDFExtractor for text extraction
- Detects document language (Korean/English/Mixed)
- Identifies if document is scanned (requires OCR)
- Extracts tables with structure preservation
- Extracts images with bounding boxes

---

## Stage 1: Segmentation

**File**: `src/pipeline/stage1_segmentation.py`

**Purpose**: Break raw text into meaningful semantic units using LLM.

**Input**:
```python
@dataclass
class Stage1Input:
    document_id: str
    raw_text: str
    raw_text_by_page: list[str]
    page_count: int
```

**Output**:
```python
@dataclass
class Stage1Output:
    document_id: str
    segments: list[Segment]
```

**Segment Structure**:
```python
class Segment(BaseModel):
    segment_id: int
    content: str
    page_number: int
    position_in_page: int
    semantic_type: SemanticType  # definition, procedure, example, etc.
    key_concepts: list[str]
    reasoning: str
```

**Semantic Types**:
- `definition` - Definitions and explanations of terms
- `procedure` - Step-by-step instructions
- `example` - Examples and illustrations
- `explanation` - General explanations
- `reference` - Citations and references
- `list` - Lists and enumerations
- `comparison` - Comparative content
- `warning` - Warnings and cautions
- `note` - Notes and remarks
- `code` - Code snippets
- `formula` - Mathematical formulas

---

## Stage 2: Headings

**File**: `src/pipeline/stage2_headings.py`

**Purpose**: Extract headings and detect hierarchy using LLM.

**Input**:
```python
@dataclass
class Stage2Input:
    document_id: str
    segments: list[Segment]
```

**Output**:
```python
@dataclass
class Stage2Output:
    document_id: str
    segments_with_headings: list[SegmentWithHeading]
```

**SegmentWithHeading Structure**:
```python
class SegmentWithHeading(BaseModel):
    segment: Segment
    candidate_headings: list[str]      # Possible heading titles
    confidence_scores: list[float]     # Confidence per candidate
    selected_heading: Optional[str]    # Best heading
    heading_level: Optional[TOCLevel]  # L1, L2, or L3
```

---

## Stage 3: TOC Alignment

**File**: `src/pipeline/stage3_toc_alignment.py`

**Purpose**: Align extracted headings with document's table of contents structure.

**Input**:
```python
@dataclass
class Stage3Input:
    document_id: str
    segments_with_headings: list[SegmentWithHeading]
```

**Output**:
```python
@dataclass
class Stage3Output:
    document_id: str
    toc_nodes: list[TOCNodeOutput]
    segment_to_toc_mapping: dict[int, str]  # segment_id -> toc_node_id
```

**Key Features**:
- Creates hierarchical TOC structure
- Maps each segment to its parent TOC node
- Handles multi-level hierarchies (L1, L2, L3)

---

## Stage 4: TOC Normalization

**File**: `src/pipeline/stage4_toc_normalization.py`

**Purpose**: Normalize TOC nodes to standardized format.

**Input**:
```python
@dataclass
class Stage4Input:
    document_id: str
    toc_nodes: list[TOCNodeOutput]
    segment_to_toc_mapping: dict[int, str]
```

**Output**:
```python
@dataclass
class Stage4Output:
    document_id: str
    normalized_toc_nodes: list[TOCNode]
```

**TOCNode Structure**:
```python
class TOCNode(BaseModel):
    id: str
    document_id: str
    level: TOCLevel                      # L1, L2, L3
    title: str                           # Original title
    normalized_title: str                # Standardized title
    sequence_number: int
    parent_id: Optional[str]
    children_ids: list[str]
    page_start: Optional[int]
    page_end: Optional[int]
    retrieval_chunk_ids: list[str]       # Linked chunks
    generation_chunk_ids: list[str]
    entity_ids: list[str]                # Linked entities
```

---

## Stage 5: Chunking

**File**: `src/pipeline/stage5_chunking.py`

**Purpose**: Create dual-chunk system (retrieval + generation chunks).

**Input**:
```python
@dataclass
class Stage5Input:
    document_id: str
    normalized_toc_nodes: list[TOCNode]
    segments: list[Segment]
    segment_to_toc_mapping: dict[int, str]
```

**Output**:
```python
@dataclass
class Stage5Output:
    document_id: str
    retrieval_chunks: list[RetrievalChunk]
    generation_chunks: list[GenerationChunk]
```

**Chunking Strategy**:
1. Group segments by TOC node
2. For content > 500 chars: Use LLM for intelligent chunking
3. For smaller content: Use fallback simple chunking
4. Create retrieval chunks (dense, 100-300 tokens)
5. Create generation chunks (detailed, 500-1500 tokens)
6. Link retrieval chunks to their generation counterparts

---

## Stage 5B: Entities

**File**: `src/pipeline/stage5b_entities.py`

**Purpose**: Extract entities (tables, images) with TOC context mapping.

**Input**:
```python
@dataclass
class Stage5bInput:
    document_id: str
    tables: list[TableData]
    images: list[ImageData]
    toc_nodes: list[TOCNode]
    page_to_toc_mapping: dict[int, str]
```

**Output**:
```python
@dataclass
class Stage5bOutput:
    document_id: str
    entities: list[Entity]
```

**Entity Structure**:
```python
class Entity(BaseModel):
    id: str
    document_id: str
    toc_node_id: Optional[str]
    generation_chunk_id: Optional[str]
    entity_type: EntityType           # table, image, diagram, chart, equation
    page_number: int
    sequence_in_page: int
    bbox: Optional[BoundingBox]
    canonical_json: Optional[dict]    # Structured table data
    markdown: Optional[str]           # Markdown representation
    image_path: Optional[str]
    image_base64: Optional[str]
    vision_description: Optional[str] # From Stage 6
    vision_processed: bool
    caption: Optional[str]
    surrounding_context: Optional[str]
```

---

## Stage 6: Vision

**File**: `src/pipeline/stage6_vision.py`

**Purpose**: Process images and tables using vision model (Claude/GPT-4V).

**Input**:
```python
@dataclass
class Stage6Input:
    document_id: str
    entities: list[Entity]
    skip_vision: bool
```

**Output**:
```python
@dataclass
class Stage6Output:
    document_id: str
    processed_entities: list[Entity]
```

**Key Features**:
- Optional stage (can be skipped with `skip_vision=True`)
- Uses VisionClient for multimodal processing
- Generates descriptions for images and complex tables
- Updates entities with `vision_description` field

---

## Stage 7: Embedding

**File**: `src/pipeline/stage7_embedding.py`

**Purpose**: Generate vector embeddings for retrieval chunks.

**Input**:
```python
@dataclass
class Stage7Input:
    document_id: str
    retrieval_chunks: list[RetrievalChunk]
```

**Output**:
```python
@dataclass
class Stage7Output:
    document_id: str
    embedded_chunks: list[RetrievalChunk]  # With embeddings
```

**Embedding Details**:
- Uses OpenAI embedding model (configurable)
- Generates embeddings for each retrieval chunk's content
- Stores embedding vector and model name in chunk

---

## Base Stage Interface

All stages inherit from `BaseStage`:

```python
class BaseStage(ABC, Generic[InputT, OutputT]):
    stage: PipelineStage
    stage_name: str

    @abstractmethod
    async def execute(self, input_data: InputT) -> OutputT:
        """Core stage logic"""
        pass

    @abstractmethod
    def validate_input(self, input_data: InputT) -> bool:
        """Validate input before execution"""
        pass

    @abstractmethod
    def validate_output(self, output_data: OutputT) -> bool:
        """Validate output after execution"""
        pass

    def get_output_summary(self, output_data: OutputT) -> dict:
        """Generate summary for logging"""
        return {"status": "completed"}

    async def run(self, input_data: InputT) -> tuple[OutputT, StageResult]:
        """Full execution with timing, validation, error handling"""
        # Validates input, executes, validates output, returns result
```

For skippable stages, use `SkippableStage`:

```python
class SkippableStage(BaseStage[InputT, OutputT]):
    def should_skip(self, input_data: InputT) -> bool:
        """Return True to skip this stage"""
        return False
```
