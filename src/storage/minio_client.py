"""MinIO 오브젝트 스토리지 클라이언트."""

import io
from pathlib import Path
from typing import Optional

import structlog
from minio import Minio
from minio.error import S3Error

logger = structlog.get_logger()


class MinIOClient:
    """MinIO 클라이언트 - 이미지 업로드/다운로드/URL 생성."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        use_ssl: bool = False,
        public_endpoint: str = "",
    ):
        self.endpoint = endpoint
        self.bucket = bucket
        self.public_endpoint = public_endpoint or endpoint
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=use_ssl,
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            if not self._client.bucket_exists(self.bucket):
                self._client.make_bucket(self.bucket)
                # 버킷 공개 읽기 정책 설정
                policy = f'''{{
                    "Version":"2012-10-17",
                    "Statement":[{{
                        "Effect":"Allow",
                        "Principal":{{"AWS":["*"]}},
                        "Action":["s3:GetObject"],
                        "Resource":["arn:aws:s3:::{self.bucket}/*"]
                    }}]
                }}'''
                self._client.set_bucket_policy(self.bucket, policy)
                logger.info("MinIO 버킷 생성", bucket=self.bucket)
            else:
                logger.info("MinIO 버킷 확인", bucket=self.bucket)
        except S3Error as e:
            logger.error("MinIO 버킷 설정 실패", error=str(e))

    def upload_file(self, object_name: str, file_path: str) -> Optional[str]:
        """로컬 파일을 MinIO에 업로드. 성공 시 object_name 반환."""
        try:
            path = Path(file_path)
            if not path.exists():
                logger.warning("업로드할 파일 없음", path=file_path)
                return None
            ext = path.suffix.lower().lstrip(".")
            content_type = f"image/{ext}" if ext in ("jpg", "jpeg", "png", "gif", "webp") else "application/octet-stream"
            if ext == "jpg":
                content_type = "image/jpeg"
            self._client.fput_object(self.bucket, object_name, file_path, content_type=content_type)
            logger.info("MinIO 업로드 성공", object=object_name)
            return object_name
        except S3Error as e:
            logger.error("MinIO 업로드 실패", object=object_name, error=str(e))
            return None

    def get_public_url(self, object_name: str) -> str:
        """공개 URL 반환 (버킷 공개 정책 필요)."""
        scheme = "https" if self._client._base_url.is_https else "http"
        return f"{scheme}://{self.public_endpoint}/{self.bucket}/{object_name}"

    def get_presigned_url(self, object_name: str, expires_hours: int = 24) -> str:
        """임시 접근 URL 생성."""
        from datetime import timedelta
        try:
            url = self._client.presigned_get_object(
                self.bucket, object_name, expires=timedelta(hours=expires_hours)
            )
            # public_endpoint로 교체 (내부 hostname → 외부 IP)
            if self.public_endpoint and self.endpoint != self.public_endpoint:
                url = url.replace(self.endpoint, self.public_endpoint)
            return url
        except S3Error as e:
            logger.error("MinIO presigned URL 실패", object=object_name, error=str(e))
            return ""


_minio_client: Optional[MinIOClient] = None


def get_minio_client(settings=None) -> Optional[MinIOClient]:
    """싱글톤 MinIO 클라이언트 반환."""
    global _minio_client
    if _minio_client is None:
        if settings is None:
            from src.core.config import get_settings
            settings = get_settings()
        try:
            _minio_client = MinIOClient(
                endpoint=settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                bucket=settings.minio_bucket,
                use_ssl=settings.minio_use_ssl,
                public_endpoint=settings.minio_public_endpoint,
            )
        except Exception as e:
            logger.error("MinIO 초기화 실패", error=str(e))
            return None
    return _minio_client
