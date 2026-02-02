# RAG VectorDB PDF Pipeline - Full Specification

## Executive Summary

This specification defines a production-ready RAG (Retrieval-Augmented Generation) pipeline for processing PDF documents. The system extracts text and visual elements, structures content hierarchically using TOC-based organization, and enables semantic search through a dual-chunk architecture.

## Key Architectural Decisions

- **Dual-Chunk System**: Separation of retrieval (short, embedding-optimized) and generation (detailed, context-rich) chunks
- **8-Stage Pipeline**: Modular, resumable processing with state persistence
- **Entity-First Design**: Tables and images as first-class entities with canonical JSON + derived Markdown
- **TOC Hierarchy**: L1/L2/L3 structure linking all content for contextual retrieval

## Tech Stack

| Area | Technology |
|------|------------|
| Backend | FastAPI |
| Frontend | React + Tailwind (Vite) |
| Database | MongoDB (Docker) |
| LLM | gpt-4o-mini (text), gpt-4o (vision) |
| Embeddings | text-embedding-3-small (1536 dims) |
| OCR | PyMuPDF + pytesseract |

## Pipeline Stages

| Stage | Purpose | Input | Output |
|-------|---------|-------|--------|
| 0 | PDF Extraction | PDF file | raw_text + tables + images |
| 1 | Semantic Segmentation | raw_text | segments[] |
| 2 | Heading Generation | segments[] | segments + headings |
| 3 | TOC Alignment | segments + headings | toc_structure |
| 4 | TOC Normalization | toc_structure | normalized_toc |
| 5 | Dual Chunking | normalized_toc + segments | retrieval[] + generation[] |
| 5b | Entity Extraction | tables + images | entities[] |
| 6 | Vision (optional) | images | enhanced descriptions |
| 7 | Embedding | retrieval_chunks | embedding vectors |

## Project Structure

```
260128_OCR_skills/
├── pyproject.toml
├── docker-compose.yml
├── .env
├── pipeline_state/
├── uploads/
├── src/
│   ├── api/
│   │   ├── main.py
│   │   ├── dependencies.py
│   │   └── routers/
│   │       ├── documents.py
│   │       ├── pipeline.py
│   │       └── search.py
│   ├── core/
│   │   ├── config.py
│   │   ├── models.py
│   │   └── exceptions.py
│   ├── ocr/
│   │   ├── extractor.py
│   │   ├── text_handler.py
│   │   ├── table_handler.py
│   │   └── image_handler.py
│   ├── pipeline/
│   │   ├── orchestrator.py
│   │   ├── state_manager.py
│   │   ├── stage0_extraction.py
│   │   ├── stage1_segmentation.py
│   │   ├── stage2_headings.py
│   │   ├── stage3_toc_alignment.py
│   │   ├── stage4_toc_normalization.py
│   │   ├── stage5_chunking.py
│   │   ├── stage5b_entities.py
│   │   ├── stage6_vision.py
│   │   └── stage7_embedding.py
│   ├── prompts/
│   │   └── templates/
│   ├── llm/
│   │   ├── openai_client.py
│   │   └── vision_client.py
│   ├── embeddings/
│   │   └── openai_provider.py
│   ├── db/
│   │   ├── mongodb.py
│   │   └── repositories/
│   │       ├── document_repo.py
│   │       ├── chunk_repo.py
│   │       ├── toc_repo.py
│   │       └── entity_repo.py
│   └── utils/
│       ├── language_detector.py
│       └── image_classifier.py
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── App.tsx
│       ├── components/
│       ├── pages/
│       ├── api/
│       ├── hooks/
│       ├── store/
│       └── types/
└── tests/
```

## API Endpoints

### Documents
- `POST /api/v1/documents/upload` - Upload PDF
- `GET /api/v1/documents/{id}` - Get document details
- `GET /api/v1/documents` - List documents
- `DELETE /api/v1/documents/{id}` - Delete document
- `GET /api/v1/documents/{id}/toc` - Get TOC structure

### Pipeline
- `POST /api/v1/pipeline/run` - Start/resume pipeline
- `GET /api/v1/pipeline/status/{id}` - Get pipeline status
- `POST /api/v1/pipeline/cancel/{id}` - Cancel pipeline
- `POST /api/v1/pipeline/retry/{id}` - Retry failed stage

### Search
- `POST /api/v1/search/semantic` - Vector search
- `POST /api/v1/search/toc` - TOC search
- `GET /api/v1/search/chunks/{id}` - List chunks
- `GET /api/v1/search/entities/{id}` - List entities

## MongoDB Collections

- `documents` - Document metadata and raw text
- `toc_nodes` - Hierarchical TOC structure
- `retrieval_chunks` - Short chunks with embeddings
- `generation_chunks` - Detailed chunks for answers
- `entities` - Tables, images, diagrams
- `pipeline_states` - Pipeline execution state

## Dual-Chunk System

### Retrieval Chunk (100-300 tokens)
- Short, dense semantic content
- Optimized for embedding similarity search
- Links to TOC node and generation chunk

### Generation Chunk (500-1500 tokens)
- Detailed, context-rich content
- Contains summary and context path
- Links to retrieval chunks and entities

### Search Flow
1. Query → Embedding
2. Vector search on retrieval chunks
3. Get matched TOC node IDs
4. Fetch linked generation chunks + entities
5. Return enriched results with context path

## Environment Variables

```
OPENAI_API_KEY=sk-...
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=rag_vectordb
OPENAI_MODEL=gpt-4o-mini
VISION_MODEL=gpt-4o
EMBEDDING_MODEL=text-embedding-3-small
MAX_CHUNK_TOKENS=1000
PIPELINE_STATE_DIR=./pipeline_state
UPLOAD_DIR=./uploads
```

## Implementation Phases

### Phase 1: Foundation
- Project setup (uv, dependencies)
- Docker (MongoDB)
- Configuration and models
- Database connection

### Phase 2: OCR & Extraction
- PyMuPDF text extraction
- Table extraction
- Image extraction
- Language detection

### Phase 3: LLM Integration
- OpenAI client with structured output
- Prompt templates
- Vision client

### Phase 4: Pipeline
- All 8 stages
- State manager (persistence/resume)
- Orchestrator

### Phase 5: Search
- Embedding provider
- Vector search with dual-chunk linkage
- Filtering

### Phase 6: Frontend
- React + Tailwind setup
- Upload, Search, Pipeline components
- API integration
