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
