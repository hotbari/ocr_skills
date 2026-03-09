"""Application configuration."""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings loaded from environment variables."""

    # OpenAI
    openai_api_key: str
    vision_model: str = "gpt-4o"
    llm_model: str = "gpt-4o-mini"

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "ocr_pipeline"

    # Storage
    upload_dir: Path = Path("./uploads")
    pipeline_state_dir: Path = Path("./pipeline_state")

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = False

    # File limits
    max_file_size_mb: int = 100
    max_pages: int = 500

    # Pipeline options
    enable_vision_captioning: bool = True   # Stage 3: gpt-4o 이미지 캡셔닝
    enable_tag_generation: bool = True      # Stage 4: LLM 태그/요약
    use_paddle_ocr: bool = True             # 스캔 PDF PaddleOCR 사용
    use_pp_structure: bool = True           # PP-Structure 레이아웃 분석 사용

    # PP-Structure 설정
    pp_structure_lang: str = "korean"              # OCR 언어 (korean / ch / en)
    pp_structure_use_angle_cls: bool = False       # 기울어진 텍스트 감지 (cls 모델 필요)
    pp_structure_use_gpu: bool = False             # GPU 사용 여부

    # EasyOCR 설정 (스캔 PDF 한국어 OCR)
    easyocr_lang: list[str] = ["ko", "en"]         # 한국어 + 영어

    # MinIO 설정
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "ocr-images"
    minio_use_ssl: bool = False
    minio_public_endpoint: str = ""   # 외부 접근용 (비어있으면 minio_endpoint 사용)

    # 스캔 판별 설정
    scan_min_chars_per_page: int = 50              # 페이지당 최소 글자수 (미만이면 스캔)
    scan_image_ratio_threshold: float = 0.8        # 이미지 면적 비율 임계값

    # 블록 후처리 설정
    block_merge_enabled: bool = True               # 인접 텍스트 블록 병합 여부
    block_merge_y_gap: float = 10.0                # 병합 허용 Y 간격 (픽셀)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def ensure_directories(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.pipeline_state_dir.mkdir(parents=True, exist_ok=True)


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_directories()
    return _settings
