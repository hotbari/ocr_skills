# OCR Pipeline v2

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/) [![FastAPI](https://img.shields.io/badge/fastapi-0.110+-green.svg)](https://fastapi.tiangolo.com/) [![MongoDB](https://img.shields.io/badge/mongodb-7.0+-green.svg)](https://www.mongodb.com/) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**PyMuPDF + EasyOCR 기반 한국어 최적화 PDF OCR 파이프라인**

디지털 PDF와 스캔 PDF를 모두 처리하며, GPT-4o Vision과 GPT-4o-mini를 활용한 AI 기반 이미지 캡셔닝 및 문서 구조화를 지원합니다.

## 개요

OCR Pipeline v2는 **PP-Structure를 완전히 제거**하고 PyMuPDF + EasyOCR로 전환한 고성능 OCR 문서 처리 시스템입니다. 이전 버전 대비 **10배 향상된 속도**(34.5초 → 3.4초)와 **완벽한 한글 처리**를 제공합니다.

- **디지털 PDF**: PyMuPDF로 고속 텍스트/이미지/테이블 추출
- **스캔 PDF**: EasyOCR(['ko', 'en']) 한국어 OCR 인식
- **벡터선 테이블**: PyMuPDF `get_drawings()` 기반 자동 검출
- **AI 캡셔닝**: GPT-4o Vision으로 이미지 분석
- **문서 구조화**: 섹션 계층 구조, 목차, 태그 자동 생성

---

## 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI 웹 서버 (8000)                       │
│                    /documents /pipeline /ocr-results             │
└──────────────────────┬──────────────────────────────────────────┘
                       │
       ┌───────────────┼───────────────┐
       │               │               │
       ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  Stage 0     │ │  Stage 1     │ │  Stage 2     │
│  PDF 추출    │ │ 레이아웃분석 │ │  구조화      │
│ PyMuPDF      │ │PyMuPDF+Easy  │ │ 섹션/테이블  │
│              │ │OCR/벡터선    │ │              │
└──────────────┘ └──────────────┘ └──────────────┘
       │               │               │
       └───────────────┼───────────────┘
                       │
       ┌───────────────┼───────────────┐
       │               │               │
       ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  Stage 3     │ │  Stage 4     │ │  MongoDB     │
│이미지캡셔닝  │ │  태그/요약   │ │  MinIO       │
│ GPT-4o V    │ │ GPT-4o-mini  │ │              │
└──────────────┘ └──────────────┘ └──────────────┘
```

**데이터 흐름**: PDF → (Stage 0) → 원본 텍스트+이미지 → (Stage 1) → 레이아웃 블록 → (Stage 2) → 섹션/테이블/이미지 → (Stage 3~4) → 최종 구조화 문서

---

## OCR 엔진 및 도구

### 1. PyMuPDF (fitz) - 메인 엔진

**디지털 PDF 전용 고성능 텍스트 추출**

| 기능 | 설명 |
|------|------|
| `get_text("dict")` | 폰트 정보 포함 텍스트 추출 (블록/라인/단어 단위) |
| `get_images()` | 임베디드 이미지 자동 감지 |
| `get_drawings()` | 벡터선 감지 (테이블 그리드라인) |
| `get_textbox()` | 좌표 기반 셀 텍스트 추출 |
| 폰트 크기 분석 | L1/L2/L3 제목 레벨 자동 추정 |

**예**: 10페이지 디지털 PDF 처리 시간: **~0.3초**

```python
import fitz
doc = fitz.open("document.pdf")
page = doc[0]

# 텍스트 추출
text_dict = page.get_text("dict")
for block in text_dict["blocks"]:
    if block["type"] == 0:  # 텍스트 블록
        print(block["lines"])

# 벡터선 감지 (테이블)
drawings = page.get_drawings()
for drawing in drawings:
    print(drawing.rect, drawing.type)
```

### 2. EasyOCR ['ko', 'en'] - 스캔 PDF 전용

**PyTorch 기반 딥러닝 한국어 OCR**

| 특성 | 설명 |
|------|------|
| 언어 모델 | 한국어(ko) + 영어(en) 동시 인식 |
| Lazy 초기화 | 스캔 페이지 없으면 모델 로딩 생략 |
| 위치 기반 추론 | bbox 좌표로 TITLE/TEXT/TABLE 자동 분류 |
| 신뢰도 필터 | confidence >= 0.3인 결과만 사용 |

**예**: 스캔 PDF 처리 시간: **~3초/페이지**

```python
import easyocr
reader = easyocr.Reader(['ko', 'en'], gpu=False)

# 스캔 이미지 OCR 인식
results = reader.readtext("scan_page.png")
for (bbox, text, confidence) in results:
    print(f"{text} (신뢰도: {confidence:.2f})")
```

### 3. 벡터선 테이블 감지

**PyMuPDF 그래픽 엔진 기반 테이블 자동 검출**

```
원리:
  1. get_drawings() → 모든 선 수집
  2. 수평선(h_lines) + 수직선(v_lines) 분리
  3. 선 교차점에서 셀 경계 추출
  4. 각 셀에 get_textbox()로 텍스트 할당
  5. 마크다운 테이블 변환

파라미터:
  - table_min_line_len: 20pt (이상 선만 인식)
  - table_max_line_width: 3pt (테이블선 두께)
  - table_row_gap_threshold: 80pt (행 간격 판정)
```

**장점**: 벡터 PDF 테이블을 정확하게 감지, 마크다운/HTML 변환 가능

### 4. OpenAI GPT-4o Vision (Stage 3)

**이미지 분석 및 자연어 설명 생성**

```json
입력: {
  "image_path": "extracted_image.png",
  "surrounding_context": "섹션 텍스트",
  "max_tokens": 200
}

출력: {
  "vision_description": "이 차트는 2020~2025년 매출 추이를 보여줍니다..."
}
```

**설정**: `ENABLE_VISION_CAPTIONING=true` (선택적 실행)

### 5. OpenAI GPT-4o-mini (Stage 4)

**섹션 태그 및 요약 생성**

| 출력 | 설명 |
|------|------|
| `tags` | 3~7개 키워드 자동 생성 |
| `summary` | 1~2문장 섹션 요약 |
| 최소 길이 | 100자 이상 섹션만 처리 |

**설정**: `ENABLE_TAG_GENERATION=true` (선택적 실행)

---

## 파이프라인 5단계

### Stage 0: PDF 추출 (pdf_extractor.py)

**PyMuPDF 기반 원본 텍스트/이미지/테이블 추출**

```
입력: PDF 파일
처리:
  1. 전체 페이지 순회 (get_text() - 디지털 텍스트 추출)
  2. 스캔 페이지 판별:
     - 기준 1: 페이지당 글자수 < 50자
     - 기준 2: 이미지 면적 비율 > 80% AND 임베디드 폰트 없음
  3. 이미지 추출 및 저장 (uploads/{doc_id}/images/)
  4. 테이블 감지 (벡터선 기초)
  5. 언어 감지 (한글 비율 분석)
출력:
  - raw_text: 전체 문서 텍스트 (page break \n\n)
  - text_by_page: 페이지별 텍스트
  - images[]: RawImage(page_number, bbox, path)
  - tables[]: RawTable(page_number, bbox, markdown)
  - is_scanned: boolean (절반 이상 스캔 판정)
  - scanned_pages: int[] (스캔 페이지 번호 목록)
  - detected_language: Language (ko/en/mixed/unknown)
```

**환경 변수**:
```env
SCAN_MIN_CHARS_PER_PAGE=50              # 글자수 임계값
SCAN_IMAGE_RATIO_THRESHOLD=0.8          # 이미지 면적 비율
```

**처리 시간**: ~0.3초 (10페이지)

---

### Stage 1: 레이아웃 분석 (layout_analyzer.py)

**PyMuPDF + EasyOCR 기반 레이아웃 블록 분류**

#### 디지털 페이지 분석

```
처리 순서:
  1. _extract_text_blocks()
     - get_text("dict")에서 모든 텍스트 블록 추출
     - 폰트 크기 기반 블록 타입 추론:
       * 중앙값 × 1.4 이상 또는 bold → TITLE
       * 나머지 → TEXT
     - HEADER/FOOTER: 상단/하단 3% 영역

  2. _detect_vector_tables()
     - get_drawings()로 벡터선 수집
     - 수평선+수직선 교차점에서 셀 생성
     - 각 셀에 get_textbox() 텍스트 할당
     - 마크다운 변환

  3. 겹침 필터링
     - 테이블과 50% 이상 겹치는 텍스트 블록 제거

  4. _postprocess_blocks()
     - 인접 블록 병합 (Y 간격 <= 10px)
     - 읽기 순서 정렬 (2단 레이아웃 감지)
     - sequence_in_page 재부여
```

**출력 예시**:
```json
{
  "block_type": "title",
  "bbox": {"x0": 50, "y0": 100, "x1": 400, "y1": 130},
  "text": "제1장 서론",
  "font_size": 16.0,
  "confidence": 1.0
}
```

#### 스캔 페이지 분석

```
처리 순서:
  1. EasyOCR 초기화 (lazy - 필요시에만)
  2. 이미지 전처리:
     - 저해상도(w<1500, h<2000) → 2x 업스케일
     - Otsu 이진화 (흑백 명확화)
     - 모폴로지 노이즈 제거 (닫음 연산)
  3. readtext()로 텍스트 인식
  4. bbox 기반 블록 타입 추론:
     - 상단/하단 3% → HEADER/FOOTER
     - 테이블 패턴 감지 → TABLE
     - 이미지 영역 → FIGURE
     - 나머지 → TEXT
```

**환경 변수**:
```env
EASYOCR_LANG=ko,en                     # OCR 언어
BLOCK_MERGE_ENABLED=true                # 블록 병합 활성화
BLOCK_MERGE_Y_GAP=10.0                  # Y 간격 임계값 (픽셀)
```

**처리 시간**: ~3초/페이지 (스캔 PDF)

---

### Stage 2: 구조화 (stage2_structure.py)

**레이아웃 블록 → 섹션/테이블/이미지 변환**

```
처리 순서:
  1. 폰트 크기 수집
     - TITLE 블록에서 폰트 크기 통계 계산

  2. 제목 레벨 추론
     우선순위:
     a) 폰트 크기: 큰 순서 → L1/L2/L3
     b) 패턴: "1.", "1-1" 형식
     c) Fallback: 텍스트 길이

  3. 섹션 계층 구조 구성
     - 제목별 본문 범위 자동 결정
     - 인라인 테이블/이미지 할당

  4. TOC 트리 생성
     - Section → TOCNode 매핑
     - parent_id / children_ids 설정

  5. 테이블 병합
     - Stage 0 테이블 + Stage 1 테이블 bbox 비교
     - 겹치는 것들을 하나로 통합
