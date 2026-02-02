"""Document repository for CRUD operations."""

from datetime import datetime
from typing import List, Optional

import structlog
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.exceptions import DocumentNotFoundError, StorageError
from src.core.models import Document, DocumentStatus, PipelineStage
from src.db.mongodb import Collections

logger = structlog.get_logger()


class DocumentRepository:
    """Repository for document operations."""

    def __init__(self, database: AsyncIOMotorDatabase):
        """Initialize repository.

        Args:
            database: MongoDB database instance
        """
        self.collection = database[Collections.DOCUMENTS]
        self.logger = logger.bind(component="DocumentRepository")

    async def create(self, document: Document) -> str:
        """Create a new document.

        Args:
            document: Document to create

        Returns:
            Document ID

        Raises:
            StorageError: If creation fails
        """
        try:
            doc_dict = document.model_dump()
            doc_dict["_id"] = document.id

            await self.collection.insert_one(doc_dict)

            self.logger.info("Document created", document_id=document.id)
            return document.id

        except Exception as e:
            self.logger.error("Failed to create document", error=str(e))
            raise StorageError(f"Failed to create document: {e}")

    async def get(self, document_id: str) -> Optional[Document]:
        """Get document by ID.

        Args:
            document_id: Document ID

        Returns:
            Document or None if not found
        """
        doc = await self.collection.find_one({"_id": document_id})

        if doc:
            doc["id"] = doc.pop("_id")
            return Document.model_validate(doc)

        return None

    async def get_or_raise(self, document_id: str) -> Document:
        """Get document by ID or raise exception.

        Args:
            document_id: Document ID

        Returns:
            Document

        Raises:
            DocumentNotFoundError: If document not found
        """
        document = await self.get(document_id)

        if not document:
            raise DocumentNotFoundError(f"Document not found: {document_id}")

        return document

    async def list(
        self,
        skip: int = 0,
        limit: int = 20,
        status: Optional[DocumentStatus] = None,
        sort_by: str = "upload_timestamp",
        sort_order: int = -1,
    ) -> tuple[list[Document], int]:
        """List documents with pagination.

        Args:
            skip: Number of documents to skip
            limit: Maximum documents to return
            status: Filter by status
            sort_by: Field to sort by
            sort_order: 1 for ascending, -1 for descending

        Returns:
            Tuple of (documents list, total count)
        """
        query = {}
        if status:
            query["status"] = status.value

        # Get total count
        total = await self.collection.count_documents(query)

        # Get documents
        cursor = self.collection.find(query)
        cursor = cursor.sort(sort_by, sort_order)
        cursor = cursor.skip(skip).limit(limit)

        documents = []
        async for doc in cursor:
            doc["id"] = doc.pop("_id")
            documents.append(Document.model_validate(doc))

        return documents, total

    async def update(self, document_id: str, **updates) -> bool:
        """Update document fields.

        Args:
            document_id: Document ID
            **updates: Fields to update

        Returns:
            True if updated, False if not found
        """
        if not updates:
            return False

        result = await self.collection.update_one(
            {"_id": document_id},
            {"$set": updates},
        )

        return result.modified_count > 0

    async def update_status(
        self,
        document_id: str,
        status: DocumentStatus,
        error_message: Optional[str] = None,
        current_stage: Optional[PipelineStage] = None,
    ) -> bool:
        """Update document status.

        Args:
            document_id: Document ID
            status: New status
            error_message: Error message if failed
            current_stage: Current pipeline stage

        Returns:
            True if updated
        """
        updates = {"status": status.value}

        if error_message is not None:
            updates["error_message"] = error_message

        if current_stage is not None:
            updates["current_stage"] = current_stage.value

        if status == DocumentStatus.PROCESSING:
            updates["processing_started_at"] = datetime.utcnow()
        elif status in (DocumentStatus.COMPLETED, DocumentStatus.FAILED):
            updates["processing_completed_at"] = datetime.utcnow()

        return await self.update(document_id, **updates)

    async def set_raw_text(
        self, document_id: str, raw_text: str, raw_text_by_page: List[str]
    ) -> bool:
        """Set extracted raw text.

        Args:
            document_id: Document ID
            raw_text: Full raw text
            raw_text_by_page: Text by page

        Returns:
            True if updated
        """
        return await self.update(
            document_id,
            raw_text=raw_text,
            raw_text_by_page=raw_text_by_page,
        )

    async def delete(self, document_id: str) -> bool:
        """Delete document.

        Args:
            document_id: Document ID

        Returns:
            True if deleted
        """
        result = await self.collection.delete_one({"_id": document_id})

        if result.deleted_count > 0:
            self.logger.info("Document deleted", document_id=document_id)
            return True

        return False

    async def exists(self, document_id: str) -> bool:
        """Check if document exists.

        Args:
            document_id: Document ID

        Returns:
            True if exists
        """
        count = await self.collection.count_documents({"_id": document_id})
        return count > 0

    async def get_by_filename(self, filename: str) -> Optional[Document]:
        """Get document by filename.

        Args:
            filename: Document filename

        Returns:
            Document or None
        """
        doc = await self.collection.find_one({"filename": filename})

        if doc:
            doc["id"] = doc.pop("_id")
            return Document.model_validate(doc)

        return None
