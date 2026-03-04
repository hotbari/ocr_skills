# OCR 프로세스 상세 문서

## 목차
1. [프로젝트 개요](#1-프로젝트-개요)
2. [기술 스택](#2-기술-스택)
3. [8단계 파이프라인 아키텍처](#3-8단계-파이프라인-아키텍처)
4. [Stage별 상세 프로세스](#4-stage별-상세-프로세스)
5. [Dual-Chunk System](#5-dual-chunk-system)
6. [상태 관리 및 재개 메커니즘](#6-상태-관리-및-재개-메커니즘)
7. [LLM 통합 전략](#7-llm-통합-전략)
8. [데이터 모델](#8-데이터-모델)
9. [장점과 단점](#9-장점과-단점)
10. [특징 및 차별점](#10-특징-및-차별점)

---

## 1. 프로젝트 개요

### 1.1 프로젝트 목적
이 프로젝트는 **PDF 문서를 RAG(Retrieval-Augmented Generation) 시스템용 벡터 데이터베이스로 변환하는 8단계 OCR 파이프라인**입니다.

### 1.2 핵심 목표
- PDF에서 텍스트, 테이블, 이미지를 정확하게 추출
- 의미 기반 구조화를 통한 고품질 검색 지원
- 이중 청크 시스템(Retrieval + Generation)으로 검색과 답변 생성 최적화
- 중단 후 재개(Resume) 가능한 안정적 파이프라인

### 1.3 시스템 흐름도

```
┌─────────────┐
│ PDF 업로드   │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│              8-Stage Pipeline                           │
├─────────────────────────────────────────────────────────┤
│  Stage 0: PDF → Raw Text (OCR)                          │
│  Stage 1: Raw Text → Segments (의미 단위 분리)          │
│  Stage 2: Segments → Candidate Headings (제목 생성)     │
│  Stage 3: Headings → TOC Hierarchy (계층 정렬)          │
│  Stage 4: TOC → Normalized TOC (제목 정규화)            │
│  Stage 5: TOC → Dual Chunks (이중 청킹)                 │
│  Stage 5b: PDF → Entities (테이블/이미지 추출)          │
│  Stage 6: Images → Vision Descriptions (이미지 분석)    │
│  Stage 7: Chunks → Embeddings (벡터화)                  │
└──────┬──────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────┐
│ MongoDB 저장    │
│ - documents     │
│ - toc_nodes     │
│ - retrieval_    │
│   chunks        │
│ - generation_   │
│   chunks        │
│ - entities      │
└─────────────────┘
       │
       ▼
┌─────────────────┐
│ Vector Search   │
│ + QA System     │
└─────────────────┘
```

---

## 2. 기술 스택

### 2.1 Core Technologies

| 기술 | 버전 | 용도 |
|-----|------|------|
| **Python** | 3.11+ | 백엔드 언어 |
| **FastAPI** | Latest | REST API 서버 |
| **MongoDB** | Latest | 문서/청크/임베딩 저장 |
| **PyMuPDF (fitz)** | Latest | PDF 텍스트 추출 |
| **pytesseract** | Latest | 스캔 PDF OCR (fallback) |
| **OpenAI API** | Latest | LLM 및 임베딩 |

### 2.2 LLM 및 임베딩

| 컴포넌트 | 모델 | 용도 |
|---------|------|------|
| **LLM (Stage 1-5)** | gpt-4o-mini | 텍스트 구조화, 세그멘테이션, TOC 생성 |
| **Vision API (Stage 6)** | gpt-4o-vision | 이미지/다이어그램/차트 분석 |
| **Embedding (Stage 7)** | text-embedding-3-small | 벡터 임베딩 (1536차원) |

### 2.3 주요 라이브러리

```python
# 주요 의존성 (pyproject.toml)
dependencies = [
    "fastapi",
    "uvicorn",
    "pydantic>=2.0",
    "pydantic-settings",
    "pymupdf",           # PDF 텍스트 추출
    "pytesseract",       # OCR fallback
    "pillow",            # 이미지 처리
    "motor",             # MongoDB async driver
    "openai",            # OpenAI API
    "langdetect",        # 언어 감지
    "tiktoken",          # 토큰 카운팅
    "structlog",         # 구조화 로깅
    "python-multipart",  # 파일 업로드
    "aiofiles",          # 비동기 파일 처리
]
```

---

## 3. 8단계 파이프라인 아키텍처

### 3.1 파이프라인 개요

이 시스템은 **8개의 독립적이면서도 순차적인 Stage**로 구성됩니다. 각 Stage는:
- **입력**: 이전 Stage의 출력 (또는 PDF 파일)
- **처리**: 특정 변환 작업 수행
- **출력**: 구조화된 JSON 데이터
- **저장**: `pipeline_state/{document_id}/stage{N}_output.json`

### 3.2 Stage 의존성 그래프

```
Stage 0: PDF Extraction
    │
    ├──→ Stage 1: Segmentation
    │         │
    │         └──→ Stage 2: Headings
    │                   │
    │                   └──→ Stage 3: TOC Alignment
    │                             │
    │                             └──→ Stage 4: TOC Normalization
    │                                       │
    │                                       ├──→ Stage 5: Chunking
    │                                       │
    └──→ Stage 5b: Entities ←──────────────┘
              │
              └──→ Stage 6: Vision
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
      Stage 7: Embedding    (MongoDB 최종 저장)
```

### 3.3 Orchestrator 역할

`PipelineOrchestrator`는 다음을 담당합니다:

```python
class PipelineOrchestrator:
    """8단계 파이프라인 오케스트레이터"""

    STAGE_ORDER = [
        PipelineStage.STAGE_0_EXTRACTION,      # PDF → Raw Text
        PipelineStage.STAGE_1_SEGMENTATION,    # Text → Segments
        PipelineStage.STAGE_2_HEADINGS,        # Segments → Headings
        PipelineStage.STAGE_3_TOC_ALIGNMENT,   # Headings → TOC Tree
        PipelineStage.STAGE_4_TOC_NORMALIZATION, # TOC → Normalized TOC
        PipelineStage.STAGE_5_CHUNKING,        # TOC → Dual Chunks
        PipelineStage.STAGE_5B_ENTITIES,       # PDF → Tables/Images
        PipelineStage.STAGE_6_VISION,          # Images → Descriptions
        PipelineStage.STAGE_7_EMBEDDING,       # Chunks → Vectors
    ]
```

**주요 기능:**
1. **순차 실행**: Stage를 순서대로 실행
2. **상태 저장**: 각 Stage 완료 시 결과를 JSON으로 저장
3. **재개 지원**: 중단 시 마지막 완료 Stage부터 재시작
4. **오류 처리**: Stage 실패 시 로그 기록 및 상태 업데이트
5. **DB 동기화**: 주요 Stage 완료 시 MongoDB에 데이터 저장

---

## 4. Stage별 상세 프로세스

### Stage 0: PDF 추출 (Extraction)

#### 목적
PDF 파일에서 모든 콘텐츠(텍스트, 테이블, 이미지)를 추출합니다.

#### 입력
```python
Stage0Input:
    document_id: str
    file_path: Path  # PDF 파일 경로
```

#### 처리 과정

**1. 스캔 PDF 감지**
```python
is_scanned = self.text_handler.check_is_scanned(pdf_path)
# PyMuPDF로 텍스트 레이어 존재 여부 확인
# 텍스트 추출률이 임계값 이하면 스캔 PDF로 판단
```

**2. 텍스트 추출**
```python
# 방법 1: PyMuPDF (네이티브 텍스트 레이어 추출)
import fitz
doc = fitz.open(pdf_path)
for page in doc:
    text = page.get_text()  # 빠르고 정확

# 방법 2: pytesseract (스캔 PDF용 OCR)
# 현재는 TODO - 향후 구현 예정
```

**3. 메타데이터 추출**
```python
metadata = {
    "title": doc.metadata.get("title"),
    "author": doc.metadata.get("author"),
    "page_count": len(doc),
    "file_size_bytes": pdf_path.stat().st_size,
}
```

**4. 언어 감지**
```python
from langdetect import detect
detected_language = detect(raw_text)
# "ko", "en", "mixed", "unknown"
```

**5. 테이블 추출**
```python
# PyMuPDF의 테이블 감지 기능 사용
tables = page.find_tables()
```

**6. 이미지 추출**
```python
# PDF 내 임베디드 이미지 추출
images = page.get_images()
for img in images:
    # 이미지를 파일로 저장
    # uploads/{document_id}/images/ 에 저장
```

#### 출력
```python
ExtractionResult:
    document_id: str
    raw_text: str              # 전체 텍스트
    page_count: int
    text_by_page: list[PageText]  # 페이지별 텍스트
    tables: list[ExtractedTable]
    images: list[ExtractedImage]
    metadata: dict
    detected_language: Language
    is_scanned: bool
```

#### 특징
- **빠른 처리**: PyMuPDF는 매우 빠름 (100페이지 PDF를 수 초 내 처리)
- **Fallback 지원**: 스캔 PDF 감지 시 pytesseract OCR로 전환 (현재 TODO)
- **다국어 지원**: 언어 자동 감지

---

### Stage 1: 세그멘테이션 (Segmentation)

#### 목적
원시 텍스트를 **의미 기반 세그먼트**로 분할합니다.

#### 입력
```python
Stage1Input:
    document_id: str
    raw_text: str
    raw_text_by_page: list[str]
    page_count: int
```

#### 처리 과정

**1. LLM Prompt 구성**
```python
system_prompt = """
당신은 전문 문서 분석가입니다.
주어진 텍스트를 의미 기반으로 세그먼트로 분할하세요.

세그먼트 분할 기준:
- 정의(definition): 용어 설명
- 절차(procedure): 단계별 설명
- 예시(example): 구체적 사례
- 설명(explanation): 일반적 설명
- 참조(reference): 다른 섹션 참조
- 목록(list): 항목 나열
- 비교(comparison): 요소 간 비교
- 경고(warning): 주의 사항
- 코드(code): 코드 블록
- 수식(formula): 수학 공식
"""

user_prompt = f"""
다음 문서를 분석하여 의미 단위로 세그먼트를 분할하세요.

<document>
{raw_text}
</document>
"""
```

**2. OpenAI Structured Output 호출**
```python
response = await openai_client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ],
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "SegmentationOutput",
            "schema": Segment.model_json_schema()
        }
    }
)
```

**3. 결과 파싱**
```python
# LLM이 반환한 JSON을 Pydantic 모델로 변환
segments = [Segment(**seg) for seg in response.segments]
```

#### 출력
```python
Stage1Output:
    segments: list[Segment]
    total_segments: int

Segment:
    segment_id: int
    content: str              # 세그먼트 텍스트
    page_number: int
    position_in_page: int
    semantic_type: SemanticType  # definition, procedure, example 등
    key_concepts: list[str]   # 핵심 키워드
    reasoning: str            # LLM의 분류 이유
```

#### 예시
**입력 텍스트:**
```
딥러닝(Deep Learning)은 인공신경망을 기반으로 한 머신러닝의 한 분야로,
여러 층의 은닉층을 통해 데이터의 추상적 특징을 학습한다.

예를 들어, 이미지 분류 문제에서는 첫 번째 층이 엣지를 감지하고,
두 번째 층이 패턴을 인식하며, 최종 층이 객체를 분류한다.
```

**출력 Segments:**
```json
[
  {
    "segment_id": 1,
    "content": "딥러닝(Deep Learning)은 인공신경망을 기반으로...",
    "semantic_type": "definition",
    "key_concepts": ["딥러닝", "인공신경망", "은닉층"],
    "reasoning": "용어의 정의와 특성을 설명하고 있으므로 definition"
  },
  {
    "segment_id": 2,
    "content": "예를 들어, 이미지 분류 문제에서는...",
    "semantic_type": "example",
    "key_concepts": ["이미지 분류", "층별 역할"],
    "reasoning": "'예를 들어'로 시작하며 구체적 사례를 제시하므로 example"
  }
]
```

#### 특징
- **문맥 이해**: LLM이 문맥을 이해하여 의미 단위로 분할
- **다양한 유형 분류**: 11가지 semantic_type으로 분류
- **설명 가능성**: `reasoning` 필드로 분류 근거 제공

---

### Stage 2: 제목 생성 (Headings)

#### 목적
각 세그먼트에 대표 제목을 부여합니다.

#### 입력
```python
Stage2Input:
    document_id: str
    segments: list[Segment]
```

#### 처리 과정

**1. LLM Prompt**
```python
system_prompt = """
각 세그먼트에 적절한 제목을 생성하세요.
제목은 세그먼트의 핵심 내용을 간결하게 표현해야 합니다.

제목 생성 가이드:
- 명확성: 무엇을 다루는지 즉시 이해 가능
- 간결성: 3-7 단어
- 계층성: L1(대분류), L2(중분류), L3(소분류) 중 하나로 분류
- 일관성: 비슷한 레벨의 제목은 유사한 형식 사용
"""
```

**2. 세그먼트별 후보 제목 생성**
```python
for segment in segments:
    response = await llm.generate(
        prompt=f"다음 세그먼트에 적절한 제목 후보 3개를 생성하세요:\n{segment.content}"
    )
    # 후보: ["딥러닝 정의", "딥러닝 개요", "딥러닝이란"]
    # 신뢰도: [0.92, 0.85, 0.78]
```

**3. 최적 제목 선택**
```python
# 신뢰도가 가장 높은 제목 선택
selected_heading = candidate_headings[0]
```

#### 출력
```python
Stage2Output:
    segments_with_headings: list[SegmentWithHeading]

SegmentWithHeading:
    segment: Segment
    candidate_headings: list[str]  # 후보 제목들
    confidence_scores: list[float] # 신뢰도
    selected_heading: str          # 최종 선택 제목
    heading_level: TOCLevel        # 1, 2, 3
```

#### 예시
```json
{
  "segment_id": 1,
  "candidate_headings": ["딥러닝 정의", "딥러닝 개요", "딥러닝이란"],
  "confidence_scores": [0.92, 0.85, 0.78],
  "selected_heading": "딥러닝 정의",
  "heading_level": 2
}
```

#### 특징
- **다양한 후보 제공**: 최대 3개의 제목 후보
- **신뢰도 기반 선택**: 가장 신뢰도 높은 제목 자동 선택
- **계층 분류**: L1/L2/L3 레벨 자동 판단

---

### Stage 3: TOC 정렬 (TOC Alignment)

#### 목적
제목들을 **계층 구조(Tree)**로 정렬합니다.

#### 입력
```python
Stage3Input:
    document_id: str
    segments_with_headings: list[SegmentWithHeading]
```

#### 처리 과정

**1. LLM을 통한 계층 구조 분석**
```python
system_prompt = """
제목들을 분석하여 계층 구조를 만드세요.

규칙:
- L1: 최상위 장/절 (예: "제1장 서론")
- L2: L1의 하위 섹션 (예: "1.1 배경")
- L3: L2의 하위 세부 항목 (예: "1.1.1 연구 동기")

출력:
- 부모-자식 관계를 명확히 정의
- 순서대로 정렬
```

**2. 트리 구조 생성**
```python
# LLM이 반환한 계층 구조를 파싱
toc_nodes = []
for node_data in llm_response.nodes:
    node = TOCNode(
        id=node_data.id,
        level=node_data.level,
        title=node_data.title,
        parent_id=node_data.parent_id,
        children_ids=[],
        segment_ids=node_data.segment_ids
    )
    toc_nodes.append(node)

# 부모-자식 관계 설정
for node in toc_nodes:
    if node.parent_id:
        parent = find_node(node.parent_id)
        parent.children_ids.append(node.id)
```

#### 출력
```python
Stage3Output:
    toc_nodes: list[TOCNode]
    segment_to_toc_mapping: dict[int, str]  # segment_id -> toc_node_id

TOCNode:
    id: str
    level: TOCLevel  # 1, 2, 3
    title: str
    parent_id: str | None
    children_ids: list[str]
    segment_ids: list[int]  # 이 노드에 속한 세그먼트들
```

#### 예시
```json
{
  "toc_nodes": [
    {
      "id": "toc-001",
      "level": 1,
      "title": "제1장 서론",
      "parent_id": null,
      "children_ids": ["toc-002", "toc-003"],
      "segment_ids": [1, 2, 3]
    },
    {
      "id": "toc-002",
      "level": 2,
      "title": "1.1 딥러닝 개요",
      "parent_id": "toc-001",
      "children_ids": [],
      "segment_ids": [1, 2]
    }
  ]
}
```

#### 특징
- **자동 계층화**: LLM이 제목 간 관계를 분석하여 자동으로 트리 구조 생성
- **유연한 구조**: 문서마다 다른 계층 깊이 지원

---

### Stage 4: TOC 정규화 (TOC Normalization)

#### 목적
TOC를 **표준화하고 검증**합니다.

#### 입력
```python
Stage4Input:
    document_id: str
    toc_nodes: list[TOCNode]
    segment_to_toc_mapping: dict
```

#### 처리 과정

**1. 제목 정규화**
```python
# 중복 제거
"제1장 서론" → "서론"
"1. Introduction" → "Introduction"

# 일관성 검사
"1장 배경" vs "제2장 방법론" → "제1장 배경" vs "제2장 방법론"

# 특수 문자 제거
"# 1.1 개요 ##" → "1.1 개요"
```

**2. 구조 검증**
```python
# 체크리스트:
- 모든 L2는 L1 부모를 가져야 함
- 모든 L3는 L2 부모를 가져야 함
- 순서가 올바른지 (1.1 다음에 1.3이 오면 안 됨)
- 순환 참조가 없는지
```

**3. 페이지 범위 계산**
```python
# 세그먼트의 페이지 정보를 기반으로 TOC 노드의 페이지 범위 계산
for node in toc_nodes:
    segments = [seg for seg in all_segments if seg.segment_id in node.segment_ids]
    node.page_start = min(seg.page_number for seg in segments)
    node.page_end = max(seg.page_number for seg in segments)
```

#### 출력
```python
Stage4Output:
    normalized_toc_nodes: list[TOCNode]
    validation_passed: bool
    issues_fixed: list[str]

TOCNode (추가 필드):
    normalized_title: str  # 정규화된 제목
    page_start: int
    page_end: int
```

#### 예시
```json
{
  "normalized_toc_nodes": [
    {
      "id": "toc-001",
      "title": "제1장 서론",
      "normalized_title": "서론",
      "level": 1,
      "page_start": 1,
      "page_end": 15
    }
  ],
  "validation_passed": true,
  "issues_fixed": ["중복 제목 'Overview' 제거", "L2 '1.3'의 부모를 'toc-001'로 설정"]
}
```

#### 특징
- **자동 수정**: 구조 문제를 자동으로 감지하고 수정
- **검증 리포트**: 수정된 내용을 명확히 기록

---

### Stage 5: 청킹 (Chunking)

#### 목적
**이중 청크 시스템** 생성 - Retrieval 청크와 Generation 청크를 동시에 생성합니다.

#### 입력
```python
Stage5Input:
    document_id: str
    normalized_toc_nodes: list[TOCNode]
    segments: list[Segment]
    segment_to_toc_mapping: dict
```

#### 처리 과정

**1. Retrieval Chunk 생성 (검색 최적화)**

목표 토큰 수: **100-300 토큰**

```python
# 전략: 세그먼트를 작게 분할하여 정밀한 검색 지원
for toc_node in toc_nodes:
    segments = get_segments_for_node(toc_node)

    # 세그먼트를 작은 단위로 분할
    for segment in segments:
        if segment.token_count > 300:
            # 문장 단위로 분할
            sentences = split_into_sentences(segment.content)
            current_chunk = ""
            for sentence in sentences:
                if token_count(current_chunk + sentence) <= 300:
                    current_chunk += sentence
                else:
                    # 청크 생성
                    create_retrieval_chunk(current_chunk)
                    current_chunk = sentence
        else:
            create_retrieval_chunk(segment.content)
```

**Retrieval Chunk 구조:**
```python
RetrievalChunk:
    id: str
    document_id: str
    toc_node_id: str
    content: str              # 100-300 토큰
    semantic_type: SemanticType
    key_concepts: list[str]   # 검색 키워드
    page_numbers: list[int]
    sequence_in_document: int
    sequence_in_toc_node: int
    generation_chunk_id: str  # 연결된 Generation 청크
    token_count: int
```

**2. Generation Chunk 생성 (답변 생성 최적화)**

목표 토큰 수: **500-1500 토큰**

```python
# 전략: 여러 세그먼트를 합쳐서 충분한 컨텍스트 제공
for toc_node in toc_nodes:
    segments = get_segments_for_node(toc_node)

    # 세그먼트들을 합쳐서 큰 청크 생성
    current_chunk_content = ""
    for segment in segments:
        if token_count(current_chunk_content + segment.content) <= 1500:
            current_chunk_content += "\n\n" + segment.content
        else:
            # Generation 청크 생성
            chunk = create_generation_chunk(
                content=current_chunk_content,
                summary=generate_summary(current_chunk_content),
                context_path=build_toc_path(toc_node),
                parent_summary=get_parent_summary(toc_node)
            )
            current_chunk_content = segment.content
```

**Generation Chunk 구조:**
```python
GenerationChunk:
    id: str
    document_id: str
    toc_node_id: str
    content: str              # 500-1500 토큰 (상세 내용)
    summary: str              # LLM 생성 요약
    semantic_type: SemanticType
    key_concepts: list[str]
    context_path: str         # "제1장 서론 > 1.1 딥러닝 개요"
    parent_summary: str       # 상위 섹션 요약
    page_numbers: list[int]
    sequence_in_document: int
    retrieval_chunk_ids: list[str]  # 연결된 Retrieval 청크들
    entity_ids: list[str]     # 연결된 테이블/이미지
    token_count: int
```

**3. 청크 연결**
```python
# Retrieval 청크와 Generation 청크를 연결
for retrieval_chunk in retrieval_chunks:
    # 같은 TOC 노드 내의 Generation 청크 찾기
    gen_chunk = find_generation_chunk_for_toc(retrieval_chunk.toc_node_id)
    retrieval_chunk.generation_chunk_id = gen_chunk.id
    gen_chunk.retrieval_chunk_ids.append(retrieval_chunk.id)
```

#### 출력
```python
Stage5Output:
    retrieval_chunks: list[RetrievalChunk]
    generation_chunks: list[GenerationChunk]
    total_retrieval: int
    total_generation: int
    avg_retrieval_tokens: float
    avg_generation_tokens: float
```

#### 예시

**Retrieval Chunk:**
```json
{
  "id": "rc-001",
  "content": "딥러닝은 인공신경망 기반의 머신러닝으로, 여러 은닉층을 통해 데이터의 추상적 특징을 학습한다.",
  "semantic_type": "definition",
  "key_concepts": ["딥러닝", "인공신경망", "은닉층"],
  "token_count": 85,
  "generation_chunk_id": "gc-001"
}
```

**Generation Chunk:**
```json
{
  "id": "gc-001",
  "content": "딥러닝(Deep Learning)은 인공신경망을 기반으로 한 머신러닝의 한 분야입니다. 여러 층의 은닉층(hidden layer)을 통해 데이터의 추상적 특징을 학습하며...(상세 설명 500-1500 토큰)",
  "summary": "딥러닝의 정의와 전통 머신러닝과의 차이점을 설명",
  "context_path": "제1장 서론 > 1.1 딥러닝 개요",
  "parent_summary": "1장에서는 딥러닝의 기본 개념과 역사를 다룬다",
  "token_count": 450,
  "retrieval_chunk_ids": ["rc-001", "rc-002", "rc-003"]
}
```

#### 특징
- **이중 최적화**: 검색과 생성을 각각 최적화
- **컨텍스트 보존**: Generation 청크는 충분한 문맥 제공
- **연결 관계**: 청크 간 관계를 명확히 저장

---

### Stage 5b: 엔티티 추출 (Entities)

#### 목적
테이블, 이미지, 차트 등 **비텍스트 요소**를 추출하고 구조화합니다.

#### 입력
```python
Stage5bInput:
    document_id: str
    tables: list[ExtractedTable]  # Stage 0에서 추출된 테이블
    images: list[ExtractedImage]  # Stage 0에서 추출된 이미지
    toc_nodes: list[TOCNode]
    page_to_toc_mapping: dict[int, str]  # 페이지 → TOC 노드 매핑
```

#### 처리 과정

**1. 테이블 엔티티 생성**
```python
for table in tables:
    # 테이블이 속한 TOC 노드 찾기
    toc_node_id = page_to_toc_mapping.get(table.page_number)

    # 구조화된 JSON 생성
    canonical_json = {
        "rows": table.rows,
        "cols": table.cols,
        "headers": table.headers,
        "cells": [cell.to_dict() for cell in table.cells]
    }

    # 마크다운 변환
    markdown = convert_table_to_markdown(table)

    # 주변 텍스트 추출 (컨텍스트)
    surrounding_text = extract_surrounding_text(table.page_number, table.bbox)

    entity = Entity(
        id=f"ent-table-{table.id}",
        entity_type=EntityType.TABLE,
        page_number=table.page_number,
        canonical_json=canonical_json,
        markdown=markdown,
        surrounding_context=surrounding_text,
        toc_node_id=toc_node_id
    )
```

**2. 이미지 엔티티 생성**
```python
for image in images:
    toc_node_id = page_to_toc_mapping.get(image.page_number)

    entity = Entity(
        id=f"ent-image-{image.id}",
        entity_type=EntityType.IMAGE,
        page_number=image.page_number,
        image_path=image.file_path,
        image_base64=image.base64_data,
        bbox=image.bbox,
        caption=extract_caption(image.page_number, image.bbox),
        surrounding_context=extract_surrounding_text(image.page_number, image.bbox),
        toc_node_id=toc_node_id,
        vision_processed=False  # Stage 6에서 처리
    )
```

**3. Generation Chunk와 연결**
```python
# 같은 TOC 노드의 Generation 청크와 엔티티 연결
for entity in entities:
    gen_chunks = find_generation_chunks_for_toc(entity.toc_node_id)
    for chunk in gen_chunks:
        chunk.entity_ids.append(entity.id)
    entity.generation_chunk_id = gen_chunks[0].id if gen_chunks else None
```

#### 출력
```python
Stage5bOutput:
    entities: list[Entity]
    total_tables: int
    total_images: int
    total_diagrams: int
    total_charts: int

Entity:
    id: str
    document_id: str
    entity_type: EntityType  # table, image, diagram, chart, equation
    page_number: int
    sequence_in_page: int
    bbox: BoundingBox | None
    canonical_json: dict | None      # 테이블의 구조화된 데이터
    markdown: str | None             # 마크다운 표현
    image_path: str | None           # 이미지 파일 경로
    image_base64: str | None         # Base64 인코딩 이미지
    vision_description: str | None   # Stage 6에서 채워짐
    vision_processed: bool
    caption: str | None
    surrounding_context: str | None
    toc_node_id: str | None
    generation_chunk_id: str | None
```

#### 예시
```json
{
  "id": "ent-table-001",
  "entity_type": "table",
  "page_number": 12,
  "canonical_json": {
    "rows": 4,
    "cols": 3,
    "headers": ["모델", "파라미터", "정확도"],
    "cells": [
      {"row": 1, "col": 0, "content": "BERT"},
      {"row": 1, "col": 1, "content": "110M"},
      {"row": 1, "col": 2, "content": "94.5%"}
    ]
  },
  "markdown": "| 모델 | 파라미터 | 정확도 |\n|---|---|---|\n| BERT | 110M | 94.5% |",
  "caption": "표 2.1 주요 모델 비교",
  "surrounding_context": "다음 표는 주요 언어 모델의 성능을 비교한 것이다.",
  "toc_node_id": "toc-005"
}
```

#### 특징
- **구조 보존**: 테이블을 JSON, 마크다운 등 다양한 형식으로 저장
- **컨텍스트 추출**: 주변 텍스트를 함께 저장하여 검색 품질 향상
- **TOC 연결**: 엔티티가 어느 섹션에 속하는지 명확히 저장

---

### Stage 6: 비전 처리 (Vision)

#### 목적
이미지, 다이어그램, 차트 등을 **Vision API로 분석**하여 텍스트 설명을 생성합니다.

#### 입력
```python
Stage6Input:
    document_id: str
    entities: list[Entity]  # Stage 5b에서 생성된 엔티티
    skip_vision: bool       # Vision 처리 건너뛰기 옵션
```

#### 처리 과정

**1. Vision API 호출**
```python
for entity in entities:
    # 이미지 엔티티만 처리
    if entity.entity_type not in [EntityType.IMAGE, EntityType.DIAGRAM, EntityType.CHART]:
        continue

    # Vision API 호출
    description = await vision_client.analyze_image(
        image_path=entity.image_path,
        prompt="""
        이 이미지를 분석하여 다음을 설명하세요:
        1. 주요 내용
        2. 핵심 요소
        3. 시각적 특징
        4. 전달하려는 메시지

        검색 가능하도록 상세히 설명하세요.
        """
    )

    entity.vision_description = description
    entity.vision_processed = True
```

**2. 설명을 Retrieval Chunk로 추가**
```python
# Vision 설명을 검색 가능한 청크로 변환
for entity in entities:
    if entity.vision_description:
        # 새로운 Retrieval Chunk 생성
        vision_chunk = RetrievalChunk(
            id=f"rc-vision-{entity.id}",
            document_id=entity.document_id,
            toc_node_id=entity.toc_node_id,
            content=f"[이미지 설명] {entity.vision_description}",
            semantic_type=SemanticType.EXPLANATION,
            key_concepts=extract_keywords(entity.vision_description),
            page_numbers=[entity.page_number],
            generation_chunk_id=entity.generation_chunk_id
        )
```

#### 출력
```python
Stage6Output:
    processed_entities: list[Entity]  # vision_description이 채워진 엔티티
    total_processed: int
    total_skipped: int
    vision_chunks_created: int
```

#### 예시

**입력 이미지:**
```
[Neural Network Architecture 다이어그램]
Input Layer → Hidden Layers → Output Layer
```

**Vision API 출력:**
```json
{
  "entity_id": "ent-image-005",
  "vision_description": "이 다이어그램은 심층 신경망의 구조를 보여줍니다.
  입력 레이어에서 데이터를 받아 여러 개의 은닉층을 거쳐 출력 레이어로 전달되는
  정보 흐름을 시각화하고 있습니다. 각 층은 다수의 뉴런(노드)으로 구성되어 있으며,
  화살표는 층 간 연결을 나타냅니다. 이는 전형적인 피드포워드 신경망 구조입니다.",
  "vision_processed": true
}
```

#### 특징
- **선택적 처리**: `skip_vision=true`로 Vision 처리 생략 가능 (비용 절감)
- **검색 통합**: Vision 설명을 별도 청크로 생성하여 검색 가능
- **컨텍스트 증강**: 이미지 내용을 텍스트화하여 RAG 성능 향상

---

### Stage 7: 임베딩 (Embedding)

#### 목적
Retrieval Chunk를 **벡터로 변환**하여 검색 가능하게 만듭니다.

#### 입력
```python
Stage7Input:
    document_id: str
    retrieval_chunks: list[RetrievalChunk]
```

#### 처리 과정

**1. OpenAI Embedding API 호출**
```python
# 배치 임베딩 (최대 2048개씩)
texts = [chunk.content for chunk in retrieval_chunks]

response = await openai.embeddings.create(
    model="text-embedding-3-small",
    input=texts
)

# 결과를 청크에 저장
for chunk, embedding_data in zip(retrieval_chunks, response.data):
    chunk.embedding = embedding_data.embedding  # list[float] (1536차원)
    chunk.embedding_model = "text-embedding-3-small"
```

**2. MongoDB 저장**
```python
# Retrieval Chunk의 embedding 필드 업데이트
for chunk in retrieval_chunks:
    await chunk_repo.update_embedding(
        chunk_id=chunk.id,
        embedding=chunk.embedding,
        embedding_model=chunk.embedding_model
    )
```

#### 출력
```python
Stage7Output:
    embedded_chunks: list[RetrievalChunk]  # embedding이 채워진 청크
    total_embedded: int
    embedding_model: str
    embedding_dimensions: int  # 1536
```

#### 예시
```json
{
  "chunk_id": "rc-001",
  "content": "딥러닝은 인공신경망 기반의 머신러닝으로...",
  "embedding": [0.023, -0.045, 0.012, ..., 0.089],  // 1536개의 float
  "embedding_model": "text-embedding-3-small"
}
```

#### 특징
- **고품질 임베딩**: OpenAI의 text-embedding-3-small 사용 (최신 모델)
- **배치 처리**: 한 번에 여러 청크를 임베딩하여 API 호출 최소화
- **차원 고정**: 1536차원으로 고정되어 일관된 검색 가능

---

## 5. Dual-Chunk System

### 5.1 이중 청크 시스템의 필요성

#### 문제: 단일 청크의 딜레마
```
짧은 청크 (100-200 토큰):
  ✓ 검색 정밀도 높음
  ✗ 답변 생성 시 컨텍스트 부족

긴 청크 (1000+ 토큰):
  ✓ 답변 생성에 충분한 컨텍스트
  ✗ 검색 정밀도 낮음 (노이즈 많음)
```

#### 해결책: Dual-Chunk
```
Retrieval Chunk (100-300 토큰):
  - 임베딩 생성
  - 벡터 검색에 사용
  - 정밀한 매칭

Generation Chunk (500-1500 토큰):
  - LLM에 전달
  - 답변 생성에 사용
  - 충분한 컨텍스트
```

### 5.2 검색 흐름

```
사용자 쿼리: "딥러닝에서 과적합을 방지하는 방법은?"
       ↓
[1] 쿼리 임베딩 생성
    embedding = embed("딥러닝에서 과적합을 방지하는 방법은?")
       ↓
[2] Retrieval Chunk 벡터 검색
    top_retrieval_chunks = vector_search(embedding, top_k=10)
    # 결과: rc-045 (score: 0.89), rc-102 (score: 0.82), ...
       ↓
[3] Generation Chunk 로드
    for rc in top_retrieval_chunks:
        gc = load_generation_chunk(rc.generation_chunk_id)
        results.append({
            "retrieval": rc,
            "generation": gc,
            "score": rc.score
        })
       ↓
[4] LLM에 전달하여 답변 생성
    context = "\n\n".join([r.generation.content for r in results])
    answer = llm.generate(
        prompt=f"질문: {query}\n\n컨텍스트:\n{context}\n\n답변:"
    )
```

### 5.3 장점

| 측면 | 이점 |
|-----|------|
| **검색 정밀도** | Retrieval 청크가 짧아서 정확한 매칭 가능 |
| **답변 품질** | Generation 청크가 길어서 충분한 컨텍스트 제공 |
| **비용 효율** | 임베딩은 짧은 청크만 생성 (비용 절감) |
| **유연성** | 검색과 생성을 독립적으로 최적화 가능 |

### 5.4 실제 예시

**쿼리:** "딥러닝에서 과적합을 방지하는 방법은?"

**검색된 Retrieval Chunk:**
```json
{
  "id": "rc-045",
  "content": "드롭아웃은 학습 시 무작위로 뉴런을 제거하여 과적합을 방지하는 정규화 기법이다.",
  "score": 0.89
}
```

**연결된 Generation Chunk:**
```json
{
  "id": "gc-015",
  "content": "과적합을 방지하기 위한 대표적인 정규화 기법으로 드롭아웃(Dropout)이 있습니다.

  드롭아웃은 학습 과정에서 무작위로 뉴런을 비활성화하여 네트워크가 특정 뉴런에 과도하게
  의존하는 것을 방지합니다. 일반적으로 0.2-0.5의 비율로 뉴런을 제거하며, 이는 앙상블
  효과를 내어 모델의 일반화 성능을 향상시킵니다.

  또한 조기 종료(Early Stopping), L1/L2 정규화, 배치 정규화(Batch Normalization)
  등도 효과적인 과적합 방지 기법입니다...",
  "context_path": "제3장 학습 최적화 > 3.2 정규화 기법"
}
```

**LLM 답변 생성:**
```
질문: 딥러닝에서 과적합을 방지하는 방법은?

컨텍스트:
[gc-015의 상세 내용]

답변:
딥러닝에서 과적합을 방지하는 주요 방법은 다음과 같습니다:

1. 드롭아웃(Dropout): 학습 시 무작위로 뉴런을 비활성화하여...
2. 조기 종료(Early Stopping): 검증 손실이 증가하기 시작하면...
3. L1/L2 정규화: 가중치에 패널티를 부여하여...

특히 드롭아웃은 0.2-0.5 비율로 설정하면 효과적이며...
```

---

## 6. 상태 관리 및 재개 메커니즘

### 6.1 상태 저장 구조

```
pipeline_state/
├── {document_id}/
│   ├── metadata.json           # 문서 메타정보
│   ├── current_state.json      # 현재 진행 상태
│   ├── stage0_output.json      # Stage 0 결과
│   ├── stage1_output.json      # Stage 1 결과
│   ├── stage2_output.json      # Stage 2 결과
│   ├── stage3_output.json      # Stage 3 결과
│   ├── stage4_output.json      # Stage 4 결과
│   ├── stage5_output.json      # Stage 5 결과
│   ├── stage5b_output.json     # Stage 5b 결과
│   ├── stage6_output.json      # Stage 6 결과
│   └── stage7_output.json      # Stage 7 결과
```

### 6.2 PipelineState 모델

```python
PipelineState:
    id: str
    document_id: str
    stages: dict[str, StageResult]  # 각 Stage의 실행 결과
    current_stage: PipelineStage | None
    last_completed_stage: PipelineStage | None
    stage_outputs: dict[str, str]   # Stage별 출력 파일 경로
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    total_duration_seconds: float | None
    config_snapshot: dict           # 실행 시 설정 (모델, 파라미터 등)

StageResult:
    stage: PipelineStage
    status: StageStatus  # pending, running, completed, failed, skipped
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: float | None
    error_message: str | None
    output_summary: dict | None
```

### 6.3 재개 메커니즘

**시나리오: Stage 3에서 실패 후 재시작**

```python
# 1. 상태 로드
state = await state_manager.load_state(document_id)

# 2. 재개 지점 결정
resume_point = await state_manager.get_resume_point(document_id)
# stage3_toc_alignment (실패한 Stage)

# 3. 이전 Stage 결과 로드
stage0_output = load_json(f"pipeline_state/{doc_id}/stage0_output.json")
stage1_output = load_json(f"pipeline_state/{doc_id}/stage1_output.json")
stage2_output = load_json(f"pipeline_state/{doc_id}/stage2_output.json")

# 4. Stage 3부터 재실행
for stage in [Stage3, Stage4, Stage5, Stage5b, Stage6, Stage7]:
    result = await stage.run(previous_outputs)
    await state_manager.save_stage_output(document_id, stage, result)
```

### 6.4 장점

- **내결함성**: 중간에 실패해도 처음부터 다시 시작할 필요 없음
- **비용 절감**: 이미 완료된 Stage의 LLM 호출을 반복하지 않음
- **디버깅 용이**: 각 Stage의 중간 결과를 확인 가능
- **병렬 실험**: 다양한 파라미터로 특정 Stage만 재실행 가능

---

## 7. LLM 통합 전략

### 7.1 LLM 호출 위치

| Stage | LLM 호출 | 목적 | 입력 | 출력 |
|-------|---------|------|------|------|
| **Stage 0** | ✗ | PDF 추출 | PDF 파일 | Raw Text |
| **Stage 1** | ✓ | 의미 분할 | Raw Text | Segments |
| **Stage 2** | ✓ | 제목 생성 | Segments | Headings |
| **Stage 3** | ✓ | TOC 정렬 | Headings | TOC Tree |
| **Stage 4** | ✓ | TOC 정규화 | TOC Tree | Normalized TOC |
| **Stage 5** | ✓ | 청킹 | TOC + Segments | Dual Chunks |
| **Stage 5b** | ✗ | 엔티티 추출 | PDF | Entities |
| **Stage 6** | ✓ | 이미지 분석 | Images | Descriptions |
| **Stage 7** | ✓ | 임베딩 | Chunks | Vectors |

**총 LLM 호출:**
- **문서당**: 5회 (Stage 1, 2, 3, 4, 5)
- **이미지당**: 1회 (Stage 6)
- **청크당**: 1회 (Stage 7 - 임베딩)

### 7.2 Structured Output 전략

모든 LLM 호출은 **OpenAI Structured Output**을 사용하여 안정적인 JSON 응답을 보장합니다.

```python
# Pydantic 스키마 정의
class SegmentationOutput(BaseModel):
    segments: list[Segment]
    total_segments: int

# LLM 호출 시 스키마 강제
response = await openai.chat.completions.create(
    model="gpt-4o-mini",
    messages=[...],
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "SegmentationOutput",
            "schema": SegmentationOutput.model_json_schema()
        }
    }
)

# 결과는 항상 유효한 JSON
output = SegmentationOutput(**json.loads(response.choices[0].message.content))
```

### 7.3 비용 최적화

**모델 선택 전략:**
```python
# Stage 1-5: gpt-4o-mini (비용 효율적)
# - 구조화 작업에 충분히 강력
# - gpt-4o 대비 1/10 비용

# Stage 6: gpt-4o-vision (정확도 중요)
# - 이미지 분석은 고품질 모델 필요
# - 선택적 처리로 비용 관리

# Stage 7: text-embedding-3-small
# - 최신 임베딩 모델
# - 저렴하고 빠름
```

**예상 비용 (150페이지 문서):**
```
Stage 1-5 (gpt-4o-mini):
  - 입력: ~50,000 토큰
  - 출력: ~10,000 토큰
  - 비용: ~$0.02

Stage 6 (gpt-4o-vision):
  - 이미지 30개
  - 비용: ~$0.15

Stage 7 (embedding):
  - 청크 250개
  - 비용: ~$0.01

총: ~$0.18 per document
```

---

## 8. 데이터 모델

### 8.1 핵심 컬렉션

MongoDB에 저장되는 주요 컬렉션:

```python
# 1. documents
Document:
    id: str
    filename: str
    original_filename: str
    upload_timestamp: datetime
    status: DocumentStatus  # uploaded, processing, completed, failed
    metadata: DocumentMetadata
    raw_text: str
    raw_text_by_page: list[str]
    current_stage: PipelineStage | None
    error_message: str | None

# 2. toc_nodes
TOCNode:
    id: str
    document_id: str
    level: TOCLevel  # 1, 2, 3
    title: str
    normalized_title: str
    sequence_number: int
    parent_id: str | None
    children_ids: list[str]
    page_start: int | None
    page_end: int | None
    retrieval_chunk_ids: list[str]
    generation_chunk_ids: list[str]
    entity_ids: list[str]

# 3. retrieval_chunks
RetrievalChunk:
    id: str
    document_id: str
    toc_node_id: str
    content: str  # 100-300 토큰
    semantic_type: SemanticType
    key_concepts: list[str]
    page_numbers: list[int]
    generation_chunk_id: str
    embedding: list[float]  # 1536차원
    embedding_model: str
    token_count: int

# 4. generation_chunks
GenerationChunk:
    id: str
    document_id: str
    toc_node_id: str
    content: str  # 500-1500 토큰
    summary: str
    semantic_type: SemanticType
    key_concepts: list[str]
    context_path: str
    parent_summary: str | None
    page_numbers: list[int]
    retrieval_chunk_ids: list[str]
    entity_ids: list[str]
    token_count: int

# 5. entities
Entity:
    id: str
    document_id: str
    entity_type: EntityType  # table, image, diagram, chart
    page_number: int
    bbox: BoundingBox | None
    canonical_json: dict | None
    markdown: str | None
    image_path: str | None
    vision_description: str | None
    caption: str | None
    surrounding_context: str | None
    toc_node_id: str | None
    generation_chunk_id: str | None
```

### 8.2 관계 다이어그램

```
Document (1)
    │
    ├─── TOCNode (N)
    │       │
    │       ├─── RetrievalChunk (N)
    │       │       │
    │       │       └─── embedding: vector
    │       │
    │       ├─── GenerationChunk (N)
    │       │       │
    │       │       └─── retrieval_chunk_ids
    │       │
    │       └─── Entity (N)
    │               │
    │               └─── vision_description
    │
    └─── PipelineState (1)
            │
            └─── StageResult (8)
```

---

## 9. 장점과 단점

### 9.1 장점

#### ✅ 고품질 구조화
- **의미 기반 분할**: LLM이 문맥을 이해하여 정확히 분할
- **계층 구조**: 자동으로 TOC 트리 생성, 검색 시 네비게이션 제공
- **이중 청크**: 검색과 생성을 각각 최적화

#### ✅ 안정성 및 재개 가능
- **Checkpoint 시스템**: 각 Stage마다 결과 저장
- **Resume 지원**: 실패 시 중단 지점부터 재시작
- **오류 추적**: 상세한 로그 및 상태 관리

#### ✅ 비용 효율성
- **모델 선택**: gpt-4o-mini로 대부분 처리 (저렴)
- **선택적 Vision**: 이미지 분석 생략 가능
- **재실행 방지**: Resume으로 중복 LLM 호출 제거

#### ✅ 확장성
- **비동기 처리**: FastAPI + motor로 고성능
- **배치 임베딩**: 여러 청크를 한 번에 처리
- **MongoDB**: 대용량 문서 및 벡터 저장 지원

#### ✅ 검색 품질
- **Dual-Chunk**: 정밀 검색 + 풍부한 컨텍스트
- **Semantic Type**: 콘텐츠 유형별 필터링 가능
- **엔티티 통합**: 테이블/이미지 내용도 검색 가능

### 9.2 단점

#### ❌ 복잡성
- **8단계 파이프라인**: 초기 학습 곡선 높음
- **다양한 모델**: Document, TOCNode, Chunk, Entity 등 관리 복잡
- **상태 관리**: PipelineState 로직이 복잡

#### ❌ 처리 시간
- **순차 실행**: Stage가 순차적으로 실행되어 시간 소요
- **LLM 대기**: Stage 1-5에서 LLM 응답 대기 필요
- **150페이지 문서**: 약 5-10분 소요 (LLM 속도에 따라 변동)

#### ❌ LLM 의존성
- **품질 변동**: LLM 출력이 일관되지 않을 수 있음
- **비용 누적**: 대량 문서 처리 시 비용 증가
- **언어 제한**: 한/영 외 언어는 품질 저하 가능

#### ❌ 스캔 PDF 지원 부족
- **pytesseract 미구현**: 현재 스캔 PDF OCR이 TODO 상태
- **이미지 품질**: 저품질 스캔 문서는 텍스트 추출 실패 가능

#### ❌ 벡터 검색 한계
- **In-Memory 검색**: MongoDB에서 전체 청크를 로드하여 코사인 유사도 계산
- **성능 저하**: 청크 수가 많아지면 검색 속도 느려짐
- **해결책**: Atlas Vector Search로 마이그레이션 필요

### 9.3 개선 가능 영역

| 영역 | 현재 상태 | 개선 방안 |
|-----|----------|----------|
| **스캔 PDF** | pytesseract TODO | Tesseract OCR 통합 구현 |
| **벡터 검색** | Python 코사인 유사도 | MongoDB Atlas Vector Search 사용 |
| **병렬 처리** | 순차 실행 | Stage 1-2, 5-5b 등 병렬화 |
| **다국어** | 한/영 중심 | langdetect + 다국어 프롬프트 확장 |
| **캐싱** | 없음 | LLM 응답 캐싱으로 비용 절감 |

---

## 10. 특징 및 차별점

### 10.1 핵심 특징

#### 🎯 1. Dual-Chunk System (독창성)
대부분의 RAG 시스템은 단일 청크를 사용하지만, 이 시스템은:
- **Retrieval Chunk**: 검색 정밀도 최적화 (100-300 토큰)
- **Generation Chunk**: 답변 품질 최적화 (500-1500 토큰)
- **1:N 관계**: 하나의 Generation 청크가 여러 Retrieval 청크와 연결

**차별점:** 검색과 생성을 분리하여 각각 최적화

#### 🎯 2. LLM 기반 구조화 (고급 분석)
단순한 텍스트 추출이 아닌, LLM을 통한 의미 분석:
- **Semantic Type**: 정의, 절차, 예시 등 11가지 유형 자동 분류
- **Key Concepts**: 핵심 키워드 자동 추출
- **TOC 자동 생성**: 제목을 분석하여 계층 구조 자동 생성

**차별점:** 단순 키워드 매칭이 아닌 의미 기반 검색 지원

#### 🎯 3. Resume 기능 (안정성)
각 Stage를 독립적으로 저장하여:
- **중단 후 재개**: 실패 지점부터 재시작
- **비용 절감**: 이미 완료된 LLM 호출 반복 안 함
- **디버깅**: 각 Stage 출력을 개별 확인 가능

**차별점:** 대부분의 파이프라인은 실패 시 처음부터 재시작

#### 🎯 4. 엔티티 통합 (멀티모달)
텍스트뿐만 아니라:
- **테이블**: 구조화된 JSON + 마크다운
- **이미지**: Vision API로 분석 후 텍스트화
- **차트/다이어그램**: 시각 정보를 검색 가능하게 변환

**차별점:** 테이블과 이미지도 검색 대상에 포함

#### 🎯 5. 계층적 컨텍스트 (Context Augmentation)
각 청크에 풍부한 메타데이터:
- **context_path**: "제1장 서론 > 1.1 딥러닝 개요"
- **parent_summary**: 상위 섹션 요약
- **surrounding_context**: 주변 텍스트

**차별점:** 검색 결과에 문서 구조 정보 제공

### 10.2 경쟁 시스템 비교

| 기능 | 이 시스템 | LlamaIndex | LangChain | Unstructured.io |
|-----|----------|-----------|-----------|----------------|
| **Dual-Chunk** | ✅ | ✗ | ✗ | ✗ |
| **LLM 구조화** | ✅ | 부분적 | 부분적 | ✗ |
| **Resume 지원** | ✅ | ✗ | ✗ | ✗ |
| **TOC 자동 생성** | ✅ | ✗ | ✗ | ✗ |
| **Vision 통합** | ✅ | ✅ | ✅ | 부분적 |
| **엔티티 추출** | ✅ (구조화) | ✅ | ✅ | ✅ |

### 10.3 사용 사례

**✅ 적합한 경우:**
- 기술 문서, 매뉴얼, 논문 등 구조화된 문서
- 테이블과 이미지가 많은 문서
- 고품질 검색 및 답변 생성이 필요한 경우
- 대용량 문서 (100+ 페이지)

**❌ 부적합한 경우:**
- 짧은 문서 (<10 페이지) - 오버엔지니어링
- 실시간 처리 필요 - 5-10분 소요
- 저비용 필수 - LLM 호출 비용 발생
- 스캔 품질이 낮은 문서 - OCR 정확도 저하

---

## 결론

이 OCR 프로세스는 **8단계 파이프라인**을 통해 PDF 문서를 고품질 RAG 시스템용 데이터로 변환합니다.

**핵심 강점:**
1. **Dual-Chunk System**: 검색과 생성을 독립적으로 최적화
2. **LLM 기반 구조화**: 의미 기반 분할 및 TOC 자동 생성
3. **Resume 지원**: 안정적이고 비용 효율적인 파이프라인
4. **멀티모달 통합**: 텍스트, 테이블, 이미지 모두 검색 가능

**향후 개선 방향:**
- pytesseract OCR 통합 (스캔 PDF 지원)
- MongoDB Atlas Vector Search 전환 (성능 향상)
- Stage 병렬화 (처리 시간 단축)
- 다국어 프롬프트 확장

이 시스템은 **고품질 RAG 시스템**을 구축하려는 프로젝트에 적합하며, 특히 **기술 문서 분석**에 탁월한 성능을 발휘합니다.