```

**출력 구조**:
```json
{
  "sections": [
    {
      "id": "SEC-0001",
      "heading": "서론",
      "heading_level": 1,
      "content": "...",
      "page_start": 1,
      "page_end": 3,
      "entity_ids": ["IMG-001", "TBL-001"],
      "tags": [],
      "summary": null
    }
  ],
  "tables": [
    {
      "page_number": 2,
      "markdown": "| 컬럼1 | 컬럼2 |...",
      "section_id": "SEC-0001"
    }
  ],
  "images": [
    {
      "page_number": 2,
      "image_path": "uploads/doc-id/images/img_1.png",
      "vision_description": null
    }
  ]
}
```

---

### Stage 3: 이미지 캡셔닝 (stage3_vision.py)

**GPT-4o Vision으로 추출 이미지 분석**

```
처리 순서:
  1. 추출된 이미지 파일 읽기
  2. base64 인코딩
  3. GPT-4o Vision API 호출
  4. vision_description 저장
  5. vision_processed=true 표시

병렬 처리: 최대 3개 동시 (asyncio)
선택적 실행: ENABLE_VISION_CAPTIONING=true
```

**프롬프트 예시**:
```
"다음 이미지를 분석하고 자연어로 설명해주세요.
배경: {surrounding_context}"
```

**출력 예시**:
```json
{
  "vision_description": "이 그래프는 2020년부터 2025년까지의
                         월별 판매량 추이를 보여줍니다.
                         상승 추세가 뚜렷하며..."
}
```

---

### Stage 4: 태그/요약 (stage4_tags.py)

**GPT-4o-mini로 섹션 분석**

```
처리 조건:
  - 섹션 본문 길이 >= 100자
  - ENABLE_TAG_GENERATION=true

