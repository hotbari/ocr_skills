"""TOC 노드 컬렉션 레포지터리."""

from typing import Optional

import structlog

from src.core.models import TOCNode, TOCStructure
from src.db.mongodb import Collections, MongoDB

logger = structlog.get_logger()


class TOCRepository:
    @property
    def collection(self):
        return MongoDB.get_collection(Collections.TOC_NODES)

    async def upsert(self, node: TOCNode) -> None:
        data = node.model_dump(mode="json")
        await self.collection.replace_one(
            {"_id": node.id}, {"_id": node.id, **data}, upsert=True
        )

    async def upsert_many(self, nodes: list[TOCNode]) -> None:
        for node in nodes:
            await self.upsert(node)

    async def get(self, node_id: str) -> Optional[TOCNode]:
        doc = await self.collection.find_one({"_id": node_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return TOCNode(**doc)

    async def get_structure(self, document_id: str) -> TOCStructure:
        """문서의 전체 TOC 구조 반환."""
        cursor = self.collection.find({"document_id": document_id}).sort("sequence_number", 1)
        nodes = []
        async for d in cursor:
            d.pop("_id", None)
            nodes.append(TOCNode(**d))

        total_l1 = sum(1 for n in nodes if n.level == 1)
        total_l2 = sum(1 for n in nodes if n.level == 2)
        total_l3 = sum(1 for n in nodes if n.level == 3)

        return TOCStructure(
            document_id=document_id,
            nodes=nodes,
            total_l1=total_l1,
            total_l2=total_l2,
            total_l3=total_l3,
        )

    async def delete_by_document(self, document_id: str) -> int:
        result = await self.collection.delete_many({"document_id": document_id})
        return result.deleted_count
