"""PaddleOCR 텍스트 추출 - 스캔 PDF 전용.

설치:
    pip install paddlepaddle paddleocr
"""

from pathlib import Path

import structlog

logger = structlog.get_logger()


class PaddleOCRExtractor:
    """스캔 PDF 페이지 이미지에서 PaddleOCR로 텍스트 추출."""

    def __init__(self, lang: str = "korean", use_gpu: bool = False):
        self.lang = lang
        self.use_gpu = use_gpu
        self._ocr = None
        self._available = False
        self._try_init()

    def _try_init(self) -> None:
        try:
            from paddleocr import PaddleOCR
            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang=self.lang,
                use_gpu=self.use_gpu,
                show_log=False,
            )
            self._available = True
            logger.info("PaddleOCR 초기화 성공", lang=self.lang)
        except ImportError:
            logger.warning("PaddleOCR 미설치 - 스캔 PDF 텍스트 추출 불가")
        except Exception as e:
            logger.warning("PaddleOCR 초기화 실패", error=str(e))

    @property
    def available(self) -> bool:
        return self._available

    def extract_text_from_image(self, image_path: str | Path) -> str:
        """이미지 파일에서 텍스트 추출."""
        if not self._available:
            return ""
        try:
            result = self._ocr.ocr(str(image_path), cls=True)
            lines = []
            if result:
                for page_result in result:
                    if page_result:
                        for line in page_result:
                            text, confidence = line[1]
                            if confidence > 0.5:
                                lines.append(text)
            return "\n".join(lines)
        except Exception as e:
            logger.warning("PaddleOCR 추출 실패", path=str(image_path), error=str(e))
            return ""

    def extract_text_from_array(self, img_array) -> str:
        """numpy 배열 이미지에서 텍스트 추출."""
        if not self._available:
            return ""
        try:
            result = self._ocr.ocr(img_array, cls=True)
            lines = []
            if result:
                for page_result in result:
                    if page_result:
                        for line in page_result:
                            text, confidence = line[1]
                            if confidence > 0.5:
                                lines.append(text)
            return "\n".join(lines)
        except Exception as e:
            logger.warning("PaddleOCR 배열 추출 실패", error=str(e))
            return ""
