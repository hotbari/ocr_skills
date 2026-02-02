# Test Setup Guide

## Quick Start

### 1. Install Dependencies

```bash
# Navigate to project root
cd C:\Users\user\Desktop\Project\260127_claude_master\260128_OCR_skills

# Install main dependencies (if not already done)
pip install -e .

# Install development/testing dependencies
pip install -e ".[dev]"

# Or install individually
pip install pytest pytest-asyncio pytest-cov reportlab
```

### 2. Start MongoDB

Tests require a running MongoDB instance:

```bash
# Option 1: Using Docker (recommended)
docker run -d -p 27017:27017 --name mongodb-test mongo:latest

# Option 2: Using installed MongoDB
# Ensure MongoDB is running on localhost:27017

# Verify connection
mongosh mongodb://localhost:27017
```

### 3. Run Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_models.py -v

# Run specific test
pytest tests/test_models.py::test_generate_id -v
```

## Test Files Overview

| File | Purpose | Test Count | Dependencies |
|------|---------|------------|--------------|
| `conftest.py` | Fixtures & setup | N/A | motor, reportlab |
| `test_models.py` | Pydantic model tests | ~50 | None (unit) |
| `test_ocr.py` | OCR & extraction | ~25 | pymupdf, reportlab |
| `test_pipeline.py` | Pipeline orchestration | ~30 | motor |
| `test_search.py` | Vector search | ~30 | motor, numpy |
| `test_api.py` | FastAPI endpoints | ~35 | motor, fastapi |

**Total: ~170 tests**

## Expected Output

When tests pass successfully, you should see:

```
collected 170 items

tests/test_models.py ................................................... [ 30%]
tests/test_ocr.py ..........................                           [ 45%]
tests/test_pipeline.py ..............................                 [ 63%]
tests/test_search.py ..............................                   [ 80%]
tests/test_api.py ...................................                 [100%]

===================== 170 passed in 45.23s =====================
```

## Troubleshooting

### Issue: ModuleNotFoundError: No module named 'motor'

**Solution:**
```bash
pip install motor pymongo
```

### Issue: ModuleNotFoundError: No module named 'reportlab'

**Solution:**
```bash
pip install reportlab
```

### Issue: MongoDB connection error

**Solution:**
```bash
# Check MongoDB is running
docker ps  # Should show mongodb-test container

# Restart MongoDB
docker restart mongodb-test

# Or start new instance
docker run -d -p 27017:27017 --name mongodb-test mongo:latest
```

### Issue: Test database not cleaned up

**Solution:**
```bash
# Connect to MongoDB and drop test database
mongosh mongodb://localhost:27017
use test_rag_vectordb
db.dropDatabase()
```

### Issue: Async tests failing

**Solution:**
```bash
# Ensure pytest-asyncio is installed
pip install pytest-asyncio

# Check pytest.ini_options in pyproject.toml includes:
# asyncio_mode = "auto"
```

## Environment Variables

Tests use the following environment (automatically configured in conftest.py):

```
OPENAI_API_KEY=test-key-123  (mocked, not real)
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=test_rag_vectordb
```

No .env file needed for tests.

## Coverage Report

After running with coverage:

```bash
pytest --cov=src --cov-report=html
```

Open `htmlcov/index.html` in a browser to view detailed coverage report.

Target coverage: **>80%** for all modules.

## Next Steps

1. ✅ Install dependencies
2. ✅ Start MongoDB
3. ✅ Run tests
4. ✅ View coverage report
5. ⬜ Add more tests as needed
6. ⬜ Integrate with CI/CD

## Notes

- Tests use temporary directories (auto-cleaned)
- Tests use isolated test database (`test_rag_vectordb`)
- External APIs (OpenAI) are mocked
- PDFs are generated programmatically for tests
