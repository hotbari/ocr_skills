# RAG VectorDB PDF Pipeline - Progress Tracker

## Overview
PDF → OCR/추출 → 5단계 LLM 파이프라인 → Dual-Chunk 시스템 → MongoDB → FastAPI + React UI

---

## Phase 1: Foundation (기반 구축)

- [x] 스펙 문서 작성 (`.omc/autopilot/spec.md`)
- [x] `pyproject.toml` - 프로젝트 설정 및 의존성
- [x] `docker-compose.yml` - MongoDB 컨테이너
- [x] `.env.example` - 환경 변수 템플릿
- [x] `.gitignore` - Git 무시 파일
- [x] `src/core/config.py` - 설정 관리
- [x] `src/core/models.py` - Pydantic 모델 (Document, TOC, Chunk, Entity 등)
- [x] `src/core/exceptions.py` - 예외 계층 구조
- [x] `src/db/mongodb.py` - MongoDB 연결 관리
- [x] 디렉토리 구조 생성

---

## Phase 2: OCR & 추출

- [x] `src/ocr/text_handler.py` - PyMuPDF 텍스트 추출
- [x] `src/ocr/table_handler.py` - 표 추출 (JSON + Markdown)
- [x] `src/ocr/image_handler.py` - 이미지 추출
- [x] `src/ocr/extractor.py` - 통합 추출기
- [x] `src/utils/language_detector.py` - 언어 자동 감지

---

## Phase 3: LLM 연동

- [x] `src/llm/openai_client.py` - OpenAI 클라이언트 (retry, structured output)
- [x] `src/llm/vision_client.py` - GPT-4o Vision 클라이언트
- [x] `src/prompts/loader.py` - 프롬프트 로더
- [x] `src/prompts/templates/stage1_segmentation.txt`
- [x] `src/prompts/templates/stage2_headings.txt`
- [x] `src/prompts/templates/stage3_toc_alignment.txt`
- [x] `src/prompts/templates/stage4_toc_normalization.txt`
- [x] `src/prompts/templates/stage5_chunking.txt`
- [x] `src/prompts/templates/vision_describe.txt`
- [x] `src/embeddings/openai_provider.py` - 임베딩 생성

---

## Phase 4: Repositories (데이터 접근 계층)

- [x] `src/db/repositories/document_repo.py` - 문서 CRUD
- [x] `src/db/repositories/toc_repo.py` - TOC 노드 CRUD
- [x] `src/db/repositories/chunk_repo.py` - Dual 청크 + 벡터 검색
- [x] `src/db/repositories/entity_repo.py` - 엔티티 CRUD

---

## Phase 5: Pipeline (8단계 파이프라인)

- [x] `src/pipeline/base.py` - 스테이지 기본 인터페이스
- [x] `src/pipeline/state_manager.py` - 상태 저장/재개
- [x] `src/pipeline/stage0_extraction.py` - PDF 추출
- [x] `src/pipeline/stage1_segmentation.py` - 의미 기반 세그먼트 분할
- [x] `src/pipeline/stage2_headings.py` - 후보 헤딩 생성
- [x] `src/pipeline/stage3_toc_alignment.py` - TOC 구조 정렬
- [x] `src/pipeline/stage4_toc_normalization.py` - TOC 정규화
- [x] `src/pipeline/stage5_chunking.py` - Dual 청킹
- [x] `src/pipeline/stage5b_entities.py` - 표/이미지 엔티티 생성
- [x] `src/pipeline/stage6_vision.py` - Vision 처리 (선택적)
- [x] `src/pipeline/stage7_embedding.py` - 임베딩 생성
- [x] `src/pipeline/orchestrator.py` - 파이프라인 오케스트레이터

---

## Phase 6: API (FastAPI 엔드포인트)

- [x] `src/api/dependencies.py` - FastAPI 의존성
- [x] `src/api/routers/documents.py` - 문서 업로드/조회
- [x] `src/api/routers/pipeline.py` - 파이프라인 실행/상태
- [x] `src/api/routers/search.py` - 검색 API
- [x] `src/api/main.py` - 메인 앱 + 미들웨어

---

## Phase 7: Frontend (React + Tailwind)

- [x] `frontend/package.json` - 의존성
- [x] `frontend/vite.config.ts` - Vite 설정
- [x] `frontend/tailwind.config.js` - Tailwind 설정
- [x] `frontend/src/main.tsx` - 엔트리 포인트
- [x] `frontend/src/App.tsx` - 메인 앱
- [x] `frontend/src/api/client.ts` - API 클라이언트
- [x] `frontend/src/components/` - UI 컴포넌트
- [x] `frontend/src/pages/` - 페이지

---

## Phase 8: Testing & Verification

- [x] `tests/conftest.py` - Pytest fixtures (Mock 설정, 샘플 PDF 생성 등)
- [x] `tests/test_models.py` - Pydantic 모델 테스트
- [x] `tests/test_ocr.py` - OCR 테스트
- [x] `tests/test_pipeline.py` - 파이프라인 테스트
- [x] `tests/test_search.py` - 검색 테스트
- [x] `tests/test_api.py` - FastAPI 엔드포인트 테스트
- [x] `tests/README.md` - 테스트 문서
- [x] `tests/SETUP.md` - 설정 가이드
- [ ] E2E 테스트 (업로드 → 파이프라인 → 검색) - 실제 통합 테스트

---

## Current Status

**마지막 업데이트**: 2026-01-29

**현재 단계**: Phase 8 - Testing & Verification 완료 ✅

**완료된 작업**:
- 137개 단위 테스트 모두 통과 ✅
- 모든 핵심 모듈 테스트 커버리지 완료
  - test_models.py: Pydantic 모델 테스트 (35개)
  - test_ocr.py: OCR 및 언어 감지 테스트 (25개)
  - test_pipeline.py: 파이프라인 상태 관리 테스트 (30개)
  - test_search.py: 벡터 검색 테스트 (20개)
  - test_api.py: FastAPI 엔드포인트 테스트 (27개)
- 테스트 문서화 (README.md, SETUP.md 등)

**버그 수정**:
- API 라우터 enum.value AttributeError 수정
- state_manager.py enum 처리 수정
- toc_repo.py insert() 메서드 추가

**프로젝트 상태**: MVP 완료 ✅

**다음 작업 (선택적)**:
1. E2E 통합 테스트 추가
2. 실제 PDF 파일로 전체 플로우 테스트
3. 프로덕션 배포 준비

---

## Notes

- Dual-Chunk 시스템: Retrieval (100-300 토큰) + Generation (500-1500 토큰)
- TOC 기반 계층: L1/L2/L3로 청크 그룹화
- 표/이미지는 별도 엔티티로 저장
- 파이프라인 상태 저장으로 실패 시 재개 가능
