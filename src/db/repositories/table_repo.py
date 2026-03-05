"""Table 컬렉션 레포지터리."""

from typing import Optional

import structlog

from src.core.models import TableEntity
from src.db.mongodb import Collections, MongoDB

logger = structlog.get_logger()


class TableRepository:
    @property
    def collection(self):
        return MongoDB.get_collection(Collections.TABLES)

    async def upsert(self, table: TableEntity) -> None:
        data = table.model_dump(mode="json")
        await self.collection.replace_one(
            {"_id": table.id}, {"_id": table.id, **data}, upsert=True
        )

    async def get(self, table_id: str) -> Optional[TableEntity]:
        doc = await self.collection.find_one({"_id": table_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return TableEntity(**doc)

    async def list_by_document(self, document_id: str) -> list[TableEntity]:
        cursor = self.collection.find({"document_id": document_id}).sort(
            [("page_number", 1), ("sequence_in_page", 1)]
        )
        results = []
        async for d in cursor:
            d.pop("_id", None)
            results.append(TableEntity(**d))
        return results

    async def list_by_section(self, section_id: str) -> list[TableEntity]:
        cursor = self.collection.find({"section_id": section_id})
        results = []
        async for d in cursor:
            d.pop("_id", None)
            results.append(TableEntity(**d))
        return results

    async def delete_by_document(self, document_id: str) -> int:
        result = await self.collection.delete_many({"document_id": document_id})
        return result.deleted_count
