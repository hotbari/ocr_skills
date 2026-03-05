"""Custom exceptions."""

from fastapi import status


class OCRPipelineError(Exception):
    """Base pipeline error."""

    def __init__(
        self,
        message: str,
        code: str = "PIPELINE_ERROR",
        detail: str | None = None,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    ):
        self.message = message
        self.code = code
        self.detail = detail
        self.status_code = status_code
        super().__init__(message)


class DocumentNotFoundError(OCRPipelineError):
    def __init__(self, document_id: str):
        super().__init__(
            message=f"Document not found: {document_id}",
            code="DOCUMENT_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ExtractionError(OCRPipelineError):
    def __init__(self, message: str, detail: str | None = None):
        super().__init__(message=message, code="EXTRACTION_ERROR", detail=detail)


class LayoutAnalysisError(OCRPipelineError):
    def __init__(self, message: str, detail: str | None = None):
        super().__init__(message=message, code="LAYOUT_ANALYSIS_ERROR", detail=detail)


class DatabaseConnectionError(OCRPipelineError):
    def __init__(self, message: str):
        super().__init__(message=message, code="DB_CONNECTION_ERROR")
