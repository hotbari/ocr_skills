"""Search API router."""

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.dependencies import (get_chunk_repo, get_document_repo,
                                  get_embedding_provider, get_entity_repo,
                                  get_toc_repo)
from src.db.repositories.chunk_repo import ChunkRepository
from src.db.repositories.document_repo import DocumentRepository
from src.db.repositories.entity_repo import EntityRepository
from src.db.repositories.toc_repo import TOCRepository
from src.embeddings.openai_provider import OpenAIEmbeddingProvider

router = APIRouter(prefix="/api/v1/search", tags=["Search"])


class SemanticSearchRequest(BaseModel):
    """Semantic search request."""

    query: str = Field(..., min_length=1)
    document_ids: Optional[list[str]] = None
    top_k: int = Field(default=10, ge=1, le=100)
    min_score: float = Field(default=0.5, ge=0.0, le=1.0)
    include_entities: bool = True
    include_generation_chunks: bool = True


@router.post("/semantic")
async def semantic_search(
    request: SemanticSearchRequest,
    chunk_repo: ChunkRepository = Depends(get_chunk_repo),
    toc_repo: TOCRepository = Depends(get_toc_repo),
    entity_repo: EntityRepository = Depends(get_entity_repo),
    embedding_provider: OpenAIEmbeddingProvider = Depends(get_embedding_provider),
):
    """Perform semantic vector search.

    Flow:
    1. Embed query
    2. Search retrieval chunks by vector similarity
    3. For each match, fetch linked generation chunk, TOC node, entities
    4. Return enriched results
    """
    start_time = time.time()

    # Generate query embedding
    embed_start = time.time()
    query_embedding = await embedding_provider.embed_query(request.query)
    embed_time = (time.time() - embed_start) * 1000

    # Search retrieval chunks
    search_start = time.time()

    # If filtering by documents, search each
    if request.document_ids:
        all_results = []
        for doc_id in request.document_ids:
            results = await chunk_repo.vector_search(
                query_embedding=query_embedding,
                document_id=doc_id,
                top_k=request.top_k,
                min_score=request.min_score,
            )
            all_results.extend(results)

        # Sort combined results and take top_k
        all_results.sort(key=lambda x: x.score, reverse=True)
        search_results = all_results[: request.top_k]
    else:
        search_results = await chunk_repo.vector_search(
            query_embedding=query_embedding,
            top_k=request.top_k,
            min_score=request.min_score,
        )

    search_time = (time.time() - search_start) * 1000

    # Enrich results
    enriched_results = []
    for result in search_results:
        # Get TOC node and context path
        toc_node = await toc_repo.get(result.retrieval_chunk.toc_node_id)
        context_path = ""
        if toc_node:
            context_path = await toc_repo.get_context_path(toc_node.id)

        # Get entities if requested
        entities = []
        if request.include_entities and result.generation_chunk:
            entities = await entity_repo.get_by_generation_chunk(
                result.generation_chunk.id
            )

        enriched = {
            "score": result.score,
            "context_path": context_path,
            "retrieval_chunk": {
                "id": result.retrieval_chunk.id,
                "content": result.retrieval_chunk.content,
                "key_concepts": result.retrieval_chunk.key_concepts,
                "page_numbers": result.retrieval_chunk.page_numbers,
                "document_id": result.retrieval_chunk.document_id,
            },
        }

        if request.include_generation_chunks and result.generation_chunk:
            enriched["generation_chunk"] = {
                "id": result.generation_chunk.id,
                "content": result.generation_chunk.content,
                "summary": result.generation_chunk.summary,
                "key_concepts": result.generation_chunk.key_concepts,
                "context_path": result.generation_chunk.context_path,
            }

        if toc_node:
            enriched["toc_node"] = {
                "id": toc_node.id,
                "title": toc_node.title,
                "level": (
                    toc_node.level.value
                    if hasattr(toc_node.level, "value")
                    else toc_node.level
                ),
            }

        if entities:
            enriched["entities"] = [
                {
                    "id": e.id,
                    "type": (
                        e.entity_type.value
                        if hasattr(e.entity_type, "value")
                        else e.entity_type
                    ),
                    "page_number": e.page_number,
                    "caption": e.caption,
                    "markdown": e.markdown[:500] if e.markdown else None,
                }
                for e in entities[:5]  # Limit entities per result
            ]

        enriched_results.append(enriched)

    total_time = (time.time() - start_time) * 1000

    return {
        "query": request.query,
        "query_embedding_time_ms": embed_time,
        "search_time_ms": search_time,
        "total_time_ms": total_time,
        "results": enriched_results,
        "total_found": len(enriched_results),
    }


