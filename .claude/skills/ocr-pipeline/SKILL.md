---
name: ocr-pipeline
description: 8-stage OCR document processing pipeline for RAG systems. Use when processing PDF documents for text extraction, semantic segmentation, TOC generation, dual-chunking (retrieval + generation), entity extraction, vision processing, and embedding generation. Triggers on PDF processing, document ingestion, RAG pipeline, chunk creation, or TOC extraction tasks.
---

# OCR Pipeline

## Overview

This skill provides guidance for working with the 8-stage OCR document processing pipeline designed for RAG (Retrieval-Augmented Generation) systems. The pipeline transforms PDF documents into searchable, semantically-enriched chunks with embeddings.

## Pipeline Architecture

```
PDF Input
    |
    v
[Stage 0] Extraction -----> raw text, tables, images, language detection
    |
    v
[Stage 1] Segmentation ---> semantic units from raw text
    |
    v
[Stage 2] Headings -------> heading extraction & hierarchy
    |
    v
[Stage 3] TOC Alignment --> align headings with TOC structure
    |
    v
[Stage 4] Normalization --> standardize TOC nodes
    |
    v
[Stage 5] Chunking -------> dual chunks (retrieval + generation)
    |
[Stage 5B] Entities ------> tables/images with TOC mapping
    |
    v
[Stage 6] Vision ---------> optional vision model processing
    |
    v
[Stage 7] Embedding ------> vector embeddings for retrieval
    |
    v
MongoDB Storage
```

## Stage Reference

| Stage | Purpose | Input | Output |
|-------|---------|-------|--------|
| 0 | PDF Extraction | PDF file | raw_text, tables, images, language |
| 1 | Segmentation | raw_text | semantic segments |
| 2 | Headings | segments | segments with candidate headings |
| 3 | TOC Alignment | segments + headings | TOC nodes + segment mapping |
| 4 | Normalization | TOC nodes | normalized TOC structure |
| 5 | Chunking | TOC + segments | retrieval + generation chunks |
| 5B | Entities | tables + images | entities with TOC context |
| 6 | Vision | entities | vision descriptions |
| 7 | Embedding | retrieval chunks | chunks with embeddings |

## Quick Start

### Run Pipeline via API

```bash
# Start pipeline
POST /api/v1/pipeline/run
{
    "document_id": "doc-uuid",
    "skip_vision": false,
    "force_restart": false
}

# Check status
GET /api/v1/pipeline/status/{document_id}

# Get stage result
GET /api/v1/pipeline/stage/{document_id}/{stage_name}?include_output=true
```

### Run Pipeline Programmatically

```python
from src.pipeline.orchestrator import PipelineOrchestrator

orchestrator = PipelineOrchestrator(
    document_repo=document_repo,
    toc_repo=toc_repo,
    chunk_repo=chunk_repo,
    entity_repo=entity_repo,
)

result = await orchestrator.run_pipeline(
    document_id="doc-uuid",
    pdf_path=Path("/path/to/document.pdf"),
    skip_vision=False,
    force_restart=False,
)

print(f"Chunks created: {result.total_retrieval_chunks}")
```

## Creating New Stages

To add a new pipeline stage:

1. Create stage file in `src/pipeline/`:

```python
from dataclasses import dataclass
from src.pipeline.base import BaseStage
from src.core.models import PipelineStage

@dataclass
class StageNInput:
    document_id: str
    # ... input fields

@dataclass
class StageNOutput:
    document_id: str
    # ... output fields

class StageNCustom(BaseStage[StageNInput, StageNOutput]):
    stage = PipelineStage.STAGE_N_CUSTOM
    stage_name = "custom"

    def validate_input(self, input_data: StageNInput) -> bool:
        return bool(input_data.document_id)

    def validate_output(self, output_data: StageNOutput) -> bool:
        return True

    async def execute(self, input_data: StageNInput) -> StageNOutput:
        # Implementation
        return StageNOutput(document_id=input_data.document_id)

    def get_output_summary(self, output: StageNOutput) -> dict:
        return {"status": "completed"}
```

2. Register in orchestrator `STAGE_ORDER` and `_init_stages()`

3. Add input wiring in `_execute_stage()`

## Dual-Chunk System

The pipeline creates two types of chunks for optimal RAG performance:

### Retrieval Chunks (100-300 tokens)
- Dense, keyword-rich content
- Optimized for vector similarity search
- Contains key concepts extracted from content

### Generation Chunks (500-1500 tokens)
- Full context with narrative flow
- Includes summary and context path
- Links to related retrieval chunks and entities

```python
# Retrieval chunk structure
RetrievalChunk(
    content="Dense searchable content...",
    key_concepts=["concept1", "concept2"],
    embedding=[0.1, 0.2, ...],  # Added in Stage 7
    generation_chunk_id="linked-gen-chunk-id"
)

# Generation chunk structure
GenerationChunk(
    content="Full detailed content...",
    summary="Brief summary of content",
    context_path="Chapter 1 > Section 1.1 > Topic",
    retrieval_chunk_ids=["ret-1", "ret-2"]
)
```

## Resume Capability

Pipeline supports resuming from failures:

```python
# State is saved after each stage to .pipeline_state/
# On retry, pipeline resumes from last completed stage

# Force restart from beginning
result = await orchestrator.run_pipeline(
    document_id="doc-uuid",
    pdf_path=pdf_path,
    force_restart=True  # Ignores saved state
)
```

## Resources

For detailed documentation:
- **Stage implementations**: See `references/stages.md`
- **Data models**: See `references/models.md`
- **API endpoints**: See `references/api.md`
