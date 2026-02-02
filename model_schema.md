# RAG VectorDB PDF Pipeline - 모델 스키마 문서

이 문서는 PDF 문서를 처리하여 검색 가능한 벡터 데이터베이스를 구축하는 파이프라인의 데이터 모델을 설명합니다.

---

## 목차

1. [프로젝트 개요](#프로젝트-개요)
2. [열거형 (Enums)](#열거형-enums)
3. [문서 모델](#문서-모델)
4. [TOC (목차) 모델](#toc-목차-모델)
5. [세그먼트 모델](#세그먼트-모델)
6. [청크 모델 (Dual-Chunk System)](#청크-모델-dual-chunk-system)
7. [엔티티 모델](#엔티티-모델)
8. [파이프라인 상태 모델](#파이프라인-상태-모델)
9. [검색 모델](#검색-모델)
10. [LLM 출력 스키마](#llm-출력-스키마)
11. [API 응답 모델](#api-응답-모델)

---

## 프로젝트 개요

이 시스템은 PDF 문서를 다음 8단계 파이프라인으로 처리합니다:

```
Stage 0: 텍스트 추출 (PDF → 원시 텍스트)
    ↓
Stage 1: 세그멘테이션 (텍스트 → 의미 단위 분리)
    ↓
Stage 2: 제목 생성 (세그먼트에 후보 제목 부여)
    ↓
Stage 3: TOC 정렬 (제목을 계층 구조로 정렬)
    ↓
Stage 4: TOC 정규화 (제목 표준화 및 검증)
    ↓
Stage 5: 청킹 (Retrieval + Generation 이중 청크 생성)
    ↓
Stage 5b: 엔티티 추출 (테이블, 이미지, 차트 등)
    ↓
Stage 6: 비전 처리 (이미지/다이어그램 분석)
    ↓
Stage 7: 임베딩 (벡터 변환 및 저장)
```

---

## 열거형 (Enums)

### DocumentStatus
문서의 전체 처리 상태를 나타냅니다.

| 값 | 설명 |
|---|---|
| `uploaded` | 문서가 업로드되었으나 처리 시작 전 |
| `processing` | 파이프라인 처리 중 |
| `completed` | 모든 단계 완료 |
| `failed` | 처리 중 오류 발생 |
| `partial` | 일부 단계만 완료 (중단됨) |

### PipelineStage
파이프라인의 각 처리 단계입니다.

| 값 | 설명 |
|---|---|
| `stage_0_extraction` | PDF에서 텍스트 추출 |
| `stage_1_segmentation` | 텍스트를 의미 단위로 분리 |
| `stage_2_headings` | 세그먼트에 제목 후보 생성 |
| `stage_3_toc_alignment` | 제목을 계층 구조로 정렬 |
| `stage_4_toc_normalization` | 제목 표준화 및 검증 |
| `stage_5_chunking` | 이중 청크 시스템 생성 |
| `stage_5b_entities` | 테이블/이미지 등 엔티티 추출 |
| `stage_6_vision` | 이미지 분석 (Vision API) |
| `stage_7_embedding` | 벡터 임베딩 생성 |

### StageStatus
개별 단계의 실행 상태입니다.

| 값 | 설명 |
|---|---|
| `pending` | 대기 중 (아직 실행 안 됨) |
| `running` | 현재 실행 중 |
| `completed` | 성공적으로 완료 |
| `failed` | 실패 |
| `skipped` | 건너뜀 (해당 없음) |

### SemanticType
콘텐츠의 의미적 유형입니다. 검색 및 답변 생성 시 활용됩니다.

| 값 | 설명 | 예시 |
|---|---|---|
| `definition` | 용어 정의 | "머신러닝이란 데이터로부터 학습하는..." |
| `procedure` | 절차/단계 설명 | "1단계: 데이터 수집, 2단계: 전처리..." |
| `example` | 예시 | "예를 들어, 고양이 이미지를 분류할 때..." |
| `explanation` | 일반적 설명 | "이 알고리즘은 효율적으로 동작한다..." |
| `reference` | 참조 정보 | "자세한 내용은 3장을 참고하세요" |
| `list` | 목록 | "주요 특징: - 빠른 속도 - 높은 정확도" |
| `comparison` | 비교 | "A방식은 B방식보다 2배 빠르다" |
| `warning` | 주의/경고 | "주의: 이 설정은 되돌릴 수 없습니다" |
| `note` | 참고 사항 | "참고: Python 3.8 이상 필요" |
| `code` | 코드 블록 | "```python\nprint('hello')```" |
| `formula` | 수식 | "E = mc²" |

### EntityType
추출된 엔티티의 유형입니다.

| 값 | 설명 |
|---|---|
| `table` | 표 |
| `image` | 이미지 |
| `diagram` | 다이어그램/흐름도 |
| `chart` | 차트/그래프 |
| `equation` | 수식 |

### TOCLevel
목차의 계층 수준입니다.

| 값 | 설명 | 예시 |
|---|---|---|
| `1` | 대분류 (L1) | "1. 서론" |
| `2` | 중분류 (L2) | "1.1 배경" |
| `3` | 소분류 (L3) | "1.1.1 연구 동기" |

### Language
문서에서 감지된 언어입니다.

| 값 | 설명 |
|---|---|
| `ko` | 한국어 |
| `en` | 영어 |
| `mixed` | 혼합 (한영 병기) |
| `unknown` | 감지 불가 |

---

## 문서 모델

### DocumentMetadata
PDF에서 추출한 메타데이터입니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `title` | `str?` | 문서 제목 |
| `author` | `str?` | 저자 |
| `subject` | `str?` | 주제 |
| `creator` | `str?` | 생성 도구 (예: "Microsoft Word") |
| `page_count` | `int` | 총 페이지 수 |
| `file_size_bytes` | `int` | 파일 크기 (바이트) |
| `detected_language` | `Language` | 감지된 언어 |

**예시:**
```json
{
  "title": "딥러닝 기초 가이드",
  "author": "홍길동",
  "subject": "인공지능",
  "creator": "Microsoft Word 2021",
  "page_count": 150,
  "file_size_bytes": 5242880,
  "detected_language": "ko"
}
```

### Document
시스템에서 관리하는 문서의 루트 엔티티입니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | `str` | 고유 식별자 (UUID) |
| `filename` | `str` | 저장된 파일명 |
| `original_filename` | `str` | 업로드 시 원본 파일명 |
| `file_path` | `str` | 서버 내 파일 경로 |
| `upload_timestamp` | `datetime` | 업로드 시각 |
| `status` | `DocumentStatus` | 현재 처리 상태 |
| `metadata` | `DocumentMetadata` | PDF 메타데이터 |
| `raw_text` | `str?` | 전체 추출 텍스트 |
| `raw_text_by_page` | `list[str]` | 페이지별 추출 텍스트 |
| `current_stage` | `PipelineStage?` | 현재 처리 중인 단계 |
| `error_message` | `str?` | 오류 발생 시 메시지 |
| `processing_started_at` | `datetime?` | 처리 시작 시각 |
| `processing_completed_at` | `datetime?` | 처리 완료 시각 |

**예시:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "550e8400_deeplearning_guide.pdf",
  "original_filename": "딥러닝 기초 가이드.pdf",
  "file_path": "/data/uploads/550e8400_deeplearning_guide.pdf",
  "upload_timestamp": "2024-01-15T09:30:00Z",
  "status": "processing",
  "metadata": { "title": "딥러닝 기초 가이드", "page_count": 150 },
  "raw_text": "제1장 서론\n딥러닝은 인공지능의 한 분야로...",
  "raw_text_by_page": ["제1장 서론\n딥러닝은...", "1.1 배경\n최근 몇 년간..."],
  "current_stage": "stage_1_segmentation",
  "error_message": null,
  "processing_started_at": "2024-01-15T09:31:00Z",
  "processing_completed_at": null
}
```

---

## TOC (목차) 모델

### TOCNode
목차의 개별 노드입니다. 트리 구조로 부모-자식 관계를 가집니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | `str` | 노드 고유 식별자 |
| `document_id` | `str` | 소속 문서 ID |
| `level` | `TOCLevel` | 계층 수준 (1, 2, 3) |
| `title` | `str` | 원본 제목 |
| `normalized_title` | `str` | 정규화된 제목 (검색용) |
| `sequence_number` | `int` | 문서 내 순서 번호 |
| `parent_id` | `str?` | 부모 노드 ID (L1은 null) |
| `children_ids` | `list[str]` | 자식 노드 ID 목록 |
| `page_start` | `int?` | 시작 페이지 |
| `page_end` | `int?` | 종료 페이지 |
| `retrieval_chunk_ids` | `list[str]` | 연결된 검색용 청크 ID들 |
| `generation_chunk_ids` | `list[str]` | 연결된 생성용 청크 ID들 |
| `entity_ids` | `list[str]` | 연결된 엔티티 ID들 |

**예시:**
```json
{
  "id": "toc-001",
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "level": 1,
  "title": "제1장 서론",
  "normalized_title": "서론",
  "sequence_number": 1,
  "parent_id": null,
  "children_ids": ["toc-002", "toc-003"],
  "page_start": 1,
  "page_end": 15,
  "retrieval_chunk_ids": ["rc-001", "rc-002"],
  "generation_chunk_ids": ["gc-001"],
  "entity_ids": ["ent-001"]
}
```

### TOCStructure
문서의 전체 목차 구조입니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `document_id` | `str` | 문서 ID |
| `root_nodes` | `list[str]` | 최상위 노드(L1) ID 목록 |
| `all_nodes` | `list[TOCNode]` | 전체 노드 목록 |
| `total_l1` | `int` | L1 노드 수 |
| `total_l2` | `int` | L2 노드 수 |
| `total_l3` | `int` | L3 노드 수 |

**예시:**
```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "root_nodes": ["toc-001", "toc-010", "toc-020"],
  "all_nodes": [
    { "id": "toc-001", "title": "제1장 서론", "level": 1 },
    { "id": "toc-002", "title": "1.1 배경", "level": 2, "parent_id": "toc-001" }
  ],
  "total_l1": 5,
  "total_l2": 15,
  "total_l3": 30
}
```

---

## 세그먼트 모델

### Segment
Stage 1에서 생성되는 원시 의미 단위입니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `segment_id` | `int` | 세그먼트 순서 번호 |
| `content` | `str` | 세그먼트 텍스트 내용 |
| `page_number` | `int` | 소속 페이지 번호 |
| `position_in_page` | `int` | 페이지 내 위치 (0부터 시작) |
| `semantic_type` | `SemanticType` | 의미적 유형 |
| `key_concepts` | `list[str]` | 핵심 개념 키워드들 |
| `reasoning` | `str` | LLM이 이 유형으로 분류한 이유 |

**예시:**
```json
{
  "segment_id": 1,
  "content": "딥러닝(Deep Learning)은 인공신경망을 기반으로 한 머신러닝의 한 분야로, 여러 층의 은닉층을 통해 데이터의 추상적 특징을 학습한다.",
  "page_number": 5,
  "position_in_page": 0,
  "semantic_type": "definition",
  "key_concepts": ["딥러닝", "인공신경망", "머신러닝", "은닉층"],
  "reasoning": "용어의 정의와 핵심 특성을 설명하고 있으므로 definition으로 분류"
}
```

### SegmentWithHeading
Stage 2에서 제목 후보가 부여된 세그먼트입니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `segment` | `Segment` | 원본 세그먼트 |
| `candidate_headings` | `list[str]` | 후보 제목 목록 (최대 3개) |
| `confidence_scores` | `list[float]` | 각 후보의 신뢰도 점수 |
| `selected_heading` | `str?` | 최종 선택된 제목 |
| `heading_level` | `TOCLevel?` | 선택된 제목의 계층 수준 |

**예시:**
```json
{
  "segment": { "segment_id": 1, "content": "딥러닝은..." },
  "candidate_headings": ["딥러닝 정의", "딥러닝 개요", "딥러닝이란"],
  "confidence_scores": [0.92, 0.85, 0.78],
  "selected_heading": "딥러닝 정의",
  "heading_level": 2
}
```

---

## 청크 모델 (Dual-Chunk System)

이 시스템의 핵심 특징은 **이중 청크 구조**입니다:
- **Retrieval Chunk**: 짧고 정밀한 벡터 검색용 (100-300 토큰)
- **Generation Chunk**: 상세한 답변 생성용 (500-1500 토큰)

### RetrievalChunk
벡터 검색에 최적화된 짧은 청크입니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | `str` | 청크 고유 ID |
| `document_id` | `str` | 소속 문서 ID |
| `toc_node_id` | `str` | 연결된 TOC 노드 ID |
| `content` | `str` | 청크 텍스트 (100-300 토큰) |
| `semantic_type` | `SemanticType` | 의미적 유형 |
| `key_concepts` | `list[str]` | 핵심 키워드들 |
| `page_numbers` | `list[int]` | 포함된 페이지들 |
| `sequence_in_document` | `int` | 문서 내 순서 |
| `sequence_in_toc_node` | `int` | TOC 노드 내 순서 |
| `generation_chunk_id` | `str` | 연결된 Generation 청크 ID |
| `embedding` | `list[float]?` | 벡터 임베딩 (1536차원 등) |
| `embedding_model` | `str?` | 사용된 임베딩 모델명 |
| `created_at` | `datetime` | 생성 시각 |
| `token_count` | `int` | 토큰 수 |

**예시:**
```json
{
  "id": "rc-001",
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "toc_node_id": "toc-002",
  "content": "딥러닝은 인공신경망 기반의 머신러닝으로, 여러 은닉층을 통해 데이터의 추상적 특징을 학습한다.",
  "semantic_type": "definition",
  "key_concepts": ["딥러닝", "인공신경망", "은닉층"],
  "page_numbers": [5],
  "sequence_in_document": 1,
  "sequence_in_toc_node": 1,
  "generation_chunk_id": "gc-001",
  "embedding": [0.023, -0.045, 0.012, ...],
  "embedding_model": "text-embedding-3-small",
  "created_at": "2024-01-15T10:00:00Z",
  "token_count": 85
}
```

### GenerationChunk
LLM 답변 생성에 사용되는 상세한 청크입니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | `str` | 청크 고유 ID |
| `document_id` | `str` | 소속 문서 ID |
| `toc_node_id` | `str` | 연결된 TOC 노드 ID |
| `content` | `str` | 청크 텍스트 (500-1500 토큰) |
| `summary` | `str` | 청크 요약문 |
| `semantic_type` | `SemanticType` | 의미적 유형 |
| `key_concepts` | `list[str]` | 핵심 키워드들 |
| `context_path` | `str` | TOC 경로 (예: "1장 > 1.1 배경") |
| `parent_summary` | `str?` | 상위 섹션 요약 |
| `page_numbers` | `list[int]` | 포함된 페이지들 |
| `sequence_in_document` | `int` | 문서 내 순서 |
| `retrieval_chunk_ids` | `list[str]` | 연결된 Retrieval 청크 ID들 |
| `entity_ids` | `list[str]` | 연결된 엔티티 ID들 |
| `created_at` | `datetime` | 생성 시각 |
| `token_count` | `int` | 토큰 수 |

**예시:**
```json
{
  "id": "gc-001",
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "toc_node_id": "toc-002",
  "content": "딥러닝(Deep Learning)은 인공신경망을 기반으로 한 머신러닝의 한 분야입니다. 여러 층의 은닉층(hidden layer)을 통해 데이터의 추상적 특징을 학습하며, 이미지 인식, 자연어 처리, 음성 인식 등 다양한 분야에서 뛰어난 성능을 보입니다.\n\n전통적인 머신러닝과 달리, 딥러닝은 특징 추출을 자동으로 수행합니다. 입력 데이터가 신경망을 통과하면서 점점 더 추상적인 표현으로 변환되어, 최종적으로 원하는 출력을 생성합니다.",
  "summary": "딥러닝의 정의와 전통 머신러닝과의 차이점을 설명",
  "semantic_type": "definition",
  "key_concepts": ["딥러닝", "인공신경망", "은닉층", "특징 추출"],
  "context_path": "제1장 서론 > 1.1 딥러닝 개요",
  "parent_summary": "1장에서는 딥러닝의 기본 개념과 역사를 다룬다",
  "page_numbers": [5, 6],
  "sequence_in_document": 1,
  "retrieval_chunk_ids": ["rc-001", "rc-002", "rc-003"],
  "entity_ids": ["ent-001"],
  "created_at": "2024-01-15T10:00:00Z",
  "token_count": 450
}
```

---

## 엔티티 모델

### TableCell
테이블의 개별 셀입니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `row` | `int` | 행 번호 (0부터 시작) |
| `col` | `int` | 열 번호 (0부터 시작) |
| `content` | `str` | 셀 내용 |
| `rowspan` | `int` | 행 병합 수 (기본 1) |
| `colspan` | `int` | 열 병합 수 (기본 1) |
| `is_header` | `bool` | 헤더 셀 여부 |

**예시:**
```json
{
  "row": 0,
  "col": 0,
  "content": "모델명",
  "rowspan": 1,
  "colspan": 1,
  "is_header": true
}
```

### TableStructure
테이블의 구조화된 표현입니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `rows` | `int` | 총 행 수 |
| `cols` | `int` | 총 열 수 |
| `headers` | `list[str]` | 헤더 행의 내용 |
| `cells` | `list[TableCell]` | 모든 셀 목록 |
| `has_merged_cells` | `bool` | 병합 셀 존재 여부 |

**예시:**
```json
{
  "rows": 4,
  "cols": 3,
  "headers": ["모델명", "파라미터 수", "정확도"],
  "cells": [
    { "row": 0, "col": 0, "content": "모델명", "is_header": true },
    { "row": 1, "col": 0, "content": "BERT" },
    { "row": 1, "col": 1, "content": "110M" },
    { "row": 1, "col": 2, "content": "94.5%" }
  ],
  "has_merged_cells": false
}
```

### BoundingBox
PDF 페이지 내 위치 좌표입니다 (0-1 정규화).

| 필드 | 타입 | 설명 |
|---|---|---|
| `x0` | `float` | 좌측 x 좌표 |
| `y0` | `float` | 상단 y 좌표 |
| `x1` | `float` | 우측 x 좌표 |
| `y1` | `float` | 하단 y 좌표 |

**예시:**
```json
{
  "x0": 0.1,
  "y0": 0.3,
  "x1": 0.9,
  "y1": 0.6
}
```

### Entity
테이블, 이미지, 다이어그램 등의 비텍스트 요소입니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | `str` | 엔티티 고유 ID |
| `document_id` | `str` | 소속 문서 ID |
| `toc_node_id` | `str?` | 연결된 TOC 노드 ID |
| `generation_chunk_id` | `str?` | 연결된 Generation 청크 ID |
| `entity_type` | `EntityType` | 엔티티 유형 |
| `page_number` | `int` | 위치한 페이지 |
| `sequence_in_page` | `int` | 페이지 내 순서 |
| `bbox` | `BoundingBox?` | 위치 좌표 |
| `canonical_json` | `dict?` | 구조화된 JSON (테이블 등) |
| `markdown` | `str?` | 마크다운 표현 |
| `ir_yaml` | `str?` | 중간 표현 (YAML) |
| `image_path` | `str?` | 추출된 이미지 경로 |
| `image_base64` | `str?` | Base64 인코딩 이미지 |
| `vision_description` | `str?` | Vision API 분석 결과 |
| `vision_processed` | `bool` | Vision 처리 완료 여부 |
| `caption` | `str?` | 캡션/제목 |
| `surrounding_context` | `str?` | 주변 텍스트 맥락 |
| `created_at` | `datetime` | 생성 시각 |

**예시:**
```json
{
  "id": "ent-001",
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "toc_node_id": "toc-005",
  "generation_chunk_id": "gc-003",
  "entity_type": "table",
  "page_number": 12,
  "sequence_in_page": 1,
  "bbox": { "x0": 0.1, "y0": 0.4, "x1": 0.9, "y1": 0.7 },
  "canonical_json": {
    "rows": 4,
    "cols": 3,
    "headers": ["모델", "파라미터", "정확도"]
  },
  "markdown": "| 모델 | 파라미터 | 정확도 |\n|---|---|---|\n| BERT | 110M | 94.5% |",
  "caption": "표 2.1 주요 모델 비교",
  "surrounding_context": "다음 표는 주요 언어 모델의 성능을 비교한 것이다.",
  "vision_processed": false,
  "created_at": "2024-01-15T10:15:00Z"
}
```

---

## 파이프라인 상태 모델

### StageResult
단일 파이프라인 단계의 실행 결과입니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `stage` | `PipelineStage` | 단계 식별자 |
| `status` | `StageStatus` | 실행 상태 |
| `started_at` | `datetime?` | 시작 시각 |
| `completed_at` | `datetime?` | 완료 시각 |
| `duration_seconds` | `float?` | 소요 시간 (초) |
| `error_message` | `str?` | 오류 메시지 |
| `output_summary` | `dict?` | 출력 요약 정보 |

**예시:**
```json
{
  "stage": "stage_1_segmentation",
  "status": "completed",
  "started_at": "2024-01-15T10:00:00Z",
  "completed_at": "2024-01-15T10:02:30Z",
  "duration_seconds": 150.5,
  "error_message": null,
  "output_summary": {
    "segments_created": 245,
    "pages_processed": 150
  }
}
```

### PipelineState
문서의 전체 파이프라인 상태입니다. 중단 후 재개(resume)를 지원합니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | `str` | 상태 고유 ID |
| `document_id` | `str` | 문서 ID |
| `stages` | `dict[str, StageResult]` | 각 단계별 결과 |
| `current_stage` | `PipelineStage?` | 현재 처리 중인 단계 |
| `last_completed_stage` | `PipelineStage?` | 마지막 완료 단계 |
| `stage_outputs` | `dict[str, str]` | 단계별 출력 파일 경로 |
| `started_at` | `datetime` | 파이프라인 시작 시각 |
| `updated_at` | `datetime` | 마지막 업데이트 시각 |
| `completed_at` | `datetime?` | 파이프라인 완료 시각 |
| `total_duration_seconds` | `float?` | 총 소요 시간 |
| `config_snapshot` | `dict?` | 실행 시 설정 스냅샷 |

**예시:**
```json
{
  "id": "ps-001",
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "stages": {
    "stage_0_extraction": { "stage": "stage_0_extraction", "status": "completed" },
    "stage_1_segmentation": { "stage": "stage_1_segmentation", "status": "completed" },
    "stage_2_headings": { "stage": "stage_2_headings", "status": "running" }
  },
  "current_stage": "stage_2_headings",
  "last_completed_stage": "stage_1_segmentation",
  "stage_outputs": {
    "stage_0_extraction": "/data/outputs/doc1/stage0.json",
    "stage_1_segmentation": "/data/outputs/doc1/stage1.json"
  },
  "started_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T10:05:00Z",
  "completed_at": null,
  "total_duration_seconds": null,
  "config_snapshot": {
    "embedding_model": "text-embedding-3-small",
    "llm_model": "gpt-4"
  }
}
```

---

## 검색 모델

### SearchQuery
사용자의 검색 요청입니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `query` | `str` | 검색 쿼리 텍스트 |
| `document_ids` | `list[str]?` | 검색 범위 문서들 (null=전체) |
| `top_k` | `int` | 반환할 최대 결과 수 (1-100, 기본 10) |
| `min_score` | `float` | 최소 유사도 점수 (0-1, 기본 0) |
| `include_entities` | `bool` | 관련 엔티티 포함 여부 (기본 true) |

**예시:**
```json
{
  "query": "딥러닝에서 과적합을 방지하는 방법은?",
  "document_ids": ["550e8400-e29b-41d4-a716-446655440000"],
  "top_k": 5,
  "min_score": 0.7,
  "include_entities": true
}
```

### SearchResult
단일 검색 결과입니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `retrieval_chunk` | `RetrievalChunk` | 매칭된 검색 청크 |
| `generation_chunk` | `GenerationChunk` | 연결된 상세 청크 |
| `toc_node` | `TOCNode` | 소속 목차 노드 |
| `entities` | `list[Entity]` | 관련 엔티티들 |
| `score` | `float` | 유사도 점수 (0-1) |
| `context_path` | `str` | 문서 내 위치 경로 |

**예시:**
```json
{
  "retrieval_chunk": { "id": "rc-045", "content": "드롭아웃은 학습 시 무작위로 뉴런을 제거하여..." },
  "generation_chunk": { "id": "gc-015", "content": "과적합 방지를 위한 대표적인 정규화 기법으로 드롭아웃이 있습니다..." },
  "toc_node": { "id": "toc-012", "title": "3.2 정규화 기법" },
  "entities": [],
  "score": 0.89,
  "context_path": "제3장 학습 최적화 > 3.2 정규화 기법"
}
```

### SearchResponse
전체 검색 응답입니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `query` | `str` | 원본 검색 쿼리 |
| `results` | `list[SearchResult]` | 검색 결과 목록 |
| `total_found` | `int` | 총 발견 결과 수 |
| `processing_time_ms` | `float` | 처리 소요 시간 (밀리초) |

**예시:**
```json
{
  "query": "딥러닝에서 과적합을 방지하는 방법은?",
  "results": [
    { "score": 0.89, "context_path": "3장 > 3.2 정규화 기법" },
    { "score": 0.82, "context_path": "3장 > 3.3 조기 종료" }
  ],
  "total_found": 12,
  "processing_time_ms": 45.3
}
```

---

## LLM 출력 스키마

각 파이프라인 단계에서 LLM이 반환하는 구조화된 출력 형식입니다.

### Stage1Output (세그멘테이션)
텍스트를 의미 단위로 분리한 결과입니다.

```json
{
  "segments": [
    {
      "segment_id": 1,
      "content": "딥러닝은 인공신경망 기반의...",
      "page_number": 5,
      "semantic_type": "definition",
      "key_concepts": ["딥러닝", "인공신경망"],
      "reasoning": "용어 정의를 포함하므로 definition"
    }
  ]
}
```

### Stage2Output (제목 생성)
각 세그먼트에 제목 후보를 부여한 결과입니다.

```json
{
  "headings": [
    {
      "segment_id": 1,
      "candidate_headings": ["딥러닝 정의", "딥러닝 개요"],
      "confidence_scores": [0.92, 0.85],
      "recommended_level": 2
    }
  ]
}
```

### Stage3Output (TOC 정렬)
제목을 계층 구조로 정렬한 결과입니다.

```json
{
  "toc_nodes": [
    {
      "node_id": "n1",
      "title": "제1장 서론",
      "level": 1,
      "parent_node_id": null,
      "segment_ids": [1, 2, 3]
    }
  ]
}
```

### Stage4Output (TOC 정규화)
제목을 표준화하고 검증한 결과입니다.

```json
{
  "normalized_nodes": [
    {
      "node_id": "n1",
      "title": "제1장 서론",
      "normalized_title": "서론",
      "level": 1,
      "parent_node_id": null,
      "segment_ids": [1, 2, 3]
    }
  ],
  "validation_passed": true,
  "issues_fixed": ["중복 제목 'Overview' → '개요'로 통합"]
}
```

### Stage5Output (이중 청킹)
Retrieval/Generation 이중 청크 생성 결과입니다.

```json
{
  "retrieval_chunks": [
    {
      "chunk_id": "rc-001",
      "toc_node_id": "n1",
      "content": "딥러닝은 인공신경망 기반...",
      "key_concepts": ["딥러닝"],
      "semantic_type": "definition"
    }
  ],
  "generation_chunks": [
    {
      "chunk_id": "gc-001",
      "toc_node_id": "n1",
      "content": "딥러닝(Deep Learning)은...(상세 설명)...",
      "summary": "딥러닝의 정의와 특징",
      "key_concepts": ["딥러닝", "인공신경망"],
      "linked_retrieval_ids": ["rc-001", "rc-002"]
    }
  ]
}
```

---

## API 응답 모델

### DocumentUploadResponse
문서 업로드 후 반환되는 응답입니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `document_id` | `str` | 생성된 문서 ID |
| `filename` | `str` | 저장된 파일명 |
| `status` | `DocumentStatus` | 초기 상태 |
| `message` | `str` | 상태 메시지 |
| `page_count` | `int` | 페이지 수 |
| `file_size_bytes` | `int` | 파일 크기 |

**예시:**
```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "550e8400_guide.pdf",
  "status": "uploaded",
  "message": "문서가 성공적으로 업로드되었습니다. 처리를 시작합니다.",
  "page_count": 150,
  "file_size_bytes": 5242880
}
```

### DocumentListResponse
문서 목록 조회 응답입니다 (페이지네이션 지원).

| 필드 | 타입 | 설명 |
|---|---|---|
| `documents` | `list[Document]` | 문서 목록 |
| `total` | `int` | 전체 문서 수 |
| `page` | `int` | 현재 페이지 번호 |
| `page_size` | `int` | 페이지당 항목 수 |
| `total_pages` | `int` | 전체 페이지 수 |

**예시:**
```json
{
  "documents": [
    { "id": "doc1", "filename": "guide.pdf", "status": "completed" },
    { "id": "doc2", "filename": "manual.pdf", "status": "processing" }
  ],
  "total": 25,
  "page": 1,
  "page_size": 10,
  "total_pages": 3
}
```

### PipelineStatusResponse
파이프라인 처리 현황 응답입니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `document_id` | `str` | 문서 ID |
| `overall_status` | `DocumentStatus` | 전체 상태 |
| `current_stage` | `PipelineStage?` | 현재 단계 |
| `stages` | `list[StageResult]` | 각 단계 결과 |
| `progress_percent` | `float` | 진행률 (0-100) |
| `error_message` | `str?` | 오류 메시지 |

**예시:**
```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "overall_status": "processing",
  "current_stage": "stage_3_toc_alignment",
  "stages": [
    { "stage": "stage_0_extraction", "status": "completed" },
    { "stage": "stage_1_segmentation", "status": "completed" },
    { "stage": "stage_2_headings", "status": "completed" },
    { "stage": "stage_3_toc_alignment", "status": "running" }
  ],
  "progress_percent": 37.5,
  "error_message": null
}
```

### ErrorResponse
오류 발생 시 반환되는 표준 응답입니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `error` | `str` | 오류 메시지 |
| `detail` | `Any?` | 상세 정보 |
| `code` | `str` | 오류 코드 |
| `timestamp` | `datetime` | 발생 시각 |

**예시:**
```json
{
  "error": "문서를 찾을 수 없습니다",
  "detail": { "document_id": "invalid-id" },
  "code": "DOCUMENT_NOT_FOUND",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

---

## 데이터 흐름 요약

```
┌─────────────────────────────────────────────────────────────────────┐
│                          PDF 업로드                                  │
└─────────────────────────┬───────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Stage 0: Document + DocumentMetadata 생성                          │
│           raw_text, raw_text_by_page 추출                           │
└─────────────────────────┬───────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Stage 1: Segment 생성 (의미 단위 분리)                              │
│           - semantic_type 분류                                       │
│           - key_concepts 추출                                        │
└─────────────────────────┬───────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Stage 2: SegmentWithHeading (제목 후보 부여)                        │
└─────────────────────────┬───────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Stage 3-4: TOCNode + TOCStructure (계층 구조 생성)                  │
└─────────────────────────┬───────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Stage 5: RetrievalChunk + GenerationChunk (이중 청크)               │
│           - 검색용 짧은 청크                                         │
│           - 생성용 상세 청크                                         │
└─────────────────────────┬───────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Stage 5b-6: Entity (테이블, 이미지 등) + Vision 처리                │
└─────────────────────────┬───────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Stage 7: embedding 벡터 생성 → VectorDB 저장                        │
└─────────────────────────┬───────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  검색: SearchQuery → RetrievalChunk 매칭 → GenerationChunk 반환      │
└─────────────────────────────────────────────────────────────────────┘
```

---

*이 문서는 `src/core/models.py` 기준으로 자동 생성되었습니다.*
