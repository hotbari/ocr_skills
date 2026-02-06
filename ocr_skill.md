# OCR Pipeline -> Claude Skill

## 목차
1. [Skill이란 무엇인가](#1-skill이란-무엇인가)
2. [왜 Skill로 만들어야 하는가](#2-왜-skill로-만들어야-하는가)
3. [Skill 설계 사고 과정](#3-skill-설계-사고-과정)
4. [OCR Skill 상세 구현](#4-ocr-skill-상세-구현)
5. [고급 패턴과 확장](#5-고급-패턴과-확장)
6. [실전 적용 가이드](#6-실전-적용-가이드)

---

## 1. Skill이란 무엇인가

### 1.1 개념 정의

**Skill = 패턴 감지 + 자동화된 워크플로우**

```
┌─────────────────────────────────────────────────────────────┐
│  사용자 입력: "PDF에서 텍스트 추출해줘"                        │
└─────────────────────┬───────────────────────────────────────┘
                      │ 패턴 매칭
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Skill 트리거: "PDF", "텍스트 추출", "OCR" 감지               │
└─────────────────────┬───────────────────────────────────────┘
                      │ 워크플로우 실행
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  자동 실행:                                                  │
│  1. 파일 확인 → 2. OCR 실행 → 3. 후처리 → 4. 검증            │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Skill의 본질적 가치

**질문: 왜 단순히 "OCR 해줘"라고 말하면 안 되는가?**

**답변:** 매번 다른 결과가 나올 수 있기 때문입니다.

| 접근 방식 | 결과 |
|-----------|------|
| 단순 요청 | Claude가 그때그때 다른 방식으로 처리 |
| Skill 사용 | **항상 동일한 품질**의 일관된 워크플로우 |

```
Without Skill:
  "OCR 해줘" → [Claude의 그날 기분?] → 불확실한 결과

With Skill:
  "OCR 해줘" → [정의된 8-Stage 파이프라인] → 예측 가능한 결과
```

### 1.3 Skill vs 단순 프롬프트

| 구분 | 단순 프롬프트 | Skill |
|------|--------------|-------|
| 재현성 | 낮음 | **높음** |
| 복잡도 처리 | 한계 있음 | **다단계 워크플로우** |
| 품질 보장 | 불확실 | **검증 단계 포함** |
| 지식 축적 | 매번 새로 설명 | **영구 저장** |
| 협업 | 어려움 | **팀 공유 가능** |

---

## 2. 왜 Skill로 만들어야 하는가

### 2.1 개발자 관점의 문제 인식

**문제 1: 반복되는 설명**
```
세션 1: "PyMuPDF로 텍스트 추출하고, tesseract로 이미지 PDF 처리하고..."
세션 2: "PyMuPDF로 텍스트 추출하고, tesseract로 이미지 PDF 처리하고..."
세션 3: 또 같은 설명...
```

**문제 2: 품질 편차**
```
월요일: 꼼꼼하게 8단계 파이프라인 실행
화요일: 급하니까 3단계만...
수요일: 어? 뭐가 달랐지?
```

**문제 3: 지식 휘발**
```
3개월 전: "이 프로젝트 OCR은 이렇게 하면 돼"
오늘: "어떻게 했더라...?"
```

### 2.2 Skill이 해결하는 것

```
┌─────────────────────────────────────────────────────────────┐
│                     Skill = 캡슐화                          │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ 지식        │  │ 워크플로우   │  │ 품질 기준   │         │
│  │ (HOW)      │  │ (WHAT)      │  │ (CHECK)    │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                             │
│  "OCR 해줘" 한 마디로 모든 것이 실행됨                         │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 사고의 전환점

**Before (명령형 사고):**
> "Claude야, PyMuPDF 써서 텍스트 추출하고,
> 테이블은 이렇게 처리하고, 이미지는 저렇게..."

**After (선언형 사고):**
> "OCR 파이프라인 실행해"

이것이 **추상화(Abstraction)**의 힘입니다.

```python
# 명령형: HOW를 매번 설명
extract_text_with_pymupdf(pdf)
if has_images:
    run_tesseract(images)
process_tables(tables)
...

# 선언형: WHAT만 선언
ocr_pipeline.run(pdf)  # Skill이 HOW를 알고 있음
```

---

## 3. Skill 설계 사고 과정

### 3.1 설계 질문 프레임워크

Skill을 설계할 때 스스로에게 물어야 할 질문들:

```
┌─────────────────────────────────────────────────────────────┐
│ Q1. 이 Skill은 어떤 문제를 해결하는가?                        │
├─────────────────────────────────────────────────────────────┤
│ A1. PDF에서 텍스트/테이블/이미지를 추출하고                    │
│     구조화된 데이터로 변환하는 복잡한 과정을 자동화              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Q2. 사용자는 어떤 말로 이 기능을 요청할까?                     │
├─────────────────────────────────────────────────────────────┤
│ A2. "PDF 텍스트 추출", "OCR 해줘", "문서 분석",                │
│     "PDF 파싱", "텍스트 인식"                                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Q3. 실패할 수 있는 지점은 어디인가?                           │
├─────────────────────────────────────────────────────────────┤
│ A3. - 스캔 품질이 낮은 PDF                                   │
│     - 다국어 혼합 문서                                        │
│     - 복잡한 테이블 구조                                      │
│     - 손글씨 포함 문서                                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Q4. 검증은 어떻게 할 것인가?                                  │
├─────────────────────────────────────────────────────────────┤
│ A4. - 추출된 텍스트 길이 체크                                 │
│     - 언어 감지 정확도                                        │
│     - 테이블 구조 유효성                                      │
│     - Stage별 출력 검증                                       │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 계층적 설계 (Layered Design)

**왜 계층을 나누는가?**

단일 거대 Skill의 문제:
```
[거대한 OCR Skill]
- 모든 것을 한 번에 처리
- 일부만 실패해도 전체 재실행
- 디버깅 어려움
- 재사용 불가
```

계층적 Skill의 장점:
```
[OCR Pipeline Skill] ← 오케스트레이션
       │
       ├── [Extraction Skill] ← 텍스트 추출만
       │
       ├── [Table Skill] ← 테이블 처리만
       │
       ├── [Image Skill] ← 이미지 처리만
       │
       └── [Validation Skill] ← 검증만

장점:
- 실패 지점 명확
- 부분 재실행 가능
- 개별 테스트 가능
- 다른 프로젝트에 재사용
```

### 3.3 상태 관리 설계

**질문: 파이프라인 중간에 실패하면?**

**나쁜 설계:**
```
PDF → [Stage1] → [Stage2] → [Stage3] → 실패!
                                        ↓
                              처음부터 다시 시작
```

**좋은 설계 (Checkpoint):**
```
PDF → [Stage1] → ✓저장 → [Stage2] → ✓저장 → [Stage3] → 실패!
                                                        ↓
                                              Stage3부터 재시작
```

이것이 이 프로젝트의 `pipeline_state/` 디렉토리가 존재하는 이유입니다.

```
pipeline_state/
├── doc_abc123/
│   ├── stage0_complete.json  ← Stage 0 결과 저장
│   ├── stage1_complete.json  ← Stage 1 결과 저장
│   ├── stage2_complete.json  ← Stage 2 결과 저장
│   └── current_stage.json    ← 현재 진행 상태
```

---

## 4. OCR Skill 상세 구현

### 4.1 Skill 파일 구조

Claude Code에서 Skill을 정의하는 방법:

```
~/.claude/skills/           ← 글로벌 Skills (모든 프로젝트)
    └── ocr-pipeline.md

프로젝트/.claude/skills/    ← 로컬 Skills (이 프로젝트만)
    └── ocr-pipeline.md
```

### 4.2 OCR Pipeline Skill 정의

```markdown
<!-- ~/.claude/skills/ocr-pipeline.md -->

# OCR Pipeline Skill

## Trigger Patterns
- "OCR", "텍스트 추출", "PDF 파싱"
- "문서 분석", "PDF에서 텍스트"
- "extract text from PDF"

## Description
PDF 문서에서 텍스트, 테이블, 이미지를 추출하고
구조화된 데이터로 변환하는 8단계 파이프라인을 실행합니다.

## Workflow

### Phase 1: 사전 검증
1. PDF 파일 존재 확인
2. 파일 크기 및 페이지 수 확인
3. 이미 처리된 문서인지 확인 (중복 방지)

### Phase 2: 텍스트 추출 (Stage 0)
1. PyMuPDF로 네이티브 텍스트 추출 시도
2. 추출 실패 시 → pytesseract OCR fallback
3. 언어 자동 감지 (한국어/영어/혼합)

### Phase 3: 구조화 (Stage 1-4)
1. Stage 1: 의미 기반 세그먼트 분할
2. Stage 2: 후보 헤딩 생성
3. Stage 3: TOC 구조 정렬 (L1/L2/L3)
4. Stage 4: TOC 정규화

### Phase 4: 청킹 (Stage 5)
1. Retrieval Chunk 생성 (100-300 토큰)
2. Generation Chunk 생성 (500-1500 토큰)
3. 엔티티 추출 (테이블, 이미지)

### Phase 5: 벡터화 (Stage 6-7)
1. Vision API로 이미지 설명 생성 (선택)
2. Embedding 생성 (text-embedding-3-small)
3. MongoDB 저장

### Phase 6: 검증
1. 추출된 청크 수 확인
2. 임베딩 차원 검증 (1536)
3. TOC 구조 유효성 검사

## Agent Delegation

| 작업 | Agent | Model | 이유 |
|------|-------|-------|------|
| 파일 탐색 | explore | haiku | 빠른 확인 |
| Stage 구현 | executor | sonnet | 표준 구현 |
| 아키텍처 검토 | architect | opus | 복잡한 판단 |
| 테이블 분석 | vision | sonnet | 시각 처리 |

## Error Handling

### 일반 오류
- 파일 없음 → 사용자에게 경로 확인 요청
- 권한 없음 → 권한 안내

### OCR 오류
- 텍스트 추출 0 → 이미지 PDF로 판단, tesseract 실행
- tesseract 실패 → 이미지 품질 문제 안내

### LLM 오류
- Rate limit → 지수 백오프 재시도
- Token limit → 청크 분할 후 재시도

## State Persistence

상태 저장 위치: `pipeline_state/{document_id}/`

| 파일 | 내용 |
|------|------|
| `metadata.json` | 문서 메타정보 |
| `stage{N}_output.json` | 각 Stage 출력 |
| `current_state.json` | 현재 진행 상태 |

## Verification Checklist

실행 완료 전 필수 확인:
- [ ] 모든 Stage 성공
- [ ] 청크 수 > 0
- [ ] 임베딩 생성 완료
- [ ] MongoDB 저장 확인
- [ ] 검색 테스트 통과
```

### 4.3 왜 이렇게 구성했는가?

#### 4.3.1 Trigger Patterns

```markdown
## Trigger Patterns
- "OCR", "텍스트 추출", "PDF 파싱"
```

**설계 이유:**
- 사용자는 다양한 표현을 사용함
- "OCR 해줘" = "텍스트 추출해줘" = "PDF 파싱해줘"
- 모든 동의어를 커버해야 누락 없음

**사고 확장:**
```
좋은 Trigger 설계:
✓ 동의어 포함 (OCR, 텍스트 추출, 문서 인식)
✓ 한국어 + 영어 혼합
✓ 동사 + 명사 패턴 ("추출해줘", "추출")

나쁜 Trigger 설계:
✗ 너무 일반적 ("문서" → 모든 문서 관련 요청에 반응)
✗ 너무 구체적 ("PyMuPDF로 PDF 텍스트 추출" → 사용자가 모를 수 있음)
```

#### 4.3.2 Phase 분리

```markdown
### Phase 1: 사전 검증
### Phase 2: 텍스트 추출
### Phase 3: 구조화
...
```

**설계 이유:**
- 실패 지점 격리 (어디서 실패했는지 명확)
- 부분 재실행 가능 (Stage 3만 다시)
- 진행 상황 추적 가능 ("현재 Phase 3/6")

**사고 확장:**
```
Phase 설계 원칙:

1. Single Responsibility
   - 각 Phase는 하나의 책임만
   - Phase 2는 "추출"만, "구조화"는 Phase 3

2. Fail Fast
   - Phase 1에서 파일 없으면 즉시 실패
   - Phase 6까지 가서 실패하면 시간 낭비

3. Checkpoint
   - 각 Phase 완료 시 상태 저장
   - 실패 시 해당 Phase부터 재시작
```

#### 4.3.3 Agent Delegation

```markdown
| 작업 | Agent | Model |
|------|-------|-------|
| Stage 구현 | executor | sonnet |
| 아키텍처 검토 | architect | opus |
```

**설계 이유:**
- 모든 작업을 직접 하면 품질 불균일
- 전문 Agent에게 위임 → 일관된 품질
- Model 선택 → 비용/품질 최적화

**사고 확장:**
```
Agent 선택 기준:

비용 효율:
┌─────────────────────────────────────────┐
│ haiku ($0.25/M) < sonnet < opus ($15/M) │
└─────────────────────────────────────────┘

작업별 최적 선택:
- 단순 탐색 → haiku (빠르고 저렴)
- 표준 구현 → sonnet (균형)
- 복잡한 판단 → opus (정확도 중요)

잘못된 선택의 비용:
- 단순 작업에 opus → 돈 낭비
- 복잡 작업에 haiku → 품질 저하, 재작업 필요
```

#### 4.3.4 Error Handling

```markdown
### OCR 오류
- 텍스트 추출 0 → 이미지 PDF로 판단
```

**설계 이유:**
- 오류는 반드시 발생함 (방어적 프로그래밍)
- 오류 유형별 대응 전략 필요
- 사용자에게 명확한 피드백

**사고 확장:**
```
오류 처리 계층:

Layer 1: 예방 (Prevention)
└── 파일 검증, 입력 검증

Layer 2: 탐지 (Detection)
└── try-catch, 상태 검사

Layer 3: 복구 (Recovery)
└── 재시도, fallback, checkpoint 복원

Layer 4: 통보 (Notification)
└── 사용자에게 명확한 오류 메시지

예시:
텍스트 추출 0
  → Layer 2: 탐지됨
  → Layer 3: tesseract fallback 시도
  → 여전히 0?
  → Layer 4: "이미지 품질이 낮습니다" 통보
```

---

## 5. 고급 패턴과 확장

### 5.1 Skill Composition (조합)

여러 Skill을 조합하여 더 큰 워크플로우 구성:

```
┌─────────────────────────────────────────────────────────────┐
│                  [Document Analysis Skill]                  │
│                                                             │
│    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐   │
│    │ OCR Skill   │ →  │ Summary     │ →  │ QA Skill    │   │
│    │             │    │ Skill       │    │             │   │
│    └─────────────┘    └─────────────┘    └─────────────┘   │
│                                                             │
│    "문서 분석해줘" → OCR + 요약 + Q&A 준비까지 자동 실행       │
└─────────────────────────────────────────────────────────────┘
```

**구현 예시:**
```markdown
# Document Analysis Skill

## Workflow
1. Invoke OCR Pipeline Skill
2. Wait for completion
3. Invoke Summary Skill with OCR output
4. Invoke QA Preparation Skill
5. Return unified result
```

### 5.2 Conditional Branching (조건 분기)

입력 특성에 따라 다른 경로 실행:

```
                    [PDF 분석]
                        │
            ┌───────────┼───────────┐
            ▼           ▼           ▼
        [텍스트 PDF] [이미지 PDF] [혼합 PDF]
            │           │           │
            ▼           ▼           ▼
        [PyMuPDF]   [Tesseract] [하이브리드]
            │           │           │
            └───────────┴───────────┘
                        │
                        ▼
                  [구조화 단계]
```

**구현:**
```markdown
### Phase 2: 텍스트 추출

#### Step 2.1: PDF 유형 판별
- text_layer_ratio 계산
- > 80%: 텍스트 PDF
- < 20%: 이미지 PDF
- 그 외: 혼합 PDF

#### Step 2.2: 유형별 처리
- IF 텍스트 PDF:
    → PyMuPDF 직접 추출
- ELIF 이미지 PDF:
    → 전체 페이지 Tesseract OCR
- ELSE:
    → 페이지별 판단 후 하이브리드 처리
```

### 5.3 Parallel Execution (병렬 실행)

독립적인 작업은 동시 실행:

```
                [Stage 0: PDF 추출]
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
   [텍스트 추출]    [테이블 추출]    [이미지 추출]
        │               │               │
        └───────────────┴───────────────┘
                        │
                        ▼
                [Stage 1: 세그먼트]
```

**왜 병렬화하는가?**
```
순차 실행:
텍스트(3초) → 테이블(5초) → 이미지(4초) = 총 12초

병렬 실행:
텍스트(3초) ─┐
테이블(5초) ─┼─→ 총 5초 (가장 긴 작업 기준)
이미지(4초) ─┘

속도 향상: 12초 → 5초 (58% 감소)
```

**구현:**
```markdown
### Phase 2: 추출 (Parallel)

동시 실행:
1. Task(subagent_type="executor", prompt="텍스트 추출...")
2. Task(subagent_type="executor", prompt="테이블 추출...")
3. Task(subagent_type="executor", prompt="이미지 추출...")

모든 Task 완료 대기 후 다음 Phase
```

### 5.4 Skill Versioning (버전 관리)

Skill도 코드처럼 버전 관리:

```markdown
# OCR Pipeline Skill v2.1.0

## Changelog
- v2.1.0: Vision API 통합, 이미지 설명 생성 추가
- v2.0.0: Dual-Chunk 시스템 도입
- v1.5.0: 다국어 지원 (한/영/일)
- v1.0.0: 초기 릴리즈

## Breaking Changes (v2.0.0)
- Chunk 구조 변경: 단일 → Retrieval + Generation
- 저장 스키마 변경: chunks → retrieval_chunks, generation_chunks
```

**왜 버전 관리가 필요한가?**
- 팀원 간 Skill 버전 동기화
- Breaking change 추적
- 롤백 가능

---

## 6. 실전 적용 가이드

### 6.1 Skill 등록 방법

#### 방법 1: 글로벌 Skill (모든 프로젝트에서 사용)

```bash
# 디렉토리 생성
mkdir -p ~/.claude/skills

# Skill 파일 생성
# ~/.claude/skills/ocr-pipeline.md 에 Skill 정의 작성
```

#### 방법 2: 로컬 Skill (현재 프로젝트만)

```bash
# 프로젝트 내 디렉토리 생성
mkdir -p .claude/skills

# Skill 파일 생성
# .claude/skills/ocr-pipeline.md 에 Skill 정의 작성
```

#### 방법 3: oh-my-claudecode의 local-skills-setup

```bash
# /oh-my-claudecode:local-skills-setup 실행
# 대화형 설정으로 Skill 등록
```

### 6.2 Skill 호출 방법

```
# 자동 트리거 (패턴 매칭)
사용자: "이 PDF에서 텍스트 추출해줘"
→ OCR Pipeline Skill 자동 활성화

# 명시적 호출
사용자: "/ocr-pipeline"
→ Skill 직접 실행

# 인자 전달
사용자: "/ocr-pipeline --file=document.pdf --lang=ko"
→ 특정 파일, 특정 언어로 실행
```

### 6.3 디버깅과 개선

#### Skill이 트리거되지 않을 때
```
체크리스트:
□ Trigger Patterns에 해당 표현 포함?
□ Skill 파일 경로 정확?
□ 문법 오류 없음?
□ 다른 Skill과 충돌?
```

#### Skill 실행이 실패할 때
```
체크리스트:
□ 어느 Phase에서 실패?
□ 해당 Phase의 전제조건 충족?
□ Agent 위임 올바름?
□ 오류 처리 누락?
```

#### Skill 개선 사이클

```
[실행] → [결과 관찰] → [문제 식별] → [Skill 수정] → [재실행]
   ↑                                                    │
   └────────────────────────────────────────────────────┘
```

### 6.4 최종 체크리스트

Skill 작성 완료 전 확인:

```
구조적 완성도:
□ Trigger Patterns 정의됨
□ Description 명확함
□ Workflow 단계별 정의됨
□ Agent Delegation 명시됨
□ Error Handling 포함됨
□ Verification 체크리스트 있음

실용성:
□ 실제 사용 시나리오 테스트함
□ 엣지 케이스 고려함
□ 성능 최적화 고려함 (병렬화 등)
□ 팀원이 이해할 수 있는 수준의 문서화
```

---

## 부록: OCR Skill 최종 템플릿

아래 템플릿을 `~/.claude/skills/ocr-pipeline.md`에 저장하세요:

```markdown
# OCR Pipeline Skill

## Metadata
- Version: 1.0.0
- Author: [Your Name]
- Last Updated: 2024-XX-XX

## Trigger Patterns
- "OCR"
- "텍스트 추출"
- "PDF 파싱"
- "PDF에서 텍스트"
- "문서 텍스트 인식"
- "extract text from PDF"

## Description
PDF 문서에서 텍스트, 테이블, 이미지를 추출하여
구조화된 데이터로 변환하는 8단계 파이프라인입니다.

## Prerequisites
- Python 3.11+
- PyMuPDF, pytesseract 설치
- MongoDB 실행 중
- OpenAI API Key 설정

## Workflow

### Phase 1: 사전 검증 (Validation)
**목적**: 실행 가능 여부 확인

1. PDF 파일 존재 확인
2. 파일 접근 권한 확인
3. 파일 크기 검사 (< 100MB)
4. 페이지 수 확인 (< 500 pages)
5. 중복 처리 여부 확인

**실패 시**: 구체적 오류 메시지와 함께 종료

### Phase 2: OCR 추출 (Stage 0)
**목적**: PDF → Raw Data

1. PyMuPDF로 텍스트 레이어 추출
2. 추출량 검사
   - 충분: 다음 단계
   - 부족: Tesseract OCR 실행
3. 언어 감지 (langdetect)
4. 테이블 영역 식별
5. 이미지 추출 및 저장

**Agent**: executor (sonnet)
**저장**: stage0_output.json

### Phase 3: 의미 구조화 (Stage 1-2)
**목적**: Raw Text → Semantic Segments

1. Stage 1: LLM 기반 의미 분할
   - 정의, 절차, 예시 등 유형 분류
   - 핵심 개념 추출
2. Stage 2: 후보 헤딩 생성
   - 각 세그먼트에 대표 제목 부여

**Agent**: executor (sonnet)
**LLM**: gpt-4o-mini
**저장**: stage1_output.json, stage2_output.json

### Phase 4: TOC 구조화 (Stage 3-4)
**목적**: Segments → Hierarchical TOC

1. Stage 3: L1/L2/L3 계층 정렬
2. Stage 4: TOC 정규화 및 검증

**Agent**: executor (sonnet)
**LLM**: gpt-4o-mini
**저장**: stage3_output.json, stage4_output.json

### Phase 5: 청킹 (Stage 5)
**목적**: TOC → Searchable Chunks

1. Retrieval Chunk 생성 (100-300 tokens)
   - 임베딩 최적화
2. Generation Chunk 생성 (500-1500 tokens)
   - 답변 생성 최적화
3. 엔티티 추출 (테이블, 이미지)

**Agent**: executor (sonnet)
**저장**: stage5_output.json

### Phase 6: 벡터화 (Stage 6-7)
**목적**: Chunks → Embeddings

1. Stage 6 (선택): Vision API로 이미지 설명
2. Stage 7: 임베딩 생성
   - Model: text-embedding-3-small
   - Dimension: 1536

**Agent**: executor (sonnet)
**저장**: stage6_output.json, stage7_output.json

### Phase 7: 저장 및 검증
**목적**: 최종 확인

1. MongoDB 저장
   - documents collection
   - retrieval_chunks collection
   - generation_chunks collection
   - entities collection
2. 검증 쿼리 실행
3. 결과 리포트 생성

**Agent**: architect (opus) for verification

## Agent Delegation Table

| Phase | Task | Agent | Model | Reason |
|-------|------|-------|-------|--------|
| 1 | 파일 검증 | - | - | 직접 수행 (단순) |
| 2 | OCR 추출 | executor | sonnet | 표준 구현 |
| 3-4 | 구조화 | executor | sonnet | LLM 연동 구현 |
| 5 | 청킹 | executor | sonnet | 알고리즘 구현 |
| 6-7 | 벡터화 | executor | sonnet | API 연동 |
| 7 | 검증 | architect | opus | 품질 판단 |

## Error Handling

### 파일 오류
| 오류 | 대응 |
|------|------|
| 파일 없음 | 경로 재확인 요청 |
| 권한 없음 | 권한 설정 안내 |
| 크기 초과 | 분할 처리 제안 |

### OCR 오류
| 오류 | 대응 |
|------|------|
| 추출 텍스트 0 | Tesseract fallback |
| Tesseract 실패 | 이미지 품질 문제 안내 |
| 언어 감지 실패 | 수동 언어 지정 요청 |

### LLM 오류
| 오류 | 대응 |
|------|------|
| Rate Limit | 지수 백오프 재시도 |
| Token Limit | 입력 분할 후 재시도 |
| API 오류 | 3회 재시도 후 실패 처리 |

### DB 오류
| 오류 | 대응 |
|------|------|
| 연결 실패 | Docker 상태 확인 안내 |
| 저장 실패 | 로컬 백업 후 재시도 |

## State Persistence

```
pipeline_state/{document_id}/
├── metadata.json         # 문서 메타정보
├── stage0_output.json    # OCR 결과
├── stage1_output.json    # 세그먼트
├── stage2_output.json    # 헤딩
├── stage3_output.json    # TOC 정렬
├── stage4_output.json    # TOC 정규화
├── stage5_output.json    # 청크
├── stage6_output.json    # Vision 결과
├── stage7_output.json    # 임베딩 메타
└── current_state.json    # 현재 진행 상태
```

## Verification Checklist

완료 선언 전 필수 확인:

- [ ] 모든 Stage 성공 (stage0-7)
- [ ] 추출된 청크 수 > 0
- [ ] Retrieval 청크 평균 토큰 100-300 범위
- [ ] Generation 청크 평균 토큰 500-1500 범위
- [ ] 임베딩 차원 = 1536
- [ ] MongoDB 저장 완료
- [ ] 테스트 검색 쿼리 성공

## Output Format

```json
{
  "document_id": "abc123",
  "status": "completed",
  "statistics": {
    "total_pages": 50,
    "total_segments": 120,
    "retrieval_chunks": 250,
    "generation_chunks": 80,
    "entities": {
      "tables": 15,
      "images": 30
    }
  },
  "processing_time": "45.3s",
  "stages_completed": ["0", "1", "2", "3", "4", "5", "6", "7"]
}
```
```

---

## 마치며: 개발자 사고 확장 포인트

### 1. 추상화의 힘
Skill은 복잡한 워크플로우를 **한 단어**로 실행 가능하게 만듭니다.
이것이 소프트웨어 공학에서 말하는 **추상화(Abstraction)**입니다.

### 2. 실패를 설계하라
"어떻게 성공할까?"보다 **"어디서 실패할까?"**를 먼저 생각하세요.
좋은 Skill은 실패 시나리오를 미리 대비합니다.

### 3. 검증 없이 완료 없다
"됐을 것 같아"가 아니라 **"확인했고, 통과했다"**가 되어야 합니다.
Verification Checklist는 단순한 체크가 아니라 **품질 보증**입니다.

### 4. 재사용을 설계하라
오늘 만든 Skill이 내일 다른 프로젝트에서도 쓰일 수 있도록
**범용성**을 고려하세요.

### 5. 문서화는 미래의 나를 위한 것
"이건 내가 알잖아"가 아니라
**"3개월 후의 내가 이걸 보면 이해할 수 있을까?"**를 기준으로 작성하세요.
