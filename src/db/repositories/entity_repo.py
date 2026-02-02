"""Entity repository for tables, images, and diagrams."""

from typing import Optional

import structlog
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.exceptions import StorageError
from src.core.models import Entity, EntityType
from src.db.mongodb import Collections

logger = structlog.get_logger()


class EntityRepository:
    """Repository for entity operations (tables, images, diagrams)."""

    def __init__(self, database: AsyncIOMotorDatabase):
        """Initialize repository.

        Args:
            database: MongoDB database instance
        """
        self.collection = database[Collections.ENTITIES]
        self.logger = logger.bind(component="EntityRepository")

    async def bulk_insert(self, entities: list[Entity]) -> int:
        """Insert multiple entities.

        Args:
            entities: List of entities to insert

        Returns:
            Number of entities inserted

        Raises:
            StorageError: If insertion fails
        """
        if not entities:
            return 0

        try:
            docs = []
            for entity in entities:
                doc = entity.model_dump()
                doc["_id"] = entity.id
                docs.append(doc)

            result = await self.collection.insert_many(docs)

            self.logger.info(
                "Entities inserted",
                count=len(result.inserted_ids),
            )

            return len(result.inserted_ids)

        except Exception as e:
            self.logger.error("Failed to insert entities", error=str(e))
            raise StorageError(f"Failed to insert entities: {e}")

    async def get(self, entity_id: str) -> Optional[Entity]:
        """Get entity by ID.

        Args:
            entity_id: Entity ID

        Returns:
            Entity or None
        """
        doc = await self.collection.find_one({"_id": entity_id})

        if doc:
            doc["id"] = doc.pop("_id")
            return Entity.model_validate(doc)

        return None

    async def get_by_document(
        self,
        document_id: str,
        entity_type: Optional[EntityType] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Entity]:
        """Get entities for a document.

        Args:
            document_id: Document ID
            entity_type: Optional type filter
            skip: Number to skip
            limit: Maximum to return

        Returns:
            List of entities
        """
        query = {"document_id": document_id}

        if entity_type:
            query["entity_type"] = entity_type.value

        cursor = (
            self.collection.find(query)
            .sort([("page_number", 1), ("sequence_in_page", 1)])
            .skip(skip)
            .limit(limit)
        )

        entities = []
        async for doc in cursor:
            doc["id"] = doc.pop("_id")
            entities.append(Entity.model_validate(doc))

        return entities

    async def get_by_toc_node(self, toc_node_id: str) -> list[Entity]:
        """Get entities linked to a TOC node.

        Args:
            toc_node_id: TOC node ID

        Returns:
            List of entities
        """
        cursor = self.collection.find({"toc_node_id": toc_node_id}).sort(
            [("page_number", 1), ("sequence_in_page", 1)]
        )

        entities = []
        async for doc in cursor:
            doc["id"] = doc.pop("_id")
            entities.append(Entity.model_validate(doc))

        return entities

    async def get_by_generation_chunk(self, generation_chunk_id: str) -> list[Entity]:
        """Get entities linked to a generation chunk.

        Args:
            generation_chunk_id: Generation chunk ID

        Returns:
            List of entities
        """
        cursor = self.collection.find({"generation_chunk_id": generation_chunk_id})

        entities = []
        async for doc in cursor:
            doc["id"] = doc.pop("_id")
            entities.append(Entity.model_validate(doc))

        return entities

    async def get_by_page(
        self,
        document_id: str,
        page_number: int,
    ) -> list[Entity]:
        """Get entities on a specific page.

        Args:
            document_id: Document ID
            page_number: Page number

        Returns:
            List of entities
        """
        cursor = self.collection.find(
            {
                "document_id": document_id,
                "page_number": page_number,
            }
        ).sort("sequence_in_page", 1)

        entities = []
        async for doc in cursor:
            doc["id"] = doc.pop("_id")
            entities.append(Entity.model_validate(doc))

        return entities

    async def update(self, entity_id: str, **updates) -> bool:
        """Update entity fields.

        Args:
            entity_id: Entity ID
            **updates: Fields to update

        Returns:
            True if updated
        """
        if not updates:
            return False

        result = await self.collection.update_one(
            {"_id": entity_id},
            {"$set": updates},
        )

        return result.modified_count > 0

    async def update_vision_description(
        self,
        entity_id: str,
        description: str,
    ) -> bool:
        """Update vision description for an entity.

        Args:
            entity_id: Entity ID
            description: Vision-generated description

        Returns:
            True if updated
        """
        return await self.update(
            entity_id,
            vision_description=description,
            vision_processed=True,
        )

    async def link_to_toc(self, entity_id: str, toc_node_id: str) -> bool:
        """Link entity to a TOC node.

        Args:
            entity_id: Entity ID
            toc_node_id: TOC node ID

        Returns:
            True if updated
        """
        return await self.update(entity_id, toc_node_id=toc_node_id)

    async def link_to_generation_chunk(
        self,
        entity_id: str,
        generation_chunk_id: str,
    ) -> bool:
        """Link entity to a generation chunk.

        Args:
            entity_id: Entity ID
            generation_chunk_id: Generation chunk ID

        Returns:
            True if updated
        """
        return await self.update(entity_id, generation_chunk_id=generation_chunk_id)

    async def delete_by_document(self, document_id: str) -> int:
        """Delete all entities for a document.

        Args:
            document_id: Document ID

        Returns:
            Number of deleted entities
        """
        result = await self.collection.delete_many({"document_id": document_id})

        self.logger.info(
            "Entities deleted",
            document_id=document_id,
            count=result.deleted_count,
        )

        return result.deleted_count

    async def count_by_document(self, document_id: str) -> dict[str, int]:
        """Count entities by type for a document.

        Args:
            document_id: Document ID

        Returns:
            Dictionary with counts by entity type
        """
        pipeline = [
            {"$match": {"document_id": document_id}},
            {"$group": {"_id": "$entity_type", "count": {"$sum": 1}}},
        ]

        counts = {}
        async for doc in self.collection.aggregate(pipeline):
            counts[doc["_id"]] = doc["count"]

        return counts

    async def get_unprocessed_for_vision(
        self,
        document_id: str,
        limit: int = 10,
    ) -> list[Entity]:
        """Get entities that haven't been processed by vision.

        Args:
            document_id: Document ID
            limit: Maximum to return

        Returns:
            List of unprocessed entities
        """
        cursor = self.collection.find(
            {
                "document_id": document_id,
                "vision_processed": False,
                "entity_type": {
                    "$in": [EntityType.IMAGE.value, EntityType.DIAGRAM.value]
                },
            }
        ).limit(limit)

        entities = []
        async for doc in cursor:
            doc["id"] = doc.pop("_id")
            entities.append(Entity.model_validate(doc))

        return entities
