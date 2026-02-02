FROM python:3.11-slim-bookworm

# Install system dependencies
# tesseract-ocr is required for the OCR features
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-kor \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
RUN pip install uv

WORKDIR /app

# Copy dependency files and README (required by pyproject.toml)
COPY pyproject.toml uv.lock README.md ./

# Install dependencies using uv
# --system installs into the system python environment, avoiding the need for venv activation
RUN uv pip install --system .

# Copy source code
COPY src ./src
COPY .env .

# Create directories for data
RUN mkdir -p uploads pipeline_state

# Expose port
EXPOSE 8000

# Run the application
# Using fastap run for production-ready server or uvicorn directly
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