처리 순서:
  1. 섹션별로 gpt-4o-mini 호출
  2. 태그 3~7개 추출
  3. 요약 1~2문장 생성
  4. Section.tags / Section.summary 업데이트

병렬 처리: 배치 처리 (5개씩)
```

**프롬프트 예시**:
```json
{
  "role": "user",
  "content": "다음 텍스트를 분석하여:
            1. 키워드 3~7개 (태그)
            2. 1~2문장 요약

            텍스트: {section_content}"
}
```

**출력 예시**:
```json
{
  "tags": ["머신러닝", "분류모델", "정확도"],
  "summary": "본 섹션에서는 SVM과
              Random Forest의 성능을 비교하고
              하이퍼파라미터 튜닝 방법을 설명합니다."
}
```

---

## PRD 출력 구조

최종 결과는 **PRD 형식** JSON으로 제공됩니다.

```json
{
  "ocr_result_id": "uuid-result-id",
  "ref_document_id": "uuid-doc-id",
  "created_at": "2026-03-10T12:30:45Z",
  "page": [
    {
      "page_num": 1,
      "section": [
        {
          "section_id": "SEC-0001",
          "title": "제1장 서론",
          "content": "본 문서는...",
          "keyword": "키워드1, 키워드2, 키워드3",
          "sequence_id": 0
        }
      ],
      "image": [
        {
          "name": "figure_1.png",
          "description": "GPT-4o Vision 분석 결과",
          "image_url": "http://minio:9000/ocr-images/doc-id/figure_1.png",
          "tag": ["차트", "통계"],
          "sequence_id": 1
        }
      ],
      "table": [
        {
          "name": "table_1",
          "table_md": "| 구분 | 2024 | 2025 |\n|------|------|------|\n| 매출 | 100 | 120 |",
          "sequence_id": 2
        }
      ]
    },
    {
      "page_num": 2,
      "section": [...],
      "image": [...],
      "table": [...]
    }
  ]
}
```

**저장 위치**:
- MongoDB: `ocr_results` 컬렉션
- MinIO: `ocr-images` 버킷

---

## 설치 및 실행

### 필수 요구사항

- Python 3.10+
- Docker & Docker Compose (권장) 또는 로컬 MongoDB 7.0+
- OpenAI API Key (gpt-4o, gpt-4o-mini)
- MinIO (또는 S3 호환 스토리지)

### 로컬 설치

#### 1. 저장소 복제

```bash
git clone <repository-url>
cd ocr_pipeline_v2
```

#### 2. 환경 설정

```bash
# .env 파일 생성
cp .env.example .env

