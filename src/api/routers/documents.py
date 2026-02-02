"""Documents API router."""

import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from src.api.dependencies import (get_chunk_repo, get_document_repo,
                                  get_entity_repo, get_toc_repo)
from src.core.config import get_settings
from src.core.exceptions import DocumentNotFoundError, InvalidFileTypeError
from src.core.models import (Document, DocumentListResponse, DocumentMetadata,
                             DocumentStatus, DocumentUploadResponse,
                             generate_id)
from src.db.repositories.chunk_repo import ChunkRepository
from src.db.repositories.document_repo import DocumentRepository
from src.db.repositories.entity_repo import EntityRepository
from src.db.repositories.toc_repo import TOCRepository

router = APIRouter(prefix="/api/v1/documents", tags=["Documents"])


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    document_repo: DocumentRepository = Depends(get_document_repo),
):
    """Upload a PDF document for processing.

    Returns document ID for pipeline execution.
    """
    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    settings = get_settings()

    # Generate document ID
    document_id = generate_id()

    # Create upload directory
    doc_dir = settings.upload_dir / document_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    # Save file
    file_path = doc_dir / file.filename
    try:
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        shutil.rmtree(doc_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    # Get file info
    file_size = file_path.stat().st_size

    # Get page count (quick check)
    page_count = 0
    try:
        import fitz

        doc = fitz.open(str(file_path))
        page_count = len(doc)
        doc.close()
    except Exception:
        pass

    # Create document record
    document = Document(
        id=document_id,
        filename=file.filename,
        original_filename=file.filename,
        file_path=str(file_path),
        status=DocumentStatus.UPLOADED,
        metadata=DocumentMetadata(
            page_count=page_count,
            file_size_bytes=file_size,
        ),
    )

    await document_repo.create(document)

    return DocumentUploadResponse(
        document_id=document_id,
        filename=file.filename,
        status=DocumentStatus.UPLOADED,
        message="Document uploaded successfully. Run pipeline to process.",
        page_count=page_count,
        file_size_bytes=file_size,
    )


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    include_raw_text: bool = Query(False),
    document_repo: DocumentRepository = Depends(get_document_repo),
    toc_repo: TOCRepository = Depends(get_toc_repo),
    chunk_repo: ChunkRepository = Depends(get_chunk_repo),
    entity_repo: EntityRepository = Depends(get_entity_repo),
):
    """Get document details including statistics."""
    document = await document_repo.get(document_id)

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get stats
    chunk_stats = await chunk_repo.count_by_document(document_id)
    entity_stats = await entity_repo.count_by_document(document_id)
    toc = await toc_repo.get_tree(document_id)

    response = {
        "document": document.model_dump(),
        "chunk_stats": chunk_stats,
        "entity_stats": entity_stats,
        "toc_summary": {
            "total_nodes": len(toc.all_nodes),
            "l1_count": toc.total_l1,
            "l2_count": toc.total_l2,
            "l3_count": toc.total_l3,
        },
    }

    # Optionally exclude raw text to reduce response size
    if not include_raw_text:
        response["document"]["raw_text"] = None
        response["document"]["raw_text_by_page"] = []

    return response


@router.get("")
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    document_repo: DocumentRepository = Depends(get_document_repo),
):
    """List all documents with pagination."""
    skip = (page - 1) * page_size

    # Parse status filter
    status_filter = None
    if status:
        try:
            status_filter = DocumentStatus(status)
        except ValueError:
            pass

    documents, total = await document_repo.list(
        skip=skip,
        limit=page_size,
        status=status_filter,
    )

    total_pages = (total + page_size - 1) // page_size

    return DocumentListResponse(
        documents=documents,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    document_repo: DocumentRepository = Depends(get_document_repo),
    toc_repo: TOCRepository = Depends(get_toc_repo),
    chunk_repo: ChunkRepository = Depends(get_chunk_repo),
    entity_repo: EntityRepository = Depends(get_entity_repo),
):
    """Delete document and all associated data."""
    # Check exists
    document = await document_repo.get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete associated data
    chunks_deleted = await chunk_repo.delete_by_document(document_id)
    entities_deleted = await entity_repo.delete_by_document(document_id)
    toc_deleted = await toc_repo.delete_by_document(document_id)

    # Delete document
    await document_repo.delete(document_id)

    # Delete files
    settings = get_settings()
    doc_dir = settings.upload_dir / document_id
    if doc_dir.exists():
        shutil.rmtree(doc_dir, ignore_errors=True)

    # Delete pipeline state
    state_dir = settings.pipeline_state_dir / document_id
    if state_dir.exists():
        shutil.rmtree(state_dir, ignore_errors=True)

    return {
        "document_id": document_id,
        "deleted": True,
        "chunks_deleted": (
            sum(chunks_deleted) if isinstance(chunks_deleted, tuple) else chunks_deleted
        ),
        "entities_deleted": entities_deleted,
        "toc_nodes_deleted": toc_deleted,
    }


@router.get("/{document_id}/toc")
async def get_document_toc(
    document_id: str,
    document_repo: DocumentRepository = Depends(get_document_repo),
    toc_repo: TOCRepository = Depends(get_toc_repo),
):
    """Get complete TOC structure for document."""
    # Check exists
    exists = await document_repo.exists(document_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Document not found")

    toc = await toc_repo.get_tree(document_id)

    return {
        "document_id": document_id,
        "root_nodes": toc.root_nodes,
        "nodes": [node.model_dump() for node in toc.all_nodes],
        "summary": {
            "total": len(toc.all_nodes),
            "l1": toc.total_l1,
            "l2": toc.total_l2,
            "l3": toc.total_l3,
        },
    }


@router.get("/{document_id}/raw-text")
async def get_raw_text(
    document_id: str,
    page: Optional[int] = None,
    document_repo: DocumentRepository = Depends(get_document_repo),
):
    """Get raw extracted text."""
    document = await document_repo.get(document_id)

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if page is not None:
        # Return specific page
        if 1 <= page <= len(document.raw_text_by_page):
            return {
                "document_id": document_id,
                "page": page,
                "total_pages": len(document.raw_text_by_page),
                "content": document.raw_text_by_page[page - 1],
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid page number. Max: {len(document.raw_text_by_page)}",
            )

    # Return all text
    return {
        "document_id": document_id,
        "total_pages": len(document.raw_text_by_page),
        "total_characters": len(document.raw_text or ""),
        "content": document.raw_text,
    }
