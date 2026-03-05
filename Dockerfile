FROM python:3.10-slim-bookworm

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# uv 설치
RUN pip install uv --no-cache-dir

WORKDIR /app

# 의존성 파일 복사 및 설치
COPY pyproject.toml ./
RUN uv pip install --system .

# 소스 코드 복사
COPY src ./src

# 데이터 디렉토리 생성
RUN mkdir -p uploads pipeline_state

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