# 필수 항목 설정
cat > .env << 'EOF'
# OpenAI API
OPENAI_API_KEY=sk-your-api-key-here

# 모델 설정
VISION_MODEL=gpt-4o
LLM_MODEL=gpt-4o-mini

# MongoDB (로컬 또는 Docker)
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=ocr_pipeline

# 저장 경로
UPLOAD_DIR=./uploads
PIPELINE_STATE_DIR=./pipeline_state

# API 설정
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=false

# 파일 제한
MAX_FILE_SIZE_MB=100
MAX_PAGES=500

# 파이프라인 옵션
ENABLE_VISION_CAPTIONING=true    # Stage 3 활성화
ENABLE_TAG_GENERATION=true       # Stage 4 활성화

# MinIO 설정
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=ocr-images
MINIO_USE_SSL=false
MINIO_PUBLIC_ENDPOINT=http://localhost:9000

# 스캔 판별 설정
SCAN_MIN_CHARS_PER_PAGE=50
SCAN_IMAGE_RATIO_THRESHOLD=0.8

# EasyOCR 설정
EASYOCR_LANG=ko,en

# 블록 후처리
BLOCK_MERGE_ENABLED=true
BLOCK_MERGE_Y_GAP=10.0
EOF
```

#### 3. Python 패키지 설치

```bash
# NumPy 호환성 필수 (EasyOCR)
pip install numpy==1.26.4

