# API Reference

REST API endpoints for the OCR pipeline system.

## Table of Contents
- [Pipeline Endpoints](#pipeline-endpoints)
- [Document Endpoints](#document-endpoints)
- [Search Endpoints](#search-endpoints)

---

## Pipeline Endpoints

Base path: `/api/v1/pipeline`

### POST /run
Start or resume pipeline processing.

**Request Body**:
```json
{
    "document_id": "uuid-string",
    "skip_vision": false,
    "force_restart": false
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| document_id | string | Yes | Document UUID |
| skip_vision | boolean | No | Skip Stage 6 vision processing (default: false) |
| force_restart | boolean | No | Ignore saved state, restart from beginning (default: false) |

**Response** (200):
```json
{
    "document_id": "uuid-string",
    "status": "started",
    "message": "Pipeline started. Check /status for progress."
}
```

**Errors**:
- 404: Document not found
- 400: Pipeline already running (use force_restart=true)

---

### GET /status/{document_id}
Get current pipeline status with detailed progress.

**Response** (200):
```json
{
    "document_id": "uuid-string",
    "overall_status": "processing",
    "current_stage": "stage_2_headings",
    "last_completed_stage": "stage_1_segmentation",
    "stages": [
        {
            "stage": "stage_0_extraction",
            "status": "completed",
            "duration_seconds": 2.5,
            "error": null,
            "summary": {"pages": 10, "tables": 3}
        },
        {
            "stage": "stage_1_segmentation",
            "status": "completed",
            "duration_seconds": 5.2,
            "error": null,
            "summary": {"segments": 45}
        },
        {
            "stage": "stage_2_headings",
            "status": "running",
            "duration_seconds": null,
            "error": null,
            "summary": null
        }
    ],
    "progress_percent": 22.2,
    "error_message": null,
    "started_at": "2024-01-15T10:30:00Z",
    "completed_at": null,
    "total_duration_seconds": null
}
```

**Errors**:
- 404: Document not found

---

### GET /stage/{document_id}/{stage}
Get detailed result of a specific stage.

**Path Parameters**:
- `document_id`: Document UUID
- `stage`: Stage name (e.g., `stage_0_extraction`)

**Query Parameters**:
- `include_output`: boolean (default: false) - Include full stage output

**Response** (200):
```json
{
    "document_id": "uuid-string",
    "stage": "stage_0_extraction",
    "status": "completed",
    "started_at": "2024-01-15T10:30:00Z",
    "completed_at": "2024-01-15T10:30:02Z",
    "duration_seconds": 2.5,
    "error_message": null,
    "output_summary": {
        "pages": 10,
        "tables": 3,
        "images": 5
    },
    "output": { ... }  // Only if include_output=true
}
```

**Errors**:
- 404: Document or pipeline state not found
- 400: Invalid stage name

---

### POST /cancel/{document_id}
Cancel running pipeline.

**Response** (200):
```json
{
    "document_id": "uuid-string",
    "cancelled": true,
    "message": "Pipeline cancelled"
}
```

If not running:
```json
{
    "document_id": "uuid-string",
    "cancelled": false,
    "message": "Pipeline is not running"
}
```

---

### POST /retry/{document_id}
Retry pipeline from last failed stage.

**Response** (200):
```json
{
    "document_id": "uuid-string",
    "started": true,
    "message": "Pipeline retry started"
}
```

If not failed:
```json
{
    "document_id": "uuid-string",
    "started": false,
    "message": "Pipeline has not failed"
}
```

---

## Document Endpoints

Base path: `/api/v1/documents`

### POST /upload
Upload a PDF document.

**Request**: `multipart/form-data`
- `file`: PDF file

**Response** (200):
```json
{
    "document_id": "uuid-string",
    "filename": "stored_filename.pdf",
    "status": "uploaded",
    "message": "Document uploaded successfully",
    "page_count": 10,
    "file_size_bytes": 1024000
}
```

---

### GET /
List all documents.

**Query Parameters**:
- `page`: int (default: 1)
- `page_size`: int (default: 20, max: 100)
- `status`: string (filter by status)

**Response** (200):
```json
{
    "documents": [...],
    "total": 50,
    "page": 1,
    "page_size": 20,
    "total_pages": 3
}
```

---

### GET /{document_id}
Get document details.

**Response** (200):
```json
{
    "id": "uuid-string",
    "filename": "document.pdf",
    "original_filename": "My Document.pdf",
    "status": "completed",
    "metadata": {
        "title": "Document Title",
        "page_count": 10,
        "detected_language": "en"
    },
    "current_stage": null,
    "error_message": null
}
```

---

### DELETE /{document_id}
Delete document and all associated data.

**Response** (200):
```json
{
    "deleted": true,
    "document_id": "uuid-string"
}
```

---

## Search Endpoints

Base path: `/api/v1/search`

### POST /
Search across processed documents.

**Request Body**:
```json
{
    "query": "What is machine learning?",
    "document_ids": ["uuid-1", "uuid-2"],
    "top_k": 10,
    "min_score": 0.5,
    "include_entities": true
}
```

**Response** (200):
```json
{
    "query": "What is machine learning?",
    "results": [
        {
            "retrieval_chunk": {
                "id": "chunk-uuid",
                "content": "Machine learning is...",
                "key_concepts": ["machine learning", "AI"]
            },
            "generation_chunk": {
                "id": "gen-chunk-uuid",
                "content": "Full detailed content...",
                "summary": "Overview of ML concepts",
                "context_path": "Chapter 1 > Introduction > ML Basics"
            },
            "toc_node": {
                "title": "ML Basics",
                "level": 3
            },
            "entities": [...],
            "score": 0.92,
            "context_path": "Chapter 1 > Introduction > ML Basics"
        }
    ],
    "total_found": 15,
    "processing_time_ms": 125.5
}
```

---

## Error Response Format

All endpoints return errors in this format:

```json
{
    "error": "Error message",
    "detail": "Additional details or null",
    "code": "ERROR_CODE",
    "timestamp": "2024-01-15T10:30:00Z"
}
```

Common error codes:
- `DOCUMENT_NOT_FOUND`
- `PIPELINE_STATE_NOT_FOUND`
- `INVALID_STAGE`
- `PIPELINE_ALREADY_RUNNING`
- `FILE_NOT_FOUND`
- `VALIDATION_ERROR`
