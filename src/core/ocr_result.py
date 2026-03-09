"""PRD 정의 OCR 결과 데이터 모델."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from src.core.models import generate_id


class OCRResultSection(BaseModel):
    """페이지 내 섹션."""
    section_id: str
    title: Optional[str] = None
    content: str = ""
    page_number: int
    keyword: Optional[str] = None   # 쉼표 구분 키워드 (Stage 4 tags)
    sequence_id: int = 0            # 페이지 내 순서


class OCRResultImage(BaseModel):
    """페이지 내 이미지."""
    name: str
    description: Optional[str] = None   # Stage 3 vision_description
    ext: str = "png"
    image_url: str = ""                 # 로컬 경로 또는 S3 URL
    tag: list[str] = Field(default_factory=list)
    type: str = "image"
    sequence_id: int = 0


class OCRResultTable(BaseModel):
    """페이지 내 테이블."""
    name: str
    table_md: str = ""
    sequence_id: int = 0


class OCRResultPage(BaseModel):
    """페이지 단위 OCR 결과."""
    page_num: int
    sections: list[OCRResultSection] = Field(default_factory=list)
    images: list[OCRResultImage] = Field(default_factory=list)
    table: list[OCRResultTable] = Field(default_factory=list)


class OCRResult(BaseModel):
    """PRD 형식 OCR 최종 결과."""
    ocr_result_id: str = Field(default_factory=generate_id)
    ref_document_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    page: list[OCRResultPage] = Field(default_factory=list)

    class Config:
        use_enum_values = True