# 기본 패키지
pip install -r pyproject.toml

# 또는 직접 설치
pip install "fastapi>=0.110.0" \
            "uvicorn[standard]>=0.29.0" \
            "pymupdf>=1.23.0" \
            "pillow>=10.0.0" \
            "openai>=1.12.0" \
            "motor>=3.3.0" \
            "easyocr>=1.7.0" \
            "opencv-python-headless>=4.8.0" \
            "minio>=7.2.0" \
            "pydantic>=2.0" \
            "pydantic-settings>=2.0" \
            "structlog>=24.0.0" \
            "aiofiles>=23.0.0"
```

#### 4. MongoDB 시작 (Docker)

```bash
# 스탠드얼론 MongoDB
docker run -d \
  --name mongodb \
  -p 27017:27017 \
  -e MONGO_INITDB_ROOT_USERNAME=root \
  -e MONGO_INITDB_ROOT_PASSWORD=password \
  mongo:7.0

# 환경변수 업데이트
MONGODB_URI=mongodb://root:password@localhost:27017
```

#### 5. MinIO 시작 (Docker)

```bash
docker run -d \
  --name minio \
  -p 9000:9000 \
  -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin \
  -e MINIO_ROOT_PASSWORD=minioadmin \
  minio/minio:latest \
  server /data --console-address ":9001"

# 버킷 생성 (mc 클라이언트)
mc alias set minio http://localhost:9000 minioadmin minioadmin
mc mb minio/ocr-images
mc anonymous set public minio/ocr-images
```

#### 6. API 서버 시작

```bash
# 개발 모드
python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# 프로덕션 모드
gunicorn -w 4 -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 src.api.main:app
```

### Docker Compose 실행 (권장)

#### 1. 환경 설정

```bash
cp .env.example .env
# .env 파일에서 OPENAI_API_KEY 설정
```

#### 2. 컨테이너 시작

```bash
# 빌드 및 실행
docker-compose up -d

# 로그 확인
docker-compose logs -f backend

# 상태 확인
docker-compose ps
```

#### 3. 접근 URL

| 서비스 | URL | 설명 |
|--------|-----|------|
| **API 서버** | http://localhost:8002 | FastAPI 메인 |
| **API 문서** | http://localhost:8002/docs | Swagger UI |
| **MinIO 콘솔** | http://localhost:9001 | 스토리지 관리 |
| **데모 페이지** | http://localhost:8002/demo | 결과 뷰어 |

---

## API 엔드포인트

### 1. 문서 업로드

```bash
curl -X POST "http://localhost:8002/documents/upload?auto_run=true" \
  -F "file=@document.pdf"
```

**응답**:
```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "document.pdf",
  "status": "processing",
  "message": "파이프라인 자동 실행 시작",
  "page_count": 10,
  "file_size_bytes": 2560000
}
```

**파라미터**:
- `auto_run` (bool): true → 즉시 파이프라인 실행, false → 업로드만

---

### 2. 처리 상태 조회

```bash
curl "http://localhost:8002/pipeline/{document_id}/status"
```

**응답**:
```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "overall_status": "completed",
  "current_stage": "stage_4_tags",
  "progress_percent": 100.0,
  "stages": [
    {
      "stage": "stage_0_extract",
      "status": "completed",
      "duration_seconds": 0.34,
      "output_summary": {
        "page_count": 10,
        "detected_language": "ko",
        "is_scanned": false,
        "images_count": 5
      }
    },
    {
      "stage": "stage_1_layout",
      "status": "completed",
      "duration_seconds": 3.21,
      "output_summary": {
        "total_blocks": 45,
        "title_blocks": 8,
        "table_blocks": 3
      }
    },
    {
      "stage": "stage_2_structure",
      "status": "completed",
      "duration_seconds": 0.15
    },
    {
      "stage": "stage_3_vision",
      "status": "completed",
      "duration_seconds": 12.45,
      "output_summary": {
        "images_captioned": 5
      }
    },
    {
      "stage": "stage_4_tags",
      "status": "completed",
      "duration_seconds": 5.67,
      "output_summary": {
        "sections_tagged": 8
      }
    }
  ],
  "error_message": null
}
```

---

### 3. OCR 결과 조회 (PRD 형식)

```bash
# 전체 문서 결과
curl "http://localhost:8002/ocr-results/{document_id}"

