"""MongoDB 연결 관리."""

from typing import Optional

import structlog
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorCollection,
    AsyncIOMotorDatabase,
)

from src.core.config import Settings, get_settings
from src.core.exceptions import DatabaseConnectionError

logger = structlog.get_logger()


class Collections:
    DOCUMENTS = "documents"
    TOC_NODES = "toc_nodes"
    SECTIONS = "sections"
    TABLES = "tables"
    IMAGES = "images"
    PIPELINE_STATES = "pipeline_states"


class MongoDB:
    client: Optional[AsyncIOMotorClient] = None
    database: Optional[AsyncIOMotorDatabase] = None
    _settings: Optional[Settings] = None

    @classmethod
    async def connect(cls, settings: Optional[Settings] = None) -> None:
        if cls.client is not None:
            return

        cls._settings = settings or get_settings()
        try:
            logger.info("MongoDB 연결 중", uri=cls._settings.mongodb_uri[:30] + "...")
            cls.client = AsyncIOMotorClient(cls._settings.mongodb_uri)
            cls.database = cls.client[cls._settings.mongodb_database]
            await cls.client.admin.command("ping")
            logger.info("MongoDB 연결 성공", database=cls._settings.mongodb_database)
            await cls._create_indexes()
        except Exception as e:
            cls.client = None
            cls.database = None
            raise DatabaseConnectionError(f"MongoDB 연결 실패: {e}")

    @classmethod
    async def disconnect(cls) -> None:
        if cls.client is not None:
            cls.client.close()
            cls.client = None
            cls.database = None
            logger.info("MongoDB 연결 해제")

    @classmethod
    def get_database(cls) -> AsyncIOMotorDatabase:
        if cls.database is None:
            raise DatabaseConnectionError("MongoDB 미연결. connect()를 먼저 호출하세요.")
        return cls.database

    @classmethod
    def get_collection(cls, name: str) -> AsyncIOMotorCollection:
        return cls.get_database()[name]

    @classmethod
    async def _create_indexes(cls) -> None:
        db = cls.get_database()

        # documents
        await db[Collections.DOCUMENTS].create_index("status")
        await db[Collections.DOCUMENTS].create_index([("upload_timestamp", -1)])

        # toc_nodes
        await db[Collections.TOC_NODES].create_index(
            [("document_id", 1), ("sequence_number", 1)]
        )
        await db[Collections.TOC_NODES].create_index([("document_id", 1), ("level", 1)])
        await db[Collections.TOC_NODES].create_index("parent_id")

        # sections
        await db[Collections.SECTIONS].create_index(
            [("document_id", 1), ("sequence_number", 1)]
        )
        await db[Collections.SECTIONS].create_index([("document_id", 1), ("heading_level", 1)])
        await db[Collections.SECTIONS].create_index("parent_id")
        await db[Collections.SECTIONS].create_index([("tags", 1)])

        # tables
        await db[Collections.TABLES].create_index(
            [("document_id", 1), ("page_number", 1), ("sequence_in_page", 1)]
        )
        await db[Collections.TABLES].create_index("section_id")

        # images
        await db[Collections.IMAGES].create_index(
            [("document_id", 1), ("page_number", 1), ("sequence_in_page", 1)]
        )
        await db[Collections.IMAGES].create_index("section_id")
        await db[Collections.IMAGES].create_index("vision_processed")

        # pipeline_states
        await db[Collections.PIPELINE_STATES].create_index("document_id", unique=True)

        logger.info("MongoDB 인덱스 생성 완료")

    @classmethod
    async def health_check(cls) -> bool:
        try:
            if cls.client is None:
                return False
            await cls.client.admin.command("ping")
            return True
        except Exception:
            return False
