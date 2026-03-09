"""Image 컬렉션 레포지터리."""

from typing import Optional

import structlog

from src.core.models import ImageEntity
from src.db.mongodb import Collections, MongoDB

logger = structlog.get_logger()


class ImageRepository:
    @property
    def collection(self):
        return MongoDB.get_collection(Collections.IMAGES)

    async def upsert(self, image: ImageEntity) -> None:
        data = image.model_dump(mode="json")
        await self.collection.replace_one(
            {"_id": image.id}, {"_id": image.id, **data}, upsert=True
        )

    async def get(self, image_id: str) -> Optional[ImageEntity]:
        doc = await self.collection.find_one({"_id": image_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return ImageEntity(**doc)

    async def list_by_document(self, document_id: str) -> list[ImageEntity]:
        cursor = self.collection.find({"document_id": document_id}).sort(
            [("page_number", 1), ("sequence_in_page", 1)]
        )
        results = []
        async for d in cursor:
            d.pop("_id", None)
            results.append(ImageEntity(**d))
        return results

    async def list_unprocessed(self, document_id: str) -> list[ImageEntity]:
        cursor = self.collection.find(
            {"document_id": document_id, "vision_processed": False}
        )
        results = []
        async for d in cursor:
            d.pop("_id", None)
            results.append(ImageEntity(**d))
        return results

    async def update_vision_description(self, image_id: str, description: str) -> None:
        await self.collection.update_one(
            {"_id": image_id},
            {"$set": {"vision_description": description, "vision_processed": True}},
        )

    async def update_image_path(self, image_id: str, image_path: str) -> None:
        col = MongoDB.get_collection(Collections.IMAGES)
        await col.update_one({"_id": image_id}, {"$set": {"image_path": image_path}})

    async def delete_by_document(self, document_id: str) -> int:
        result = await self.collection.delete_many({"document_id": document_id})
        return result.deleted_count