# 특정 페이지 결과
curl "http://localhost:8002/ocr-results/{document_id}/pages/1"
```

**응답** (`ocr-results/{document_id}`):
```json
{
  "ocr_result_id": "uuid-result-id",
  "ref_document_id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2026-03-10T12:30:45Z",
  "page": [
    {
      "page_num": 1,
      "section": [
        {
          "section_id": "SEC-0001",
          "title": "제1장 서론",
          "content": "본 문서는 OCR 파이프라인의 기능을 소개합니다.",
          "keyword": "OCR, 파이프라인, 한국어",
          "sequence_id": 0
        }
      ],
      "image": [
        {
          "name": "figure_1.png",
          "description": "시스템 아키텍처 다이어그램",
          "image_url": "http://minio:9000/ocr-images/550e8400-e29b-41d4-a716-446655440000/figure_1.png",
          "tag": [],
          "sequence_id": 1
        }
      ],
      "table": []
    }
  ]
}
```

---

### 4. 문서 상세 조회

```bash
curl "http://localhost:8002/documents/{document_id}"
```

**응답**:
```json
{
  "document": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "filename": "document.pdf",
    "status": "completed",
    "metadata": {
      "page_count": 10,
      "detected_language": "ko",
      "is_scanned": false
    },
    "processing_completed_at": "2026-03-10T12:35:45Z"
  },
  "toc": {
    "nodes": [
      {
        "id": "TOC-0001",
        "level": 1,
        "title": "제1장 서론",
        "page_start": 1,
        "page_end": 3,
        "children_ids": ["TOC-0002"]
      }
    ]
  },
  "sections": [...],
  "tables": [...],
  "images": [...],
  "total_sections": 8,
  "total_tables": 3,
  "total_images": 5
}
```

---

### 5. 헬스 체크

```bash
curl "http://localhost:8002/health"
```

**응답**:
```json
{
  "status": "healthy",
  "database": "connected",
  "version": "2.0.0"
}
```

---

## 성능

### 벤치마크 (test_10pages.pdf, 10페이지 디지털 PDF)

| Stage | 엔진 | 시간 | 비고 |
|-------|------|------|------|
| **Stage 0** | PyMuPDF | 0.34초 | PDF 추출 |
| **Stage 1** | PyMuPDF+벡터선 | 0.87초 | 레이아웃 분석 |
| **Stage 2** | 구조화 로직 | 0.15초 | 섹션 매핑 |
| **Stage 3** | GPT-4o Vision | 12.45초 | 5개 이미지 캡셔닝 |
| **Stage 4** | GPT-4o-mini | 5.67초 | 8개 섹션 태그/요약 |
| **합계** | - | **~19.5초** | 모든 Stage (Vision+Tag 포함) |

### 이전 버전 대비

| 항목 | PP-Structure v1 | PyMuPDF v2 | 개선율 |
|------|-----------------|-----------|--------|
| Stage 0~2 총 시간 | 34.5초 | 3.4초 | **10배 향상** |
| 한글 오인식 | 있음 (한자 혼입) | 없음 | **완벽 해결** |
| 테이블 감지 | PP-Structure | 벡터선 | 정확도 동등 |
| 메모리 사용 | ~2GB | ~800MB | **60% 절감** |

### 최적화 팁

```bash
# GPU 사용 (EasyOCR, 선택사항)
# 환경변수: GPU=true

