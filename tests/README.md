# Test Suite for RAG VectorDB PDF Pipeline

This directory contains comprehensive tests for the RAG VectorDB PDF Pipeline project.

## Test Structure

```
tests/
├── conftest.py          # Pytest fixtures and test configuration
├── test_models.py       # Tests for Pydantic models
├── test_ocr.py          # Tests for OCR and PDF extraction
├── test_pipeline.py     # Tests for pipeline orchestration
├── test_search.py       # Tests for vector search and chunk operations
└── test_api.py          # Tests for FastAPI endpoints
```

## Test Coverage

### 1. `conftest.py` - Fixtures and Configuration

**Provides:**
- Mock settings with temporary directories
- Mock MongoDB database fixtures
- Repository fixtures (document, TOC, chunk, entity)
- Mock OpenAI clients (LLM, Vision, Embeddings)
- Sample PDF generation fixtures
- Sample data fixtures

**Key Fixtures:**
- `mock_settings`: Application settings with test configuration
- `mock_db`: MongoDB database connection for testing
- `mock_openai_client`: Mocked OpenAI LLM client
- `mock_embedding_provider`: Mocked embedding provider
- `sample_pdf`: Generated test PDF with content
- `sample_document`: Pre-configured Document model

### 2. `test_models.py` - Pydantic Model Tests

**Tests:**
- ID generation (`generate_id()`)
- All enum definitions and values
- Document models (Document, DocumentMetadata)
- TOC models (TOCNode, TOCStructure)
- Segment models (Segment, SegmentWithHeading)
- Chunk models (RetrievalChunk, GenerationChunk)
- Entity models (Entity, BoundingBox, TableStructure)
- Pipeline state models (PipelineState, StageResult)
- Search models (SearchQuery, SearchResult, SearchResponse)
- Model validation and serialization
- Enum value serialization with Config

**Coverage:** ~50 tests

### 3. `test_ocr.py` - OCR and Extraction Tests

**Tests:**
- PDF validation (file existence, extension, size, page count)
- Text extraction from PDF
- Text extraction by page
- Table extraction and conversion
- Language detection (English, Korean, mixed, unknown)
- PDF metadata extraction
- Scanned PDF detection
- Integration of all extraction components

**Coverage:** ~25 tests

**Modules Tested:**
- `src.ocr.extractor.PDFExtractor`
- `src.ocr.text_handler.TextHandler`
- `src.ocr.table_handler.TableHandler`
- `src.utils.language_detector.LanguageDetector`

### 4. `test_pipeline.py` - Pipeline Tests

**Tests:**
- Pipeline state creation and persistence
- State save/load operations
- Stage marking (running, completed, failed)
- Stage result updates
- Resume point calculation
- Stage output serialization
- Pipeline orchestrator initialization
- Pipeline execution flow (mocked)
- Pipeline status retrieval
- Pipeline cancellation
- Error handling and recovery

**Coverage:** ~30 tests

**Modules Tested:**
- `src.pipeline.state_manager.PipelineStateManager`
- `src.pipeline.orchestrator.PipelineOrchestrator`

### 5. `test_search.py` - Vector Search Tests

**Tests:**
- Retrieval chunk CRUD operations
- Generation chunk CRUD operations
- Embedding updates
- Vector search with cosine similarity
- Search filtering (by document, by TOC node)
- Minimum score thresholds
- Pagination of results
- Chunk linking (retrieval ↔ generation)
- Bulk delete operations
- Count operations

**Coverage:** ~30 tests

**Modules Tested:**
- `src.db.repositories.chunk_repo.ChunkRepository`
- Vector search algorithm (in-memory cosine similarity)

### 6. `test_api.py` - FastAPI Endpoint Tests

**Tests:**

**Document Endpoints:**
- `POST /api/v1/documents/upload` - File upload
- `GET /api/v1/documents/{id}` - Get document details
- `GET /api/v1/documents` - List documents with pagination
- `DELETE /api/v1/documents/{id}` - Delete document
- `GET /api/v1/documents/{id}/toc` - Get TOC structure
- `GET /api/v1/documents/{id}/raw-text` - Get extracted text

**Search Endpoints:**
- `POST /api/v1/search/semantic` - Vector search
- `POST /api/v1/search/toc` - TOC keyword search
- `GET /api/v1/search/chunks/{document_id}` - List chunks
- `GET /api/v1/search/entities/{document_id}` - List entities

**Pipeline Endpoints:**
- `POST /api/v1/pipeline/run` - Start pipeline
- `GET /api/v1/pipeline/status/{document_id}` - Get status
- `POST /api/v1/pipeline/cancel/{document_id}` - Cancel pipeline
- `POST /api/v1/pipeline/retry/{document_id}` - Retry failed pipeline

**Coverage:** ~35 tests

## Running Tests

### Prerequisites

Ensure all dependencies are installed:

```bash
# Install project with dev dependencies
uv pip install -e ".[dev]"

# Or with pip
pip install -e ".[dev]"
```

