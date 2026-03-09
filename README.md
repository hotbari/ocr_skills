# OCR Pipeline v2

PyMuPDF + EasyOCR 기반 한국어 최적화 PDF OCR 파이프라인

---

## 사용 기술

| 구분 | 도구 | 용도 |
|------|------|------|
| 디지털 PDF 추출 | **PyMuPDF (fitz)** | 텍스트·이미지·벡터선 테이블 추출 |
| 스캔 PDF OCR | **EasyOCR** `['ko', 'en']` | 한국어+영어 텍스트 인식 |
| 이미지 캡셔닝 | **GPT-4o Vision** | 이미지 자동 설명 생성 (선택) |
| 태그/요약 | **GPT-4o-mini** | 섹션 키워드·요약 생성 (선택) |
| 저장소 | **MongoDB** + **MinIO** | 결과 DB 저장 + 이미지 오브젝트 스토리지 |

> PP-Structure는 NumPy 2.0 비호환 및 한글→한자 오인식 문제로 제거됨

---

## 파이프라인

```
PDF 업로드
    │
    ▼
Stage 0 │ PDF 추출 (PyMuPDF)
        │ - 텍스트·이미지·테이블 추출
        │ - 스캔 페이지 자동 판별
    │
    ▼
Stage 1 │ 레이아웃 분석
        │ - 디지털: 폰트 크기 기반 블록 분류 + 벡터선 테이블 감지
        │ - 스캔: EasyOCR 인식 → 위치 기반 블록 추론
    │
    ▼
Stage 2 │ 구조화
        │ - TITLE → 섹션 계층 구성 (폰트 크기 기반 L1/L2/L3)
        │ - TABLE → Markdown 변환
        │ - FIGURE → ImageEntity 생성
        │ - TOC 트리 자동 생성
    │
    ▼
Stage 3 │ 이미지 캡셔닝 (GPT-4o Vision, 선택)
        │ - 추출 이미지 → vision_description 생성
        │ - MinIO 업로드 → 공개 URL 저장
    │
    ▼
Stage 4 │ 태그/요약 (GPT-4o-mini, 선택)
        │ - 섹션별 키워드 태그 3~7개
        │ - 1~2문장 요약
    │
    ▼
OCR Result 저장 (PRD 형식 → MongoDB)
```

---

## 출력 구조 (PRD)

```json
{
  "ocr_result_id": "uuid",
  "ref_document_id": "doc-id",
  "page": [
    {
      "page_num": 1,
      "sections": [
        { "section_id": "SEC-0001", "title": "제목", "content": "본문",
          "keyword": "키워드1, 키워드2", "sequence_id": 0 }
      ],
      "images": [
        { "name": "image.png", "description": "GPT-4o 설명",
          "image_url": "http://minio:9000/ocr-images/...", "tag": [], "sequence_id": 1 }
      ],
      "table": [
        { "name": "테이블명", "table_md": "| 컬럼 | ... |", "sequence_id": 2 }
      ]
    }
  ]
}
```

---

## API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/documents/upload?auto_run=true` | PDF 업로드 + 파이프라인 자동 실행 |
| `GET` | `/pipeline/{id}/status` | 처리 진행 상태 조회 |
| `GET` | `/ocr-results/{id}` | PRD 형식 결과 전체 조회 |
| `GET` | `/ocr-results/{id}/pages/{num}` | 페이지 단위 조회 |
| `GET` | `/demo` | 웹 데모 페이지 |

---

## 실행

```bash
# Docker Compose (backend + MinIO)
docker compose up -d

# 접속
http://<host>:8002/demo       # 데모 페이지
http://<host>:9001            # MinIO 콘솔 (minioadmin/minioadmin)
```

---

## 성능 (10페이지 디지털 PDF 기준)

| 항목 | 결과 |
|------|------|
| 전체 처리 시간 | ~3.4초 |
| PP-Structure 대비 | 10배 향상 (34.5초 → 3.4초) |
| 한글 오인식 | 없음 (한자 치환 문제 해결) |
