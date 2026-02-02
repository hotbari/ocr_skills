"""Language detection utility."""

from typing import Optional

import structlog
from langdetect import LangDetectException, detect, detect_langs

from src.core.models import Language

logger = structlog.get_logger()


class LanguageDetector:
    """Detects language of text content."""

    # Minimum text length for reliable detection
    MIN_TEXT_LENGTH = 50

    # Supported language mappings
    LANGUAGE_MAP = {
        "ko": Language.KOREAN,
        "en": Language.ENGLISH,
    }

    def __init__(self):
        self.logger = logger.bind(component="LanguageDetector")

    def detect(self, text: str) -> Language:
        """Detect language of text.

        Args:
            text: Text to analyze

        Returns:
            Detected language enum
        """
        if not text or len(text.strip()) < self.MIN_TEXT_LENGTH:
            return Language.UNKNOWN

        try:
            # Clean text for detection
            clean_text = self._clean_for_detection(text)

            if len(clean_text) < self.MIN_TEXT_LENGTH:
                return Language.UNKNOWN

            detected = detect(clean_text)

            if detected in self.LANGUAGE_MAP:
                return self.LANGUAGE_MAP[detected]

            # For other languages, default to UNKNOWN or treat as English
            return Language.UNKNOWN

        except LangDetectException as e:
            self.logger.warning("Language detection failed", error=str(e))
            return Language.UNKNOWN

    def detect_with_confidence(self, text: str) -> tuple[Language, float]:
        """Detect language with confidence score.

        Args:
            text: Text to analyze

        Returns:
            Tuple of (detected language, confidence 0-1)
        """
        if not text or len(text.strip()) < self.MIN_TEXT_LENGTH:
            return Language.UNKNOWN, 0.0

        try:
            clean_text = self._clean_for_detection(text)

            if len(clean_text) < self.MIN_TEXT_LENGTH:
                return Language.UNKNOWN, 0.0

            results = detect_langs(clean_text)

            if not results:
                return Language.UNKNOWN, 0.0

            # Get top result
            top_result = results[0]
            lang_code = top_result.lang
            confidence = top_result.prob

            if lang_code in self.LANGUAGE_MAP:
                return self.LANGUAGE_MAP[lang_code], confidence

            return Language.UNKNOWN, confidence

        except LangDetectException:
            return Language.UNKNOWN, 0.0

    def detect_mixed(self, text: str, threshold: float = 0.3) -> Language:
        """Detect if text contains mixed languages.

        Args:
            text: Text to analyze
            threshold: Minimum probability for secondary language to be considered

        Returns:
            MIXED if multiple languages detected above threshold
        """
        if not text or len(text.strip()) < self.MIN_TEXT_LENGTH:
            return Language.UNKNOWN

        try:
            clean_text = self._clean_for_detection(text)
            results = detect_langs(clean_text)

            if not results:
                return Language.UNKNOWN

            # Check if multiple languages above threshold
            significant_langs = [r for r in results if r.prob >= threshold]

            if len(significant_langs) >= 2:
                # Check if Korean and English are both present
                lang_codes = {r.lang for r in significant_langs}
                if "ko" in lang_codes and "en" in lang_codes:
                    return Language.MIXED

            # Return primary language
            top_lang = results[0].lang
            return self.LANGUAGE_MAP.get(top_lang, Language.UNKNOWN)

        except LangDetectException:
            return Language.UNKNOWN

    def _clean_for_detection(self, text: str) -> str:
        """Clean text for language detection.

        Args:
            text: Raw text

        Returns:
            Cleaned text
        """
        # Remove excessive whitespace
        import re

        text = re.sub(r"\s+", " ", text)

        # Remove URLs
        text = re.sub(r"http[s]?://\S+", "", text)

        # Remove email addresses
        text = re.sub(r"\S+@\S+", "", text)

        # Remove numbers (they don't help with language detection)
        text = re.sub(r"\d+", "", text)

        # Remove special characters but keep language-specific chars
        text = re.sub(r"[^\w\s\u3131-\u3163\uac00-\ud7a3]", " ", text)

        return text.strip()

    def get_language_name(self, language: Language) -> str:
        """Get human-readable language name.

        Args:
            language: Language enum

        Returns:
            Language name string
        """
        names = {
            Language.KOREAN: "Korean",
            Language.ENGLISH: "English",
            Language.MIXED: "Mixed (Korean/English)",
            Language.UNKNOWN: "Unknown",
        }
        return names.get(language, "Unknown")