class TOCSearchRequest(BaseModel):
    """TOC search request."""

    document_id: str
    query: str
    level_filter: Optional[list[int]] = None


@router.post("/toc")
async def search_toc(
    request: TOCSearchRequest,
    document_repo: DocumentRepository = Depends(get_document_repo),
    toc_repo: TOCRepository = Depends(get_toc_repo),
):
    """Search within TOC structure (keyword-based)."""
    # Check document exists
    exists = await document_repo.exists(request.document_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Document not found")

    # Search TOC nodes
    nodes = await toc_repo.search_by_title(
        document_id=request.document_id,
        query=request.query,
        limit=20,
    )

    # Apply level filter
    if request.level_filter:
        nodes = [
            n
            for n in nodes
            if (n.level.value if hasattr(n.level, "value") else n.level)
            in request.level_filter
        ]

    return {
        "document_id": request.document_id,
        "query": request.query,
        "matching_nodes": [
            {
                "id": n.id,
                "title": n.title,
                "level": n.level.value if hasattr(n.level, "value") else n.level,
                "parent_id": n.parent_id,
                "page_start": n.page_start,
            }
            for n in nodes
        ],
        "total_found": len(nodes),
    }


@router.get("/chunks/{document_id}")
async def list_chunks(
    document_id: str,
    chunk_type: str = Query("retrieval", regex="^(retrieval|generation)$"),
    toc_node_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    document_repo: DocumentRepository = Depends(get_document_repo),
    chunk_repo: ChunkRepository = Depends(get_chunk_repo),
):
    """List chunks for a document with pagination."""
    # Check document exists
    exists = await document_repo.exists(document_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Document not found")

    skip = (page - 1) * page_size

    if chunk_type == "retrieval":
        if toc_node_id:
            chunks = await chunk_repo.get_retrieval_chunks_by_toc(toc_node_id)
            # Manual pagination
            chunks = chunks[skip : skip + page_size]
        else:
            chunks = await chunk_repo.get_retrieval_chunks_by_document(
                document_id, skip=skip, limit=page_size
            )
    else:
        chunks = await chunk_repo.get_generation_chunks_by_document(
            document_id, skip=skip, limit=page_size
        )

    return {
        "document_id": document_id,
        "chunk_type": chunk_type,
        "chunks": [c.model_dump(exclude={"embedding"}) for c in chunks],
        "page": page,
        "page_size": page_size,
        "count": len(chunks),
    }


@router.get("/entities/{document_id}")
async def list_entities(
    document_id: str,
    entity_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    document_repo: DocumentRepository = Depends(get_document_repo),
    entity_repo: EntityRepository = Depends(get_entity_repo),
):
    """List entities for a document with pagination."""
    # Check document exists
    exists = await document_repo.exists(document_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Document not found")

    skip = (page - 1) * page_size

    # Parse entity type
    from src.core.models import EntityType

    type_filter = None
    if entity_type:
        try:
            type_filter = EntityType(entity_type)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid entity type: {entity_type}"
            )

    entities = await entity_repo.get_by_document(
        document_id,
        entity_type=type_filter,
        skip=skip,
        limit=page_size,
    )

    return {
        "document_id": document_id,
        "entity_type_filter": entity_type,
        "entities": [
            {
                "id": e.id,
                "type": e.entity_type.value,
                "page_number": e.page_number,
                "toc_node_id": e.toc_node_id,
                "caption": e.caption,
                "markdown": e.markdown,
                "vision_description": e.vision_description,
                "vision_processed": e.vision_processed,
            }
            for e in entities
        ],
        "page": page,
        "page_size": page_size,
        "count": len(entities),
    }
