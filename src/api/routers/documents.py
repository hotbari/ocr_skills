"""문서 관리 API 라우터."""

import shutil
import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from src.core.config import Settings, get_settings
from src.core.exceptions import DocumentNotFoundError
from src.core.models import (
    Document,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentMetadata,
    DocumentUploadResponse,
)
from src.db.repositories.document_repo import DocumentRepository
from src.db.repositories.image_repo import ImageRepository
from src.db.repositories.section_repo import SectionRepository
from src.db.repositories.table_repo import TableRepository
from src.db.repositories.toc_repo import TOCRepository

logger = structlog.get_logger()
router = APIRouter(prefix="/documents", tags=["documents"])


def get_doc_repo() -> DocumentRepository:
    return DocumentRepository()


def get_section_repo() -> SectionRepository:
    return SectionRepository()


def get_table_repo() -> TableRepository:
    return TableRepository()


def get_image_repo() -> ImageRepository:
    return ImageRepository()


def get_toc_repo() -> TOCRepository:
    return TOCRepository()


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    auto_run: bool = True,
    settings: Settings = Depends(get_settings),
    doc_repo: DocumentRepository = Depends(get_doc_repo),
):
    """PDF 문서 업로드."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PDF 파일만 업로드 가능합니다.",
        )

    # 파일 크기 확인
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_file_size_mb:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"파일 크기 초과: {size_mb:.1f}MB (최대 {settings.max_file_size_mb}MB)",
        )

    document_id = str(uuid.uuid4())
    safe_name = f"{document_id}.pdf"
    doc_dir = settings.upload_dir / document_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    file_path = doc_dir / safe_name

    file_path.write_bytes(content)
    logger.info("파일 저장", document_id=document_id, size_mb=f"{size_mb:.2f}")

    # PyMuPDF로 페이지 수 빠른 확인
    page_count = 0
    try:
        import fitz
        doc = fitz.open(str(file_path))
        page_count = len(doc)
        doc.close()
    except Exception:
        pass

    document = Document(
        id=document_id,
        filename=safe_name,
        original_filename=file.filename,
        file_path=str(file_path),
        metadata=DocumentMetadata(
            page_count=page_count,
            file_size_bytes=len(content),
        ),
    )

    await doc_repo.insert(document)

    # 자동 파이프라인 실행
    pipeline_started = False
    if auto_run:
        try:
            from fastapi import BackgroundTasks
            from src.pipeline.orchestrator import PipelineOrchestrator
            import asyncio

            async def _run_pipeline():
                orchestrator = PipelineOrchestrator(settings)
                await orchestrator.run(document)

            asyncio.create_task(_run_pipeline())
            pipeline_started = True
        except Exception as e:
            logger.warning("파이프라인 자동 시작 실패", error=str(e))

    return DocumentUploadResponse(
        document_id=document_id,
        filename=file.filename,
        status=document.status,
        message="업로드 완료. 파이프라인이 자동으로 시작됩니다." if pipeline_started else "업로드 완료. /pipeline/{document_id}/run 으로 처리를 시작하세요.",
        page_count=page_count,
        file_size_bytes=len(content),
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    page: int = 1,
    page_size: int = 20,
    doc_repo: DocumentRepository = Depends(get_doc_repo),
):
    """문서 목록 조회."""
    docs, total = await doc_repo.list_all(page=page, page_size=page_size)
    return DocumentListResponse(
        documents=docs,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: str,
    doc_repo: DocumentRepository = Depends(get_doc_repo),
    toc_repo: TOCRepository = Depends(get_toc_repo),
    section_repo: SectionRepository = Depends(get_section_repo),
    table_repo: TableRepository = Depends(get_table_repo),
    image_repo: ImageRepository = Depends(get_image_repo),
):
    """문서 상세 조회 (TOC/섹션/테이블/이미지 포함)."""
    document = await doc_repo.get(document_id)
    if not document:
        raise DocumentNotFoundError(document_id)

    toc = await toc_repo.get_structure(document_id)
    sections = await section_repo.list_by_document(document_id)
    tables = await table_repo.list_by_document(document_id)
    images = await image_repo.list_by_document(document_id)

    return DocumentDetailResponse(
        document=document,
        toc=toc,
        sections=sections,
        tables=tables,
        images=images,
        total_sections=len(sections),
        total_tables=len(tables),
        total_images=len(images),
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    settings: Settings = Depends(get_settings),
    doc_repo: DocumentRepository = Depends(get_doc_repo),
    toc_repo: TOCRepository = Depends(get_toc_repo),
    section_repo: SectionRepository = Depends(get_section_repo),
    table_repo: TableRepository = Depends(get_table_repo),
    image_repo: ImageRepository = Depends(get_image_repo),
):
    """문서 및 관련 데이터 삭제."""
    document = await doc_repo.get(document_id)
    if not document:
        raise DocumentNotFoundError(document_id)

    # DB 데이터 삭제
    await toc_repo.delete_by_document(document_id)
    await section_repo.delete_by_document(document_id)
    await table_repo.delete_by_document(document_id)
    await image_repo.delete_by_document(document_id)
    await doc_repo.delete(document_id)

    # 파일 삭제
    doc_dir = settings.upload_dir / document_id
    if doc_dir.exists():
        shutil.rmtree(doc_dir)

    logger.info("문서 삭제 완료", document_id=document_id)