# Stage 3~4 비활성화 (LLM 비용 절감)
ENABLE_VISION_CAPTIONING=false
ENABLE_TAG_GENERATION=false

# 대용량 문서 처리 (병렬화)
# 최대 5개 문서 동시 처리 권장 (메모리/API 제한)
```

---

## 환경 변수 완전 목록

```env
# ============ OpenAI ============
OPENAI_API_KEY=sk-...              # 필수
VISION_MODEL=gpt-4o                # Stage 3 이미지 캡셔닝
LLM_MODEL=gpt-4o-mini              # Stage 4 태그/요약

# ============ MongoDB ============
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=ocr_pipeline

# ============ 저장 경로 ============
UPLOAD_DIR=./uploads               # PDF 및 추출 이미지
PIPELINE_STATE_DIR=./pipeline_state # 파이프라인 상태 저장

# ============ API 서버 ============
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=false                         # true → 상세 에러 메시지

# ============ 파일 제한 ============
MAX_FILE_SIZE_MB=100               # 최대 파일 크기
MAX_PAGES=500                      # 최대 페이지 수

# ============ 파이프라인 옵션 ============
ENABLE_VISION_CAPTIONING=true      # Stage 3 활성화
ENABLE_TAG_GENERATION=true         # Stage 4 활성화

# ============ MinIO ============
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=ocr-images
MINIO_USE_SSL=false
MINIO_PUBLIC_ENDPOINT=http://localhost:9000

# ============ 스캔 판별 ============
SCAN_MIN_CHARS_PER_PAGE=50         # 글자수 임계값
SCAN_IMAGE_RATIO_THRESHOLD=0.8     # 이미지 면적 비율

# ============ EasyOCR ============
EASYOCR_LANG=ko,en                 # 지원 언어 (쉼표 구분)

# ============ 블록 후처리 ============
BLOCK_MERGE_ENABLED=true           # 인접 블록 병합
BLOCK_MERGE_Y_GAP=10.0             # 병합 Y 간격 (픽셀)
```

---

## 데이터베이스 구조

### MongoDB 컬렉션

| 컬렉션 | 설명 | 주요 필드 |
|--------|------|----------|
| `documents` | 업로드된 PDF 메타데이터 | `id`, `filename`, `status`, `metadata`, `current_stage` |
| `pipeline_states` | 파이프라인 실행 상태 | `document_id`, `stages`, `current_stage`, `started_at` |
| `toc_structures` | 목차 구조 | `document_id`, `nodes[]` |
| `sections` | 섹션 정보 | `document_id`, `heading`, `content`, `tags`, `summary` |
| `tables` | 테이블 데이터 | `document_id`, `section_id`, `markdown`, `bbox` |
| `images` | 이미지 메타데이터 | `document_id`, `section_id`, `image_path`, `vision_description` |
| `ocr_results` | 최종 OCR 결과 (PRD) | `ref_document_id`, `page[]` |

### MinIO 버킷 구조

```
ocr-images/
├── {doc_id}/
│   ├── figure_1.png
│   ├── figure_2.png
│   ├── ...
```

**접근 URL**: `http://minio:9000/ocr-images/{doc_id}/figure_1.png`

---

## 문제 해결

### 1. EasyOCR 모델 다운로드 오류

```
Error: Failed to download EasyOCR model
```

**해결**:
```bash
# 수동 모델 캐시
python -c "import easyocr; reader = easyocr.Reader(['ko', 'en'])"

# 캐시 경로
~/.EasyOCR/model/
```

### 2. MongoDB 연결 실패

```
MongoServerSelectionTimeoutError
```

**해결**:
```bash
# MongoDB 상태 확인
docker ps | grep mongodb

# 재시작
docker restart mongodb

# 연결 문자열 확인
MONGODB_URI=mongodb://root:password@localhost:27017
```

### 3. OpenAI API 오류

```
openai.error.AuthenticationError: Invalid API key
```

