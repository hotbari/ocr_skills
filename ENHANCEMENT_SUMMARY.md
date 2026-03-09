# OCR Pipeline v2 고도화 작업 요약

작업일: 2026-03-09

## 목표

PP-Structure를 primary OCR/레이아웃 엔진으로 완전 통합하여 Stage 0, Stage 1을 고도화.
Tesseract 의존성 없이 스캔 PDF OCR을 PP-Structure 단독으로 완결.

---

## 변경 파일 목록

### 1. `src/core/config.py`
Settings 클래스에 8개 필드 추가:

```python
# PP-Structure 설정
pp_structure_lang: str = "korean"          # OCR 언어 (korean/ch/en)
pp_structure_use_angle_cls: bool = True    # 기울어진 텍스트 감지
pp_structure_use_gpu: bool = False         # GPU 사용 여부

# 스캔 판별 설정
scan_min_chars_per_page: int = 50          # 페이지당 최소 글자수
scan_image_ratio_threshold: float = 0.8   # 이미지 면적 비율 임계값

# 블록 후처리 설정
block_merge_enabled: bool = True           # 인접 텍스트 블록 병합
block_merge_y_gap: float = 10.0            # 병합 허용 Y 간격(픽셀)
```

### 2. `src/ocr/pdf_extractor.py`
- `ExtractionResult`에 `scanned_pages: list[int]` 필드 추가
- `PDFExtractor.__init__`에 `scan_min_chars_per_page`, `scan_image_ratio_threshold` 파라미터 추가
- `_detect_scanned()` → `_detect_scanned_pages()` 교체: 페이지별 복합 판별
  - 기준: 텍스트 < 50자 **OR** (이미지 면적비 > 0.8 **AND** 임베디드 폰트 없음)
- `PDFExtractor.preprocess_scan_image()` 정적 메서드 신규 추가:
  - 저해상도(w<1500, h<2000) → 2x 업스케일
  - Otsu 이진화
  - 모폴로지 노이즈 제거 (MORPH_CLOSE)
  - BGR 복원 (PP-Structure 입력 형식)

### 3. `src/ocr/layout_analyzer.py`
- `LayoutAnalyzer.__init__`에 `lang`, `use_angle_cls`, `block_merge_enabled`, `block_merge_y_gap` 파라미터 추가
- `_LAYOUT_LANG_MAP` 추가: PPStructure layout 모델이 `en`/`ch`만 지원하므로 `korean` → `ch` 자동 매핑
- `_try_init_pp_structure()`: `lang=layout_lang`, `use_angle_cls` 적용
- `analyze()`: `scanned_pages: list[int]` 파라미터 추가
- `_analyze_with_pp_structure()`: 스캔 페이지에 `PDFExtractor.preprocess_scan_image()` 적용
- `_parse_pp_result()`: TEXT/TITLE 블록 confidence < 0.6 필터링
- `_postprocess_blocks()` 신규: 병합 → 정렬 → sequence_in_page 재부여
- `_merge_nearby_text_blocks()` 신규: Y간격 ≤ y_gap + X차이 < 50px인 TEXT 블록 병합
- `_sort_reading_order()` 신규: 2단 레이아웃(좌/우 각 3개 이상) 감지 시 좌→우 순 정렬
- `_extract_pymupdf_page_blocks()` 교체: `get_text("dict")` 기반 폰트 크기/bold 추론
- `_infer_type_from_font()` 신규: 폰트 크기 중앙값 × 1.4 이상 또는 bold → TITLE

### 4. `src/pipeline/stage1_layout.py`
- `analyzer.analyze()` 호출 시 `scanned_pages=stage0.result.scanned_pages` 전달

### 5. `src/pipeline/orchestrator.py`
- `PDFExtractor` 초기화 시 `scan_min_chars_per_page`, `scan_image_ratio_threshold` 전달
- `LayoutAnalyzer` 초기화 시 `use_gpu`, `lang`, `use_angle_cls`, `block_merge_enabled`, `block_merge_y_gap` 전달

---

## 환경 세팅 (설치 패키지)

```bash
pip install numpy==1.26.4
pip install opencv-python==4.8.1.78
pip install paddlepaddle==2.6.2
pip install paddleocr==2.7.3
pip install paddlex[ocr]   # PPStructureV3 의존성 (설치되어 있으나 미사용)
```

> **주의**: paddleocr 3.x (PPStructureV3)는 paddlepaddle 3.x CPU 런타임 호환성 오류로 사용 불가.
> paddleocr 2.7.3 + paddlepaddle 2.6.2 조합 사용.

---

## 테스트 결과 (test_10pages.pdf / 10페이지 디지털 PDF)

```
Stage 0:  1.42s  | 10페이지, 텍스트 31,033자, 스캔 없음 (scanned_pages=[])
Stage 1: 32.99s  | PP-Structure 58블록 감지
                 | header:3, title:7, footer:17, reference:8,
                 | figure:10, text:3, figure_caption:4, table_caption:2, table:4
Stage 2:  0.00s  | 섹션 6, TOC 6, 테이블 4, 이미지 14
Stage 3:  skip   | ENABLE_VISION_CAPTIONING=false
Stage 4:  skip   | ENABLE_TAG_GENERATION=false
총 소요:  34.4s
```

---

## 알려진 이슈 및 향후 개선

| 이슈 | 원인 | 해결 방안 |
|------|------|-----------|
| 한국어 OCR 오인식 (한자 혼입) | PP-Structure layout 모델이 `ch`(중국어) 전용 | 문서 언어에 맞게 `.env`의 `PP_STRUCTURE_LANG=en` 설정 |
| Stage 1 속도 느림 (33초/10페이지) | PP-Structure CPU 추론 | GPU 환경 전환 또는 배치 처리 도입 |
| 섹션 본문 내용 없음 | PP-Structure TEXT 블록 수 부족 | confidence 임계값 조정 또는 PyMuPDF 텍스트 보완 |

---

## .env 권장 설정

```env
USE_PP_STRUCTURE=true
USE_PADDLE_OCR=true
PP_STRUCTURE_LANG=en          # 영문 문서의 경우
# PP_STRUCTURE_LANG=korean    # 한국어 문서의 경우 (layout은 ch 모델 사용)
PP_STRUCTURE_USE_ANGLE_CLS=false   # cls 모델 없으면 false
ENABLE_VISION_CAPTIONING=true
ENABLE_TAG_GENERATION=true
```
