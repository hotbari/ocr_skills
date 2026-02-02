"""MongoDB connection and database management."""

from typing import Optional

import structlog
from motor.motor_asyncio import (AsyncIOMotorClient, AsyncIOMotorCollection,
                                 AsyncIOMotorDatabase)

from src.core.config import Settings, get_settings
from src.core.exceptions import DatabaseConnectionError

logger = structlog.get_logger()


class Collections:
    """Collection name constants."""

    DOCUMENTS = "documents"
    TOC_NODES = "toc_nodes"
    RETRIEVAL_CHUNKS = "retrieval_chunks"
    GENERATION_CHUNKS = "generation_chunks"
    ENTITIES = "entities"
    PIPELINE_STATES = "pipeline_states"


class MongoDB:
    """MongoDB connection manager using Motor async driver."""

    client: Optional[AsyncIOMotorClient] = None
    database: Optional[AsyncIOMotorDatabase] = None
    _settings: Optional[Settings] = None

    @classmethod
    async def connect(cls, settings: Optional[Settings] = None) -> None:
        """Connect to MongoDB.

        Args:
            settings: Application settings. If None, will use get_settings().
        """
        if cls.client is not None:
            logger.warning("MongoDB already connected")
            return

        cls._settings = settings or get_settings()

        try:
            logger.info(
                "Connecting to MongoDB", uri=cls._settings.mongodb_uri[:30] + "..."
            )
            cls.client = AsyncIOMotorClient(cls._settings.mongodb_uri)
            cls.database = cls.client[cls._settings.mongodb_database]

            # Verify connection
            await cls.client.admin.command("ping")
            logger.info(
                "MongoDB connected successfully",
                database=cls._settings.mongodb_database,
            )

            # Create indexes
            await cls._create_indexes()

        except Exception as e:
            logger.error("Failed to connect to MongoDB", error=str(e))
            cls.client = None
            cls.database = None
            raise DatabaseConnectionError(f"Failed to connect to MongoDB: {e}")

    @classmethod
    async def disconnect(cls) -> None:
        """Disconnect from MongoDB."""
        if cls.client is not None:
            logger.info("Disconnecting from MongoDB")
            cls.client.close()
            cls.client = None
            cls.database = None
            logger.info("MongoDB disconnected")

    @classmethod
    def get_database(cls) -> AsyncIOMotorDatabase:
        """Get the database instance.

        Returns:
            AsyncIOMotorDatabase instance

        Raises:
            DatabaseConnectionError: If not connected
        """
        if cls.database is None:
            raise DatabaseConnectionError(
                "MongoDB not connected. Call connect() first."
            )
        return cls.database

    @classmethod
    def get_collection(cls, name: str) -> AsyncIOMotorCollection:
        """Get a collection by name.

        Args:
            name: Collection name

        Returns:
            AsyncIOMotorCollection instance
        """
        return cls.get_database()[name]

    @classmethod
    async def _create_indexes(cls) -> None:
        """Create necessary indexes for all collections."""
        db = cls.get_database()

        # Documents collection
        await db[Collections.DOCUMENTS].create_index("status")
        await db[Collections.DOCUMENTS].create_index([("upload_timestamp", -1)])
        await db[Collections.DOCUMENTS].create_index([("filename", "text")])

        # TOC nodes collection
        await db[Collections.TOC_NODES].create_index(
            [("document_id", 1), ("sequence_number", 1)]
        )
        await db[Collections.TOC_NODES].create_index([("document_id", 1), ("level", 1)])
        await db[Collections.TOC_NODES].create_index("parent_id")

        # Retrieval chunks collection
        await db[Collections.RETRIEVAL_CHUNKS].create_index(
            [("document_id", 1), ("sequence_in_document", 1)]
        )
        await db[Collections.RETRIEVAL_CHUNKS].create_index("toc_node_id")
        await db[Collections.RETRIEVAL_CHUNKS].create_index("generation_chunk_id")

        # Generation chunks collection
        await db[Collections.GENERATION_CHUNKS].create_index(
            [("document_id", 1), ("sequence_in_document", 1)]
        )
        await db[Collections.GENERATION_CHUNKS].create_index("toc_node_id")

        # Entities collection
        await db[Collections.ENTITIES].create_index(
            [("document_id", 1), ("entity_type", 1)]
        )
        await db[Collections.ENTITIES].create_index("toc_node_id")
        await db[Collections.ENTITIES].create_index("generation_chunk_id")

        # Pipeline states collection
        await db[Collections.PIPELINE_STATES].create_index("document_id", unique=True)

        logger.info("MongoDB indexes created")

    @classmethod
    async def drop_database(cls) -> None:
        """Drop the entire database. USE WITH CAUTION."""
        if cls._settings is None:
            raise DatabaseConnectionError("Settings not initialized")

        logger.warning("Dropping database", database=cls._settings.mongodb_database)
        await cls.client.drop_database(cls._settings.mongodb_database)

    @classmethod
    async def health_check(cls) -> bool:
        """Check if database connection is healthy.

        Returns:
            True if connected and responsive, False otherwise
        """
        try:
            if cls.client is None:
                return False
            await cls.client.admin.command("ping")
            return True
        except Exception:
            return False
