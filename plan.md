# RAG VectorDB PDF Pipeline - Implementation Plan (MVP)

## Overview
PDF에서 OCR로 텍스트 추출 → 5단계 **OpenAI API** 파이프라인 → MongoDB 저장 → FastAPI 서빙

## Tech Stack (MVP)
- **OCR**: PyMuPDF + pytesseract
- **DB**: MongoDB (Local Docker)
- **Backend**: FastAPI
- **LLM**: **OpenAI API** (gpt-4o 또는 gpt-4o-mini)
- **Embeddings**: OpenAI (text-embedding-3-small)

---

## LLM 사용 위치 정리

| Stage | LLM 호출 | 목적 | 입력 | 출력 |
|-------|----------|------|------|------|
| **Stage 1** | O | 의미 기반 세그먼트 분할 | raw_text (PDF 전체) | segments[] JSON |
| **Stage 2** | O | 후보 헤딩 생성 | segments[] | segments + candidate_headings |
| **Stage 3** | O | TOC 구조 정렬 (L1/L2/L3) | segments + headings | toc_structure |
| **Stage 4** | O | TOC 정규화 (체크리스트 강제) | toc_structure | normalized_toc |
| **Stage 5** | O | 최종 청킹 + 컨텍스트 생성 | normalized_toc + segments | chunks[] |
| **Embedding** | O | 벡터 임베딩 생성 | chunk.content | float[1536] |
| **Search** | O | 쿼리 임베딩 | user_query | float[1536] |

**총 LLM 호출**: 문서당 5회 (Stage 1-5) + 청크 수만큼 임베딩 + 검색당 1회

---

## FastAPI + OpenAI API 연동 상세 설명

### 1. OpenAI Client 설정

```python
# src/llm/openai_client.py
from openai import AsyncOpenAI
from pydantic import BaseModel
import json

class OpenAIClient:
    def __init__(self, api_key: str):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = "gpt-4o-mini"  # 비용 효율적, gpt-4o로 업그레이드 가능

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel]  # Pydantic 모델
    ) -> dict:
        """
        OpenAI의 Structured Output 기능 사용
        JSON Schema를 강제하여 안정적인 JSON 응답 보장
        """
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": response_schema.__name__,
                    "schema": response_schema.model_json_schema()
                }
            }
        )
        return json.loads(response.choices[0].message.content)
```

### 2. Pipeline Stage 구현 예시 (Stage 1)

```python
# src/pipeline/stage1_semantic_segmentation.py
from pydantic import BaseModel
from src.llm.openai_client import OpenAIClient
from src.prompts.template_loader import load_template

# 출력 스키마 정의
class Segment(BaseModel):
    segment_id: int
    content: str
    semantic_type: str  # "definition" | "procedure" | "example" 등
    key_concepts: list[str]
    reasoning: str

class Stage1Output(BaseModel):
    segments: list[Segment]
    total_segments: int

class Stage1SemanticSegmentation:
    def __init__(self, llm_client: OpenAIClient):
        self.llm = llm_client
        self.system_prompt = load_template("stage1_system.txt")

    async def execute(self, raw_text: str) -> Stage1Output:
        """
        PDF에서 추출한 raw_text를 의미 기반으로 분할
        """
        user_prompt = f"""
        다음 문서를 의미 기반으로 세그먼트로 분할하세요.

        <document>
        {raw_text}
        </document>
        """

        result = await self.llm.generate_structured(
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            response_schema=Stage1Output
        )

        return Stage1Output(**result)
```

### 3. FastAPI Endpoint 구현

```python
# src/api/routers/pipeline.py
from fastapi import APIRouter, Depends, BackgroundTasks
from src.pipeline.orchestrator import PipelineOrchestrator
from src.db.repositories.document_repo import DocumentRepository

router = APIRouter(prefix="/api/v1/pipeline", tags=["Pipeline"])

@router.post("/run/{document_id}")
async def run_pipeline(
    document_id: str,
    background_tasks: BackgroundTasks,
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator)
):
    """
    문서에 대해 5단계 파이프라인 실행 (비동기)
    """
    # Background task로 실행 (오래 걸리므로)
    background_tasks.add_task(
        orchestrator.run_full_pipeline,
        document_id
    )

    return {
        "document_id": document_id,
        "status": "processing",
        "message": "Pipeline started in background"
    }
```

