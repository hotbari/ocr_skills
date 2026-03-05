"""Core Pydantic models for the OCR pipeline."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def generate_id() -> str:
    return str(uuid.uuid4())


# ============================================================
# ENUMS
# ============================================================


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineStage(str, Enum):
    STAGE_0_EXTRACT = "stage_0_extract"
    STAGE_1_LAYOUT = "stage_1_layout"
    STAGE_2_STRUCTURE = "stage_2_structure"
    STAGE_3_VISION = "stage_3_vision"
    STAGE_4_TAGS = "stage_4_tags"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Language(str, Enum):
    KOREAN = "ko"
    ENGLISH = "en"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class BlockType(str, Enum):
    """PP-Structure 레이아웃 블록 타입."""
    TITLE = "title"
    TEXT = "text"
    TABLE = "table"
    FIGURE = "figure"
    FIGURE_CAPTION = "figure_caption"
    TABLE_CAPTION = "table_caption"
    HEADER = "header"
    FOOTER = "footer"
    REFERENCE = "reference"
    EQUATION = "equation"


class EntityType(str, Enum):
    TABLE = "table"
    IMAGE = "image"


# ============================================================
# DOCUMENT
# ============================================================


class DocumentMetadata(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    page_count: int = 0
    file_size_bytes: int = 0
    detected_language: Language = Language.UNKNOWN
    is_scanned: bool = False


class Document(BaseModel):
    id: str = Field(default_factory=generate_id)
    filename: str
    original_filename: str
    file_path: str
    upload_timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: DocumentStatus = DocumentStatus.UPLOADED
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    current_stage: Optional[PipelineStage] = None
    error_message: Optional[str] = None
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None

    class Config:
        use_enum_values = True


# ============================================================
# LAYOUT BLOCK (PP-Structure 출력)
# ============================================================


class BoundingBox(BaseModel):
    """바운딩 박스 (픽셀 좌표)."""
    x0: float
    y0: float
    x1: float
    y1: float


class LayoutBlock(BaseModel):
    """PP-Structure가 감지한 레이아웃 블록 하나."""
    id: str = Field(default_factory=generate_id)
    document_id: str
    page_number: int
    block_type: BlockType
    bbox: BoundingBox
    text: Optional[str] = None          # 텍스트 블록이면 내용
    confidence: float = 1.0
    sequence_in_page: int = 0

    class Config:
        use_enum_values = True


# ============================================================
# TOC (목차 구조)
# ============================================================


class TOCNode(BaseModel):
    """목차 노드 - PP-Structure TITLE 블록으로 자동 생성."""
    id: str = Field(default_factory=generate_id)
    document_id: str
    level: int = 1                      # 1=대제목, 2=중제목, 3=소제목
    title: str                          # 제목 텍스트
    page_start: int = 1
    page_end: int = 1
    sequence_number: int = 0           # 문서 내 순서
    parent_id: Optional[str] = None
    children_ids: list[str] = Field(default_factory=list)
    section_id: Optional[str] = None   # 연결된 Section ID
    entity_ids: list[str] = Field(default_factory=list)  # 연결된 테이블/이미지

    class Config:
        use_enum_values = True


class TOCStructure(BaseModel):
    """문서 전체 목차."""
    document_id: str
    nodes: list[TOCNode] = Field(default_factory=list)
    total_l1: int = 0
    total_l2: int = 0
    total_l3: int = 0


# ============================================================
# SECTION (구조화된 섹션)
# ============================================================


class Section(BaseModel):
    """문서의 섹션 (헤딩 + 본문)."""
    id: str = Field(default_factory=generate_id)
    document_id: str
    toc_node_id: Optional[str] = None  # 연결된 TOC 노드
    heading: Optional[str] = None       # 섹션 제목 (없으면 None)
    heading_level: int = 1              # 1=대제목, 2=중제목, 3=소제목
    content: str = ""                   # 섹션 본문
    page_start: int = 1
    page_end: int = 1
    sequence_number: int = 0
    parent_id: Optional[str] = None
    children_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)  # 연결된 테이블/이미지
    tags: list[str] = Field(default_factory=list)        # Stage 4 생성
    summary: Optional[str] = None                        # Stage 4 생성
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True


# ============================================================
# TABLE ENTITY
# ============================================================


class TableCell(BaseModel):
    row: int
    col: int
    content: str
    rowspan: int = 1
    colspan: int = 1
    is_header: bool = False


class TableStructure(BaseModel):
    rows: int
    cols: int
    headers: list[str] = Field(default_factory=list)
    cells: list[TableCell] = Field(default_factory=list)


class TableEntity(BaseModel):
    """PDF에서 추출된 테이블."""
    id: str = Field(default_factory=generate_id)
    document_id: str
    section_id: Optional[str] = None
    page_number: int
    sequence_in_page: int = 0
    bbox: Optional[BoundingBox] = None
    structure: Optional[TableStructure] = None
    markdown: str = ""                  # 마크다운 형식
    caption: Optional[str] = None      # 테이블 캡션
    surrounding_context: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True


# ============================================================
# IMAGE ENTITY
# ============================================================


class ImageEntity(BaseModel):
    """PDF에서 추출된 이미지."""
    id: str = Field(default_factory=generate_id)
    document_id: str
    section_id: Optional[str] = None
    page_number: int
    sequence_in_page: int = 0
    bbox: Optional[BoundingBox] = None
    image_path: Optional[str] = None    # 로컬 파일 경로
    caption: Optional[str] = None       # 이미지 캡션
    surrounding_context: Optional[str] = None
    vision_description: Optional[str] = None  # Stage 3 gpt-4o 캡셔닝
    vision_processed: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True


# ============================================================
# PIPELINE STATE
# ============================================================


class StageResult(BaseModel):
    stage: PipelineStage
    status: StageStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    output_summary: Optional[dict[str, Any]] = None

    class Config:
        use_enum_values = True


class PipelineState(BaseModel):
    id: str = Field(default_factory=generate_id)
    document_id: str
    stages: dict[str, StageResult] = Field(default_factory=dict)
    current_stage: Optional[PipelineStage] = None
    last_completed_stage: Optional[PipelineStage] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    total_duration_seconds: Optional[float] = None

    class Config:
        use_enum_values = True


# ============================================================
# API MODELS
# ============================================================


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    status: DocumentStatus
    message: str
    page_count: int
    file_size_bytes: int


class DocumentListResponse(BaseModel):
    documents: list[Document]
    total: int
    page: int
    page_size: int


class PipelineStatusResponse(BaseModel):
    document_id: str
    overall_status: DocumentStatus
    current_stage: Optional[PipelineStage]
    stages: list[StageResult]
    progress_percent: float
    error_message: Optional[str] = None


class DocumentDetailResponse(BaseModel):
    """문서 처리 결과 상세."""
    document: Document
    toc: TOCStructure
    sections: list[Section]
    tables: list[TableEntity]
    images: list[ImageEntity]
    total_sections: int
    total_tables: int
    total_images: int