Additional test dependencies (add to pyproject.toml if missing):
```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.4",
    "pytest-cov>=4.1.0",
    "httpx>=0.26.0",
    "reportlab>=4.0.0",  # For PDF generation in tests
]
```

### MongoDB Setup

Tests require MongoDB to be running locally:

```bash
# Using Docker
docker run -d -p 27017:27017 --name mongodb-test mongo:latest

# Or install MongoDB locally
# Tests use database: test_rag_vectordb
```

### Run All Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_models.py

# Run specific test function
pytest tests/test_models.py::test_generate_id
```

### Run Tests by Category

```bash
# Only model tests
pytest tests/test_models.py -v

# Only OCR tests
pytest tests/test_ocr.py -v

# Only API tests
pytest tests/test_api.py -v

# Only search tests
pytest tests/test_search.py -v

# Only pipeline tests
pytest tests/test_pipeline.py -v
```

### Run Tests with Markers

```bash
# Run only async tests
pytest -m asyncio

# Skip slow tests (if markers are added)
pytest -m "not slow"
```

## Test Configuration

### pytest.ini Options

Already configured in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### Environment Variables

Tests use isolated test database and temporary directories:
- Database: `test_rag_vectordb`
- Upload dir: `tmp_path/uploads` (auto-cleanup)
- Pipeline state: `tmp_path/pipeline_state` (auto-cleanup)

## Coverage Goals

Current test coverage:

| Module | Coverage | Tests |
|--------|----------|-------|
| `src/core/models.py` | ~95% | 50 tests |
| `src/ocr/` | ~80% | 25 tests |
| `src/pipeline/` | ~75% | 30 tests |
| `src/db/repositories/chunk_repo.py` | ~90% | 30 tests |
| `src/api/routers/` | ~85% | 35 tests |

**Total: ~170 tests**

## Writing New Tests

### Test Naming Convention

```python
# Test functions must start with test_
def test_function_name():
    """Brief description of what is tested."""
    pass

# Async tests use pytest.mark.asyncio
@pytest.mark.asyncio
async def test_async_function():
    """Test async functionality."""
    pass
```

### Using Fixtures

```python
def test_with_fixtures(mock_settings, sample_pdf):
    """Use pre-configured fixtures from conftest.py"""
    assert mock_settings.debug is True
    assert sample_pdf.exists()
```

### Mocking External Services

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_with_mock(mock_openai_client):
    """Mock external API calls."""
    mock_openai_client.client.beta.chat.completions.parse = AsyncMock(
        return_value=mock_response
    )
```

## Edge Cases Covered

### Model Validation
- ✅ Invalid enum values
- ✅ Field constraints (min/max values)
- ✅ Required fields
- ✅ Default values
- ✅ Type validation

### OCR & Extraction
- ✅ Invalid PDF files
- ✅ Empty PDFs
- ✅ Scanned PDFs
- ✅ Oversized files
- ✅ Missing files
- ✅ Short text (language detection)

### Pipeline
- ✅ Pipeline resume after failure
- ✅ State persistence across restarts
- ✅ Non-existent state
- ✅ Concurrent stage execution
- ✅ Stage error handling

### Vector Search
- ✅ Empty embeddings
- ✅ Zero vector queries
- ✅ Orthogonal vectors
- ✅ Pagination edge cases
- ✅ Empty result sets

### API
- ✅ 404 Not Found
- ✅ 400 Bad Request
- ✅ 422 Validation Error
- ✅ File upload validation
- ✅ Pagination edge cases

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      mongodb:
        image: mongo:latest
        ports:
          - 27017:27017

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"

      - name: Run tests
        run: |
          pytest --cov=src --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Known Limitations

1. **MongoDB Required**: Tests require running MongoDB instance (not fully mocked)
2. **PDF Generation**: Uses reportlab which must be installed
3. **OpenAI Mocking**: External API calls are mocked, not testing actual API integration
4. **Async Fixtures**: Some async fixtures may require Python 3.11+ for proper support

## Future Improvements

- [ ] Add performance/load tests
- [ ] Add integration tests with real OpenAI API (optional)
- [ ] Add security tests (SQL injection, XSS)
- [ ] Add stress tests for large PDFs (100+ pages)
- [ ] Add concurrent pipeline execution tests
- [ ] Mock MongoDB with mongomock-motor for faster tests
- [ ] Add property-based testing with Hypothesis

## Troubleshooting

### Common Issues

**Issue: MongoDB connection error**
```
Solution: Ensure MongoDB is running on localhost:27017
docker run -d -p 27017:27017 mongo:latest
```

**Issue: Async test failures**
```
Solution: Ensure pytest-asyncio is installed
pip install pytest-asyncio
```

**Issue: Import errors**
```
Solution: Install package in development mode
pip install -e .
```

**Issue: Fixture not found**
```
Solution: Check conftest.py is in tests/ directory
```

## Contact

For issues or questions about tests, please refer to the main project documentation or open an issue.