### 4. Pipeline Orchestrator

```python
# src/pipeline/orchestrator.py
from src.pipeline.stage1_semantic_segmentation import Stage1SemanticSegmentation
from src.pipeline.stage2_candidate_headings import Stage2CandidateHeadings
from src.pipeline.stage3_toc_alignment import Stage3TOCAlignment
from src.pipeline.stage4_toc_normalization import Stage4TOCNormalization
from src.pipeline.stage5_chunking import Stage5Chunking
from src.embeddings.openai_provider import OpenAIEmbeddingProvider

class PipelineOrchestrator:
    def __init__(
        self,
        llm_client: OpenAIClient,
        embedding_provider: OpenAIEmbeddingProvider,
        document_repo: DocumentRepository,
        chunk_repo: ChunkRepository
    ):
        self.stage1 = Stage1SemanticSegmentation(llm_client)
        self.stage2 = Stage2CandidateHeadings(llm_client)
        self.stage3 = Stage3TOCAlignment(llm_client)
        self.stage4 = Stage4TOCNormalization(llm_client)
        self.stage5 = Stage5Chunking(llm_client)
        self.embedding = embedding_provider
        self.doc_repo = document_repo
        self.chunk_repo = chunk_repo

    async def run_full_pipeline(self, document_id: str):
        # 1. 문서 조회
        doc = await self.doc_repo.get(document_id)
        raw_text = doc.raw_text

        # 2. Stage 1: 의미 기반 분할
        stage1_result = await self.stage1.execute(raw_text)

        # 3. Stage 2: 후보 헤딩 생성
        stage2_result = await self.stage2.execute(stage1_result.segments)

        # 4. Stage 3: TOC 구조 정렬
        stage3_result = await self.stage3.execute(stage2_result)

        # 5. Stage 4: TOC 정규화
        stage4_result = await self.stage4.execute(stage3_result)

        # 6. Stage 5: 최종 청킹
        stage5_result = await self.stage5.execute(
            normalized_toc=stage4_result,
            original_segments=stage1_result.segments
        )

        # 7. Embedding 생성
        chunks_with_embeddings = await self.embedding.embed_chunks(
            stage5_result.chunks
        )

        # 8. MongoDB 저장
        await self.chunk_repo.bulk_insert(chunks_with_embeddings)

        # 9. 문서 상태 업데이트
        await self.doc_repo.update_status(document_id, "completed")

        return {
            "document_id": document_id,
            "total_chunks": len(chunks_with_embeddings)
        }
```

### 5. Embedding 처리

```python
# src/embeddings/openai_provider.py
from openai import AsyncOpenAI

class OpenAIEmbeddingProvider:
    def __init__(self, api_key: str):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = "text-embedding-3-small"
        self.dimensions = 1536

    async def embed_single(self, text: str) -> list[float]:
        response = await self.client.embeddings.create(
            model=self.model,
            input=text
        )
        return response.data[0].embedding

    async def embed_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        """배치 임베딩 (최대 2048개씩)"""
        texts = [chunk.content for chunk in chunks]

        # OpenAI는 한 번에 여러 텍스트 임베딩 가능
        response = await self.client.embeddings.create(
            model=self.model,
            input=texts
        )

        for chunk, embedding_data in zip(chunks, response.data):
            chunk.embedding = embedding_data.embedding
            chunk.embedding_model = self.model

        return chunks
```

### 6. Vector Search 구현

```python
# src/db/repositories/chunk_repo.py
import numpy as np
from motor.motor_asyncio import AsyncIOMotorCollection

class ChunkRepository:
    def __init__(self, collection: AsyncIOMotorCollection):
        self.collection = collection

    async def vector_search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        document_id: str = None
    ) -> list[dict]:
        """
        MVP: 모든 chunk를 가져와서 Python에서 cosine similarity 계산
        (프로덕션에서는 Atlas Vector Search 사용)
        """
        filter_query = {}
        if document_id:
            filter_query["document_id"] = document_id

        # 모든 chunk 조회
        chunks = await self.collection.find(filter_query).to_list(length=None)

        # Cosine similarity 계산
        query_vec = np.array(query_embedding)
        results = []
        for chunk in chunks:
            chunk_vec = np.array(chunk["embedding"])
            similarity = np.dot(query_vec, chunk_vec) / (
                np.linalg.norm(query_vec) * np.linalg.norm(chunk_vec)
            )
            results.append({**chunk, "score": float(similarity)})

        # Top-K 정렬
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
```

