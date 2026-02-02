"""Custom exceptions for the RAG VectorDB PDF Pipeline."""

from typing import Any, Optional


class PipelineBaseError(Exception):
    """Base exception for all pipeline errors."""

    code: str = "INTERNAL_ERROR"
    status_code: int = 500

    def __init__(self, message: str, detail: Optional[Any] = None):
        self.message = message
        self.detail = detail
        super().__init__(message)


# ============================================================
# DOCUMENT ERRORS
# ============================================================


class DocumentError(PipelineBaseError):
    """Base class for document-related errors."""

    code = "DOCUMENT_ERROR"


class DocumentNotFoundError(DocumentError):
    """Document not found in database."""

    code = "DOCUMENT_NOT_FOUND"
    status_code = 404


class DocumentUploadError(DocumentError):
    """Error during document upload."""

    code = "DOCUMENT_UPLOAD_ERROR"
    status_code = 400


class InvalidFileTypeError(DocumentError):
    """Invalid file type uploaded."""

    code = "INVALID_FILE_TYPE"
    status_code = 400


class FileSizeExceededError(DocumentError):
    """File size exceeds limit."""

    code = "FILE_SIZE_EXCEEDED"
    status_code = 413


# ============================================================
# PIPELINE ERRORS
# ============================================================


class PipelineError(PipelineBaseError):
    """Base class for pipeline-related errors."""

    code = "PIPELINE_ERROR"


class StageExecutionError(PipelineError):
    """Error during stage execution."""

    code = "STAGE_EXECUTION_ERROR"

    def __init__(self, stage: str, message: str, detail: Optional[Any] = None):
        self.stage = stage
        super().__init__(f"Stage {stage} failed: {message}", detail)


class PipelineStateError(PipelineError):
    """Error with pipeline state management."""

    code = "PIPELINE_STATE_ERROR"


class PipelineResumeError(PipelineError):
    """Error resuming pipeline from saved state."""

    code = "PIPELINE_RESUME_ERROR"


class PipelineNotFoundError(PipelineError):
    """Pipeline state not found."""

    code = "PIPELINE_NOT_FOUND"
    status_code = 404


# ============================================================
# OCR ERRORS
# ============================================================


class OCRError(PipelineBaseError):
    """Base class for OCR-related errors."""

    code = "OCR_ERROR"
    status_code = 422


class TextExtractionError(OCRError):
    """Error extracting text from PDF."""

    code = "TEXT_EXTRACTION_ERROR"


class TableExtractionError(OCRError):
    """Error extracting tables from PDF."""

    code = "TABLE_EXTRACTION_ERROR"


class ImageExtractionError(OCRError):
    """Error extracting images from PDF."""

    code = "IMAGE_EXTRACTION_ERROR"


# ============================================================
# LLM ERRORS
# ============================================================


class LLMError(PipelineBaseError):
    """Base class for LLM-related errors."""

    code = "LLM_ERROR"
    status_code = 502


class LLMRateLimitError(LLMError):
    """OpenAI rate limit exceeded."""

    code = "LLM_RATE_LIMIT"
    status_code = 429


class LLMResponseParseError(LLMError):
    """Failed to parse LLM response."""

    code = "LLM_RESPONSE_PARSE_ERROR"


class LLMTimeoutError(LLMError):
    """LLM request timed out."""

    code = "LLM_TIMEOUT"
    status_code = 504


class LLMContextLengthError(LLMError):
    """Input exceeds LLM context length."""

    code = "LLM_CONTEXT_LENGTH_ERROR"
    status_code = 400


# ============================================================
# EMBEDDING ERRORS
# ============================================================


class EmbeddingError(PipelineBaseError):
    """Base class for embedding-related errors."""

    code = "EMBEDDING_ERROR"
    status_code = 502


class EmbeddingDimensionError(EmbeddingError):
    """Embedding dimension mismatch."""

    code = "EMBEDDING_DIMENSION_ERROR"


# ============================================================
# SEARCH ERRORS
# ============================================================


class SearchError(PipelineBaseError):
    """Base class for search-related errors."""

    code = "SEARCH_ERROR"


class InvalidQueryError(SearchError):
    """Invalid search query."""

    code = "INVALID_QUERY"
    status_code = 400


# ============================================================
# STORAGE ERRORS
# ============================================================


class StorageError(PipelineBaseError):
    """Base class for storage-related errors."""

    code = "STORAGE_ERROR"


class DatabaseConnectionError(StorageError):
    """Failed to connect to database."""

    code = "DATABASE_CONNECTION_ERROR"
    status_code = 503


class FileStorageError(StorageError):
    """Error with file storage operations."""

    code = "FILE_STORAGE_ERROR"


# ============================================================
# VALIDATION ERRORS
# ============================================================


class ValidationError(PipelineBaseError):
    """Base class for validation errors."""

    code = "VALIDATION_ERROR"
    status_code = 422
