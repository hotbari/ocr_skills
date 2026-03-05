"""Section 컬렉션 레포지터리."""

from typing import Optional

import structlog

from src.core.models import Section
from src.db.mongodb import Collections, MongoDB

logger = structlog.get_logger()


class SectionRepository:
    @property
    def collection(self):
        return MongoDB.get_collection(Collections.SECTIONS)

    async def upsert(self, section: Section) -> None:
        data = section.model_dump(mode="json")
        await self.collection.replace_one(
            {"_id": section.id}, {"_id": section.id, **data}, upsert=True
        )

    async def get(self, section_id: str) -> Optional[Section]:
        doc = await self.collection.find_one({"_id": section_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return Section(**doc)

    async def list_by_document(self, document_id: str) -> list[Section]:
        cursor = self.collection.find({"document_id": document_id}).sort("sequence_number", 1)
        results = []
        async for d in cursor:
            d.pop("_id", None)
            results.append(Section(**d))
        return results

    async def update_tags(
        self, section_id: str, tags: list[str], summary: Optional[str]
    ) -> None:
        update: dict = {"tags": tags}
        if summary:
            update["summary"] = summary
        await self.collection.update_one({"_id": section_id}, {"$set": update})

    async def delete_by_document(self, document_id: str) -> int:
        result = await self.collection.delete_many({"document_id": document_id})
        return result.deleted_count
