# RAG VectorDB PDF Pipeline

PDF 문서를 OCR로 텍스트를 추출하고, LLM 파이프라인을 통해 문맥을 분석하여 MongoDB에 벡터로 저장하는 RAG 파이프라인 서비스입니다.

## 🚀 시작하기 (Getting Started)

로컬 환경(127.0.0.1)에서 서비스를 실행하는 방법입니다.

### 사전 요구사항 (Prerequisites)

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- OpenAI API Key

### 1. 환경 변수 설정

`.env.example` 포맷을 참고하여 `.env` 파일을 생성하고 API 키를 입력하세요.

```bash
cp .env.example .env
# .env 파일 편집: OPENAI_API_KEY 입력
```

### 2. 데이터베이스 실행 (MongoDB)

Docker Compose를 사용하여 MongoDB를 실행합니다.

```bash
docker-compose up -d
```

### 3. 백엔드 실행 (FastAPI)

API 서버는 `127.0.0.1:8000`에서 실행됩니다.

```bash
# 의존성 설치 (uv 사용하는 경우)
uv sync

# 또는 pip 사용
pip install -e .

# 서버 실행
uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000
```

- **API Root**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 4. 프론트엔드 실행 (React)

UI 서버는 `127.0.0.1:5173`에서 실행되며, API 요청은 8000번 포트로 프록시됩니다.

```bash
cd frontend

# 의존성 설치
npm install

# 개발 서버 실행
npm run dev
```

- **UI 접속**: [http://127.0.0.1:5173](http://127.0.0.1:5173)

### 5. 프로젝트 구조

- `src/`: 백엔드 소스 (FastAPI, OCR, Pipeline logic)
- `frontend/`: 프론트엔드 소스 (React, Vite, Tailwind)
- `mongodb_data/`: DB 데이터 저장소 (Docker volume)
