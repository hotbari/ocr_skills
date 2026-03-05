"""Document 컬렉션 레포지터리."""

from datetime import datetime
from typing import Optional

import structlog

from src.core.models import Document, DocumentMetadata, DocumentStatus, Language, PipelineStage
from src.db.mongodb import Collections, MongoDB

logger = structlog.get_logger()


class DocumentRepository:
    @property
    def collection(self):
        return MongoDB.get_collection(Collections.DOCUMENTS)

    async def insert(self, document: Document) -> str:
        data = document.model_dump(mode="json")
        await self.collection.insert_one({"_id": document.id, **data})
        return document.id

    async def get(self, document_id: str) -> Optional[Document]:
        doc = await self.collection.find_one({"_id": document_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return Document(**doc)

    async def list_all(self, page: int = 1, page_size: int = 20) -> tuple[list[Document], int]:
        skip = (page - 1) * page_size
        total = await self.collection.count_documents({})
        cursor = self.collection.find({}).sort("upload_timestamp", -1).skip(skip).limit(page_size)
        docs = []
        async for d in cursor:
            d.pop("_id", None)
            docs.append(Document(**d))
        return docs, total

    async def update_status(
        self,
        document_id: str,
        status: DocumentStatus,
        current_stage: Optional[PipelineStage] = None,
        error_message: Optional[str] = None,
    ) -> None:
        update: dict = {"status": status.value if hasattr(status, "value") else status}
        if current_stage:
            update["current_stage"] = current_stage.value if hasattr(current_stage, "value") else current_stage
        if error_message:
            update["error_message"] = error_message
        if status == DocumentStatus.PROCESSING:
            update["processing_started_at"] = datetime.utcnow().isoformat()
        if status in (DocumentStatus.COMPLETED, DocumentStatus.FAILED):
            update["processing_completed_at"] = datetime.utcnow().isoformat()

        await self.collection.update_one(
            {"_id": document_id}, {"$set": update}
        )

    async def update_metadata(self, document_id: str, meta: dict) -> None:
        set_fields = {f"metadata.{k}": v for k, v in meta.items() if v is not None}
        if set_fields:
            await self.collection.update_one(
                {"_id": document_id}, {"$set": set_fields}
            )

    async def delete(self, document_id: str) -> bool:
        result = await self.collection.delete_one({"_id": document_id})
        return result.deleted_count > 0