**해결**:
```bash
# .env 파일에서 유효한 키 확인
echo $OPENAI_API_KEY

# 인증 테스트
python -c "from openai import OpenAI;
client = OpenAI();
print(client.models.list())"
```

### 4. 스캔 PDF 인식 안 됨

```
스캔 페이지인데 텍스트 미인식
```

**확인 사항**:
- `SCAN_MIN_CHARS_PER_PAGE` 값 조정 (기본 50)
- `EASYOCR_LANG`에 필요한 언어 포함 (예: `ko,en,ja`)
- 이미지 해상도 확인 (150 DPI 이상 권장)

---

## 프로젝트 구조

```
ocr_pipeline_v2/
├── src/
│   ├── api/
│   │   ├── main.py                      # FastAPI 애플리케이션
│   │   ├── routers/
│   │   │   ├── documents.py             # 문서 업로드/조회
│   │   │   ├── pipeline.py              # 파이프라인 실행/상태
│   │   │   └── ocr_results.py           # 결과 조회 (PRD)
│   │   └── static/
│   │       └── demo.html                # 웹 데모 페이지
│   ├── core/
│   │   ├── config.py                    # 설정 관리
│   │   ├── models.py                    # Pydantic 모델
│   │   └── exceptions.py                # 커스텀 예외
│   ├── ocr/
│   │   ├── pdf_extractor.py             # Stage 0: PDF 추출
│   │   ├── layout_analyzer.py           # Stage 1: 레이아웃 분석
│   │   └── paddle_ocr.py                # (미사용) PP-Structure
│   ├── pipeline/
│   │   ├── orchestrator.py              # 파이프라인 조율
│   │   ├── stage0_extract.py
│   │   ├── stage1_layout.py
│   │   ├── stage2_structure.py
│   │   ├── stage3_vision.py             # Stage 3: 이미지 캡셔닝
│   │   └── stage4_tags.py               # Stage 4: 태그/요약
│   ├── llm/
│   │   └── vision_client.py             # GPT-4o Vision 클라이언트
│   └── db/
│       ├── mongodb.py                   # MongoDB 연결
│       └── repositories/
│           ├── document_repo.py
│           ├── section_repo.py
│           ├── table_repo.py
│           ├── image_repo.py
│           ├── toc_repo.py
│           └── ocr_result_repo.py
├── tests/
│   └── test_*.py                        # 단위 테스트
├── docker-compose.yml                   # 컨테이너 오케스트레이션
├── Dockerfile                           # 이미지 빌드 설정
├── pyproject.toml                       # 패키지 설정 (Python 3.10+)
├── .env.example                         # 환경 변수 템플릿
└── README.md                            # 이 파일
```

---

## 개발 및 기여

### 로컬 테스트

```bash
# pytest 설치
pip install pytest pytest-asyncio httpx

# 전체 테스트
pytest tests/ -v

# 특정 테스트
pytest tests/test_pdf_extractor.py -v
```

### 코드 스타일

```bash
# Ruff로 포맷팅
pip install ruff
ruff check src/ --fix
ruff format src/
```

### 로깅

```python
import structlog
logger = structlog.get_logger()

logger.info("처리 시작", document_id=doc_id, pages=page_count)
logger.error("오류 발생", error=str(e), stage="stage_1")
```

---

## 라이선스

MIT License - 자유롭게 사용, 수정, 배포 가능

---

## 참고 자료

- [PyMuPDF 공식 문서](https://pymupdf.readthedocs.io/)
- [EasyOCR GitHub](https://github.com/JaidedAI/EasyOCR)
- [FastAPI 문서](https://fastapi.tiangolo.com/)
- [OpenAI API 참고](https://platform.openai.com/docs/api-reference)
- [MongoDB 스키마 설계](https://docs.mongodb.com/manual/schema/)

---

## 지원 및 연락

- 버그 리포트: GitHub Issues
- 기능 제안: GitHub Discussions
- 문의: [프로젝트 담당자]

---

**마지막 업데이트**: 2026-03-10
**버전**: 2.0.0
**상태**: Production Ready
