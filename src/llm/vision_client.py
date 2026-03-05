"""gpt-4o Vision 클라이언트 - 이미지 캡셔닝."""

import base64
from pathlib import Path

import structlog
from openai import AsyncOpenAI

logger = structlog.get_logger()

CAPTION_PROMPT = """이 이미지를 분석하여 상세하게 설명해 주세요.

다음 내용을 포함하세요:
1. 이미지의 주요 내용 (차트/다이어그램/사진/표 등 종류 포함)
2. 핵심 정보와 수치 (있다면)
3. 시각적 구성 요소
4. 이 이미지가 전달하는 메시지

한국어로 답변하세요."""

TABLE_OCR_PROMPT = """이 이미지는 표(테이블)입니다. 표의 내용을 마크다운 형식으로 변환해 주세요.

규칙:
- 헤더 행과 데이터 행을 구분하세요
- 각 셀의 내용을 정확히 추출하세요
- 마크다운 테이블 형식: | 열1 | 열2 | ... |

마크다운 표만 출력하세요."""


class VisionClient:
    """OpenAI gpt-4o Vision API 클라이언트."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def caption_image(self, image_path: str | Path) -> str:
        """이미지 캡셔닝 - 이미지 설명 생성."""
        image_path = Path(image_path)
        if not image_path.exists():
            logger.warning("이미지 파일 없음", path=str(image_path))
            return ""

        try:
            b64 = self._encode_image(image_path)
            ext = image_path.suffix.lstrip(".").lower()
            mime = f"image/{ext}" if ext in ("png", "jpg", "jpeg", "gif", "webp") else "image/png"

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{b64}"},
                            },
                            {"type": "text", "text": CAPTION_PROMPT},
                        ],
                    }
                ],
                max_tokens=800,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error("이미지 캡셔닝 실패", path=str(image_path), error=str(e))
            return ""

    async def table_image_to_markdown(self, image_path: str | Path) -> str:
        """테이블 이미지 → 마크다운 변환."""
        image_path = Path(image_path)
        if not image_path.exists():
            return ""
        try:
            b64 = self._encode_image(image_path)
            ext = image_path.suffix.lstrip(".").lower()
            mime = f"image/{ext}" if ext in ("png", "jpg", "jpeg", "gif", "webp") else "image/png"

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{b64}"},
                            },
                            {"type": "text", "text": TABLE_OCR_PROMPT},
                        ],
                    }
                ],
                max_tokens=1000,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error("테이블 이미지 변환 실패", path=str(image_path), error=str(e))
            return ""

    def _encode_image(self, image_path: Path) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
