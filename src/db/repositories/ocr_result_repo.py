"""OCR Result (PRD 형식) MongoDB 저장소."""

from typing import Optional

import structlog

from src.core.ocr_result import OCRResult
from src.db.mongodb import MongoDB

logger = structlog.get_logger()
COLLECTION = "ocr_results"


class OCRResultRepository:

    def _col(self):
        return MongoDB.get_collection(COLLECTION)

    async def upsert(self, result: OCRResult) -> None:
        """document_id 기준 upsert."""
        doc = result.model_dump(mode="json")
        doc["_id"] = result.ref_document_id
        await self._col().replace_one(
            {"_id": result.ref_document_id},
            doc,
            upsert=True,
        )
        logger.info("OCRResult 저장", document_id=result.ref_document_id)

    async def get_by_document(self, document_id: str) -> Optional[OCRResult]:
        doc = await self._col().find_one({"_id": document_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return OCRResult.model_validate(doc)

    async def list_all(self, page: int = 1, page_size: int = 20) -> tuple[list[OCRResult], int]:
        total = await self._col().count_documents({})
        cursor = (
            self._col()
            .find({}, {"page": 0})   # page 필드 제외하고 목록 조회 (성능)
            .sort("created_at", -1)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        results = []
        async for doc in cursor:
            doc.pop("_id", None)
            doc.setdefault("page", [])
            results.append(OCRResult.model_validate(doc))
        return results, total

    async def delete(self, document_id: str) -> None:
        await self._col().delete_one({"_id": document_id})