---

## API 흐름도

```
[User] --POST /documents/upload--> [FastAPI]
                                      |
                                      v
                              [OCR: PyMuPDF + Tesseract]
                                      |
                                      v
                              [MongoDB: documents 저장]
                                      |
                                      v
       <-- {document_id} --[Response]

[User] --POST /pipeline/run/{doc_id}--> [FastAPI]
                                           |
                                           v
                                   [Background Task 시작]
                                           |
       <-- {status: "processing"} --[Response]

                    [Background에서 실행]
                           |
    +----------------------+----------------------+
    |                      |                      |
    v                      v                      v
[Stage 1]            [Stage 2]              [Stage 3]
OpenAI API 호출      OpenAI API 호출        OpenAI API 호출
의미 분할            헤딩 생성               TOC 구조화
    |                      |                      |
    +----------------------+----------------------+
                           |
    +----------------------+----------------------+
    |                      |                      |
    v                      v                      v
[Stage 4]            [Stage 5]            [Embedding]
OpenAI API 호출      OpenAI API 호출       OpenAI API 호출
TOC 정규화           최종 청킹             text-embedding-3-small
    |                      |                      |
    +----------------------+----------------------+
                           |
                           v
                   [MongoDB: chunks 저장]

[User] --POST /search/semantic--> [FastAPI]
                                      |
                                      v
                            [Query Embedding]
                            OpenAI API 호출
                                      |
                                      v
                            [Vector Search]
                            (cosine similarity)
                                      |
                                      v
       <-- {results: [...]} --[Response]
```

---

## Project Structure (MVP 간소화)

```
260128_OCR_skills/
├── pyproject.toml
├── docker-compose.yml          # MongoDB만
├── .env                        # OPENAI_API_KEY
├── src/
│   ├── api/
│   │   ├── main.py
│   │   └── routers/
│   │       ├── documents.py
│   │       ├── pipeline.py
│   │       └── search.py
│   ├── core/
│   │   └── config.py
│   ├── ocr/
│   │   ├── extractor.py
│   │   └── pymupdf_handler.py
│   ├── pipeline/
│   │   ├── orchestrator.py
│   │   ├── stage1_semantic_segmentation.py
│   │   ├── stage2_candidate_headings.py
│   │   ├── stage3_toc_alignment.py
│   │   ├── stage4_toc_normalization.py
│   │   └── stage5_chunking.py
│   ├── prompts/
│   │   └── templates/          # .txt 파일 (프롬프트)
│   ├── llm/
│   │   └── openai_client.py
│   ├── embeddings/
│   │   └── openai_provider.py
│   └── db/
│       ├── mongodb.py
│       └── repositories/
│           ├── document_repo.py
│           └── chunk_repo.py
└── tests/
```

---

## Implementation Order (MVP)

### Phase 1: 기반 구축
1. `uv init` + dependencies
2. `docker-compose.yml` (MongoDB)
3. `.env` + config.py
4. FastAPI app skeleton

### Phase 2: OCR
5. PyMuPDF 텍스트 추출
6. Document upload endpoint

### Phase 3: LLM 연동
7. OpenAI client (structured output)
8. 프롬프트 템플릿 로더

### Phase 4: Pipeline
9. Stage 1-5 구현
10. Pipeline orchestrator

### Phase 5: 검색
11. OpenAI embedding provider
12. Vector search (in-memory cosine)
13. Search endpoint

---

## 환경 변수 (.env)

```
OPENAI_API_KEY=sk-...
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=rag_vectordb
OPENAI_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small
```

---

## Verification

1. **OCR 테스트**: PDF 업로드 → raw_text 확인
2. **Stage 테스트**: 각 stage 개별 호출 → JSON 출력 검증
3. **E2E 테스트**: 업로드 → 파이프라인 → 검색 전체 플로우
