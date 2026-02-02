"""TOC (Table of Contents) repository."""

from typing import Optional

import structlog
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.exceptions import StorageError
from src.core.models import TOCLevel, TOCNode, TOCStructure
from src.db.mongodb import Collections

logger = structlog.get_logger()


class TOCRepository:
    """Repository for TOC node operations."""

    def __init__(self, database: AsyncIOMotorDatabase):
        """Initialize repository.

        Args:
            database: MongoDB database instance
        """
        self.collection = database[Collections.TOC_NODES]
        self.logger = logger.bind(component="TOCRepository")

    async def insert(self, node: TOCNode) -> str:
        """Insert a single TOC node.

        Args:
            node: TOC node to insert

        Returns:
            Node ID

        Raises:
            StorageError: If insertion fails
        """
        try:
            doc = node.model_dump()
            doc["_id"] = node.id

            await self.collection.insert_one(doc)

            self.logger.info(
                "TOC node inserted",
                node_id=node.id,
                document_id=node.document_id,
            )

            return node.id

        except Exception as e:
            self.logger.error("Failed to insert TOC node", error=str(e))
            raise StorageError(f"Failed to insert TOC node: {e}")

    async def bulk_insert(self, nodes: list[TOCNode]) -> int:
        """Insert multiple TOC nodes.

        Args:
            nodes: List of TOC nodes to insert

        Returns:
            Number of nodes inserted

        Raises:
            StorageError: If insertion fails
        """
        if not nodes:
            return 0

        try:
            docs = []
            for node in nodes:
                doc = node.model_dump()
                doc["_id"] = node.id
                docs.append(doc)

            result = await self.collection.insert_many(docs)

            self.logger.info(
                "TOC nodes inserted",
                count=len(result.inserted_ids),
                document_id=nodes[0].document_id if nodes else None,
            )

            return len(result.inserted_ids)

        except Exception as e:
            self.logger.error("Failed to insert TOC nodes", error=str(e))
            raise StorageError(f"Failed to insert TOC nodes: {e}")

    async def get(self, node_id: str) -> Optional[TOCNode]:
        """Get TOC node by ID.

        Args:
            node_id: Node ID

        Returns:
            TOCNode or None
        """
        doc = await self.collection.find_one({"_id": node_id})

        if doc:
            doc["id"] = doc.pop("_id")
            return TOCNode.model_validate(doc)

        return None

    async def get_by_document(
        self,
        document_id: str,
        level: Optional[TOCLevel] = None,
    ) -> list[TOCNode]:
        """Get all TOC nodes for a document.

        Args:
            document_id: Document ID
            level: Optional level filter

        Returns:
            List of TOC nodes
        """
        query = {"document_id": document_id}

        if level is not None:
            query["level"] = level.value

        cursor = self.collection.find(query).sort("sequence_number", 1)

        nodes = []
        async for doc in cursor:
            doc["id"] = doc.pop("_id")
            nodes.append(TOCNode.model_validate(doc))

        return nodes

    async def get_tree(self, document_id: str) -> TOCStructure:
        """Get complete TOC tree for a document.

        Args:
            document_id: Document ID

        Returns:
            TOCStructure with all nodes
        """
        nodes = await self.get_by_document(document_id)

        # Find root nodes (L1)
        root_nodes = [n.id for n in nodes if n.level == TOCLevel.L1]

        # Count by level
        total_l1 = len([n for n in nodes if n.level == TOCLevel.L1])
        total_l2 = len([n for n in nodes if n.level == TOCLevel.L2])
        total_l3 = len([n for n in nodes if n.level == TOCLevel.L3])

        return TOCStructure(
            document_id=document_id,
            root_nodes=root_nodes,
            all_nodes=nodes,
            total_l1=total_l1,
            total_l2=total_l2,
            total_l3=total_l3,
        )

    async def get_context_path(self, node_id: str) -> str:
        """Get full context path for a node (breadcrumb).

        Args:
            node_id: Node ID

        Returns:
            Context path string (e.g., "Chapter 1 > Section 1.2 > Topic")
        """
        node = await self.get(node_id)

        if not node:
            return ""

        path_parts = [node.title]
        current = node

        while current.parent_id:
            parent = await self.get(current.parent_id)
            if parent:
                path_parts.insert(0, parent.title)
                current = parent
            else:
                break

        return " > ".join(path_parts)

    async def get_children(self, node_id: str) -> list[TOCNode]:
        """Get child nodes of a parent.

        Args:
            node_id: Parent node ID

        Returns:
            List of child nodes
        """
        cursor = self.collection.find({"parent_id": node_id}).sort("sequence_number", 1)

        nodes = []
        async for doc in cursor:
            doc["id"] = doc.pop("_id")
            nodes.append(TOCNode.model_validate(doc))

        return nodes

    async def update(self, node_id: str, **updates) -> bool:
        """Update TOC node fields.

        Args:
            node_id: Node ID
            **updates: Fields to update

        Returns:
            True if updated
        """
        if not updates:
            return False

        result = await self.collection.update_one(
            {"_id": node_id},
            {"$set": updates},
        )

        return result.modified_count > 0

    async def add_chunk_link(
        self,
        node_id: str,
        chunk_id: str,
        chunk_type: str,
    ) -> bool:
        """Add chunk ID to a TOC node.

        Args:
            node_id: TOC node ID
            chunk_id: Chunk ID to link
            chunk_type: "retrieval" or "generation"

        Returns:
            True if updated
        """
        field = (
            "retrieval_chunk_ids"
            if chunk_type == "retrieval"
            else "generation_chunk_ids"
        )

        result = await self.collection.update_one(
            {"_id": node_id},
            {"$addToSet": {field: chunk_id}},
        )

        return result.modified_count > 0

    async def add_entity_link(self, node_id: str, entity_id: str) -> bool:
        """Add entity ID to a TOC node.

        Args:
            node_id: TOC node ID
            entity_id: Entity ID to link

        Returns:
            True if updated
        """
        result = await self.collection.update_one(
            {"_id": node_id},
            {"$addToSet": {"entity_ids": entity_id}},
        )

        return result.modified_count > 0

    async def delete_by_document(self, document_id: str) -> int:
        """Delete all TOC nodes for a document.

        Args:
            document_id: Document ID

        Returns:
            Number of deleted nodes
        """
        result = await self.collection.delete_many({"document_id": document_id})

        self.logger.info(
            "TOC nodes deleted",
            document_id=document_id,
            count=result.deleted_count,
        )

        return result.deleted_count

    async def search_by_title(
        self,
        document_id: str,
        query: str,
        limit: int = 10,
    ) -> list[TOCNode]:
        """Search TOC nodes by title.

        Args:
            document_id: Document ID
            query: Search query
            limit: Maximum results

        Returns:
            Matching TOC nodes
        """
        # Simple regex search (for MVP, could use text index)
        cursor = self.collection.find(
            {
                "document_id": document_id,
                "title": {"$regex": query, "$options": "i"},
            }
        ).limit(limit)

        nodes = []
        async for doc in cursor:
            doc["id"] = doc.pop("_id")
            nodes.append(TOCNode.model_validate(doc))

        return nodes
