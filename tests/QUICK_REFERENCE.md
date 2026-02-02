# Test Quick Reference

## One-Time Setup

```bash
# 1. Install dependencies
pip install -e ".[dev]"

# 2. Start MongoDB
docker run -d -p 27017:27017 --name mongodb-test mongo:latest

# 3. Verify setup
pytest --version
mongosh mongodb://localhost:27017 --eval "db.version()"
```

## Common Commands

### Run Tests

```bash
# All tests
pytest

# Verbose output
pytest -v

# Very verbose (show all output)
pytest -vv

# Stop on first failure
pytest -x

# Show print statements
pytest -s

# Quiet mode (only show summary)
pytest -q
```

### Coverage

```bash
# Run with coverage
pytest --cov=src

# HTML coverage report
pytest --cov=src --cov-report=html

# Terminal coverage report
pytest --cov=src --cov-report=term

# Missing lines report
pytest --cov=src --cov-report=term-missing

# Coverage for specific module
pytest --cov=src.ocr tests/test_ocr.py
```

### Run Specific Tests

```bash
# Single test file
pytest tests/test_models.py

# Single test function
pytest tests/test_models.py::test_generate_id

# Test class
pytest tests/test_models.py::TestDocumentModel

# Tests matching pattern
pytest -k "document"

# Tests NOT matching pattern
pytest -k "not async"
```

### Filtering

```bash
# Only failed tests from last run
pytest --lf

# Failed tests first, then rest
pytest --ff

# Only tests modified since last commit
pytest --testmon
```

### Output & Debugging

```bash
# Show local variables on failure
pytest -l

# Show full diff on assertion failures
pytest -vv

# Disable warnings
pytest --disable-warnings

# Show warnings
pytest -W default

# Step into debugger on failure
pytest --pdb
```

### Parallel Execution

```bash
# Install pytest-xdist first
pip install pytest-xdist

# Run tests in parallel (auto-detect CPUs)
pytest -n auto

# Run with 4 workers
pytest -n 4
```

## Test Selection Examples

```bash
# All model tests
pytest tests/test_models.py -v

# All OCR tests
pytest tests/test_ocr.py -v

# All search tests
pytest tests/test_search.py -v

# All pipeline tests
pytest tests/test_pipeline.py -v

# All API tests
pytest tests/test_api.py -v

# All async tests
pytest -k "async" -v

# All non-async tests
pytest -k "not async" -v
```

## Coverage Shortcuts

```bash
# Quick coverage check
pytest --cov=src --cov-report=term-missing --no-cov-on-fail

# Generate HTML report and open
pytest --cov=src --cov-report=html && start htmlcov/index.html

# Coverage for single module
pytest tests/test_models.py --cov=src.core.models --cov-report=term
```

## Markers (Custom)

Add to pyproject.toml:
```toml
[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow",
    "integration: marks tests as integration tests",
    "unit: marks tests as unit tests",
]
```

Then use:
```bash
# Run only unit tests
pytest -m unit

# Skip slow tests
pytest -m "not slow"

# Run integration tests
pytest -m integration
```

## Debugging Failed Tests

```bash
# Run last failed with detailed output
pytest --lf -vv

# Run with debugger
pytest --pdb tests/test_models.py::test_failing

# Show captured output on failure
pytest --tb=short

# Show full traceback
pytest --tb=long

# No traceback
pytest --tb=no
```

## CI/CD Commands

```bash
# Run in CI mode (strict)
pytest --strict-markers --tb=short

# With coverage threshold
pytest --cov=src --cov-fail-under=80

# Generate XML report for CI
pytest --cov=src --cov-report=xml --junitxml=test-results.xml
```

## Cleanup

```bash
# Clean pytest cache
pytest --cache-clear

# Clean coverage data
rm -rf .coverage htmlcov/ .pytest_cache/

# Clean MongoDB test database
mongosh mongodb://localhost:27017 --eval "use test_rag_vectordb; db.dropDatabase();"

# Stop test MongoDB container
docker stop mongodb-test
docker rm mongodb-test
```

## Performance

```bash
# Show slowest 10 tests
pytest --durations=10

# Show all test durations
pytest --durations=0

# Profile tests
pip install pytest-profiling
pytest --profile

# Benchmark tests
pip install pytest-benchmark
pytest --benchmark-only
```

## Environment

```bash
# Show pytest configuration
pytest --version --verbose

# Show fixtures
pytest --fixtures

# Show markers
pytest --markers

# Collect tests without running
pytest --collect-only

# Dry run
pytest --setup-plan
```

## Watching for Changes

```bash
# Install pytest-watch
pip install pytest-watch

# Auto-run tests on file changes
ptw

# With coverage
ptw -- --cov=src
```

## Common Issues

### MongoDB not running
```bash
docker ps | grep mongodb
docker start mongodb-test
```

### Import errors
```bash
pip install -e .
python -c "import src; print('OK')"
```

### Async test failures
```bash
pip install pytest-asyncio
pytest tests/test_pipeline.py -v
```

### Coverage not working
```bash
pip install pytest-cov
pytest --cov=src --cov-report=term
```

## Useful Combinations

```bash
# Quick check (fast, minimal output)
pytest -q --tb=line

# Full validation (verbose, coverage, strict)
pytest -v --cov=src --cov-report=term-missing --strict-markers

# Debug mode (stop on first failure, show output, debugger)
pytest -x -s --pdb

# CI mode (coverage threshold, XML reports)
pytest --cov=src --cov-fail-under=80 --junitxml=results.xml --cov-report=xml
```

## VSCode Integration

Add to `.vscode/settings.json`:
```json
{
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false,
  "python.testing.pytestArgs": [
    "tests",
    "-v"
  ]
}
```

Then use VSCode Test Explorer to run/debug tests visually.

## Pre-commit Hook

Create `.git/hooks/pre-commit`:
```bash
#!/bin/sh
pytest --co -q > /dev/null || exit 1
pytest tests/ -x || exit 1
```

```bash
chmod +x .git/hooks/pre-commit
```

## Documentation

- Full docs: `tests/README.md`
- Setup guide: `tests/SETUP.md`
- Test summary: `tests/TEST_SUMMARY.md`
- This reference: `tests/QUICK_REFERENCE.md`
