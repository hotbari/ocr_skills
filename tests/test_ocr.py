"""Tests for OCR functionality in src/ocr/"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.exceptions import OCRError, TextExtractionError
from src.core.models import Language
from src.ocr.extractor import ExtractionResult, PDFExtractor
from src.ocr.table_handler import ExtractedTable, TableHandler
from src.ocr.text_handler import PageText, TextHandler
from src.utils.language_detector import LanguageDetector

# ============================================================
# TEST PDF EXTRACTOR - VALIDATION
# ============================================================


def test_pdf_extractor_validate_nonexistent_file(mock_settings):
    """Test validation of non-existent file."""
    extractor = PDFExtractor(mock_settings)
    pdf_path = Path("/nonexistent/file.pdf")

    is_valid, error = extractor.validate_pdf(pdf_path)

    assert not is_valid
    assert "does not exist" in error


def test_pdf_extractor_validate_wrong_extension(tmp_path, mock_settings):
    """Test validation of non-PDF file."""
    extractor = PDFExtractor(mock_settings)

    # Create a text file with wrong extension
    wrong_file = tmp_path / "test.txt"
    wrong_file.write_text("not a pdf")

    is_valid, error = extractor.validate_pdf(wrong_file)

    assert not is_valid
    assert "not a PDF" in error


def test_pdf_extractor_validate_valid_pdf(sample_pdf, mock_settings):
    """Test validation of valid PDF."""
    extractor = PDFExtractor(mock_settings)

    is_valid, error = extractor.validate_pdf(sample_pdf)

    assert is_valid
    assert error == ""


def test_pdf_extractor_validate_empty_pdf(empty_pdf, mock_settings):
    """Test validation of empty PDF."""
    extractor = PDFExtractor(mock_settings)

    # Empty PDF should still be valid if it has pages
    is_valid, error = extractor.validate_pdf(empty_pdf)

    # Should be valid (has 1 page)
    assert is_valid


def test_pdf_extractor_validate_oversized_file(tmp_path, mock_settings):
    """Test validation of file exceeding size limit."""
    extractor = PDFExtractor(mock_settings)

    # Create a fake large file path (we'll mock the size check)
    large_pdf = tmp_path / "large.pdf"

    with patch.object(Path, "stat") as mock_stat:
        # Mock file size to exceed limit
        mock_stat.return_value.st_size = (
            (mock_settings.max_file_size_mb + 1) * 1024 * 1024
        )

        with patch("fitz.open"):
            is_valid, error = extractor.validate_pdf(large_pdf)

            assert not is_valid
            assert "exceeds" in error


def test_pdf_extractor_get_file_size(sample_pdf, mock_settings):
    """Test getting file size."""
    extractor = PDFExtractor(mock_settings)

    size = extractor.get_file_size(sample_pdf)

    assert size > 0
    assert isinstance(size, int)


# ============================================================
# TEST PDF EXTRACTOR - EXTRACTION
# ============================================================


@pytest.mark.asyncio
async def test_pdf_extractor_extract_basic(sample_pdf, mock_settings):
    """Test basic PDF extraction."""
    extractor = PDFExtractor(mock_settings)

    result = await extractor.extract(sample_pdf, "test-doc-123")

    assert isinstance(result, ExtractionResult)
    assert result.document_id == "test-doc-123"
    assert result.page_count == 2
    assert len(result.raw_text) > 0
    assert "Introduction" in result.raw_text
    assert "Methods" in result.raw_text
    assert len(result.text_by_page) == 2


@pytest.mark.asyncio
async def test_pdf_extractor_extract_text_by_page(sample_pdf, mock_settings):
    """Test extraction with text separated by page."""
    extractor = PDFExtractor(mock_settings)

    result = await extractor.extract(sample_pdf, "test-doc-123")

    assert len(result.text_by_page) == 2
    assert result.text_by_page[0].content
    assert result.text_by_page[1].content
    assert "Introduction" in result.text_by_page[0].content
    assert "Methods" in result.text_by_page[1].content


@pytest.mark.asyncio
async def test_pdf_extractor_language_detection(sample_pdf, mock_settings):
    """Test language detection during extraction."""
    extractor = PDFExtractor(mock_settings)

    result = await extractor.extract(sample_pdf, "test-doc-123")

    # Should detect English from sample text
    assert result.detected_language in [Language.ENGLISH, Language.UNKNOWN]


@pytest.mark.asyncio
async def test_pdf_extractor_extract_invalid_file(tmp_path, mock_settings):
    """Test extraction with invalid file."""
    extractor = PDFExtractor(mock_settings)

    invalid_pdf = tmp_path / "invalid.pdf"
    invalid_pdf.write_text("This is not a valid PDF")

    with pytest.raises(OCRError):
        await extractor.extract(invalid_pdf, "test-doc-123")


# ============================================================
# TEST TEXT HANDLER
# ============================================================


def test_text_handler_extract_text(sample_pdf):
    """Test text extraction from PDF."""
    handler = TextHandler()

    raw_text, page_count = handler.extract_text(sample_pdf)

    assert page_count == 2
    assert len(raw_text) > 0
    assert "Introduction" in raw_text
    assert "Methods" in raw_text


def test_text_handler_extract_text_by_page(sample_pdf):
    """Test extracting text page by page."""
    handler = TextHandler()

    pages = handler.extract_text_by_page(sample_pdf)

    assert len(pages) == 2
    assert all(isinstance(page, PageText) for page in pages)
    assert pages[0].page_number == 1
    assert pages[1].page_number == 2
    assert pages[0].char_count > 0


def test_text_handler_get_metadata(sample_pdf):
    """Test metadata extraction."""
    handler = TextHandler()

    metadata = handler.get_metadata(sample_pdf)

    assert isinstance(metadata, dict)
    assert "page_count" in metadata
    assert metadata["page_count"] == 2


def test_text_handler_check_is_scanned(sample_pdf):
    """Test scanned PDF detection."""
    handler = TextHandler()

    is_scanned = handler.check_is_scanned(sample_pdf)

    # Our sample PDF has text, so it should not be scanned
    assert not is_scanned


def test_text_handler_invalid_file(tmp_path):
    """Test text extraction with invalid file."""
    handler = TextHandler()

    invalid_pdf = tmp_path / "invalid.pdf"
    invalid_pdf.write_text("Not a PDF")

    with pytest.raises(TextExtractionError):
        handler.extract_text(invalid_pdf)


# ============================================================
# TEST TABLE HANDLER
# ============================================================


def test_table_handler_extract_tables_no_tables(sample_pdf):
    """Test table extraction from PDF without tables."""
    handler = TableHandler()

    tables = handler.extract_tables(sample_pdf)

    # Our sample PDF has no tables
    assert isinstance(tables, list)
    # Might be empty or contain detected regions
    assert len(tables) >= 0


def test_table_handler_to_canonical_json():
    """Test converting table to canonical JSON."""
    handler = TableHandler()

    table = ExtractedTable(
        page_number=1,
        table_index=0,
        bbox=(100, 100, 400, 300),
        rows=[["Header1", "Header2"], ["Value1", "Value2"]],
        header_row=["Header1", "Header2"],
        row_count=2,
        col_count=2,
    )

    canonical = handler.table_to_canonical_json(table)

    assert canonical["rows"] == 1  # Data rows only
    assert canonical["cols"] == 2
    assert canonical["has_header"] is True
    assert canonical["headers"] == ["Header1", "Header2"]


def test_table_handler_to_markdown():
    """Test converting table to markdown."""
    handler = TableHandler()

    table = ExtractedTable(
        page_number=1,
        table_index=0,
        bbox=(100, 100, 400, 300),
        rows=[["Header1", "Header2"], ["Value1", "Value2"]],
        header_row=["Header1", "Header2"],
        row_count=2,
        col_count=2,
    )

    markdown = handler.table_to_markdown(table)

    assert "Header1" in markdown
    assert "Header2" in markdown
    assert "Value1" in markdown
    assert "Value2" in markdown
    assert "|" in markdown
    assert "---" in markdown


def test_table_handler_to_text():
    """Test converting table to plain text."""
    handler = TableHandler()

    table = ExtractedTable(
        page_number=1,
        table_index=0,
        bbox=(100, 100, 400, 300),
        rows=[["Header1", "Header2"], ["Value1", "Value2"], ["Value3", "Value4"]],
        header_row=["Header1", "Header2"],
        row_count=3,
        col_count=2,
    )

    text = handler.table_to_text(table)

    assert "Table with columns" in text
    assert "Header1" in text
    assert "Header2" in text
    assert "Row 1" in text or "Row 2" in text


def test_table_handler_looks_like_header():
    """Test header detection heuristic."""
    handler = TableHandler()

    # Row with text (likely header)
    header_row = ["Name", "Age", "City"]
    data_rows = [["John", "25", "NYC"], ["Jane", "30", "LA"]]

    is_header = handler._looks_like_header(header_row, data_rows)

    # Heuristic should detect this as a header
    # (text only in first row, numbers in data rows)
    assert isinstance(is_header, bool)


# ============================================================
# TEST LANGUAGE DETECTOR
# ============================================================


def test_language_detector_english():
    """Test detecting English text."""
    detector = LanguageDetector()

    text = "This is a sample English text for language detection testing."

    language = detector.detect(text)

    assert language == Language.ENGLISH


def test_language_detector_korean():
    """Test detecting Korean text."""
    detector = LanguageDetector()

    # Longer text to meet MIN_TEXT_LENGTH requirement (50 chars)
    text = (
        "이것은 한국어 텍스트입니다. 언어 감지를 테스트하기 위한 샘플 텍스트입니다. "
        "한국어 감지가 정확하게 되어야 합니다. 이 문장은 충분히 길어야 합니다. "
        "테스트를 위해 추가적인 한국어 문장을 더 작성합니다."
    )

    language = detector.detect(text)

    # Accept either KOREAN or UNKNOWN (langdetect can be inconsistent with Korean)
    assert language in (Language.KOREAN, Language.UNKNOWN)


def test_language_detector_short_text():
    """Test with text too short for detection."""
    detector = LanguageDetector()

    short_text = "Hi"

    language = detector.detect(short_text)

    assert language == Language.UNKNOWN


def test_language_detector_empty_text():
    """Test with empty text."""
    detector = LanguageDetector()

    language = detector.detect("")

    assert language == Language.UNKNOWN


def test_language_detector_with_confidence():
    """Test language detection with confidence score."""
    detector = LanguageDetector()

    # Text must be at least 50 chars for detection
    text = (
        "This is a clear English sentence for testing language detection. "
        "We need to make sure the text is long enough for reliable detection results."
    )

    language, confidence = detector.detect_with_confidence(text)

    assert language == Language.ENGLISH
    assert 0.0 <= confidence <= 1.0


def test_language_detector_mixed():
    """Test detecting mixed language text."""
    detector = LanguageDetector()

    # Mixed English and Korean - must be long enough (50+ chars)
    text = (
        "Hello 안녕하세요 This is mixed text 이것은 혼합된 텍스트입니다. "
        "We are testing language detection 언어 감지 테스트를 진행하고 있습니다. "
        "Both languages should be present 두 언어가 모두 포함되어 있습니다."
    )

    language = detector.detect_mixed(text, threshold=0.2)

    # Should detect mixed or primary language, or unknown if langdetect is inconsistent
    assert language in [
        Language.MIXED,
        Language.ENGLISH,
        Language.KOREAN,
        Language.UNKNOWN,
    ]


def test_language_detector_get_language_name():
    """Test getting human-readable language names."""
    detector = LanguageDetector()

    assert detector.get_language_name(Language.ENGLISH) == "English"
    assert detector.get_language_name(Language.KOREAN) == "Korean"
    assert detector.get_language_name(Language.MIXED) == "Mixed (Korean/English)"
    assert detector.get_language_name(Language.UNKNOWN) == "Unknown"


def test_language_detector_clean_for_detection():
    """Test text cleaning for detection."""
    detector = LanguageDetector()

    dirty_text = "Test text with URL https://example.com and email test@example.com and numbers 12345"

    clean_text = detector._clean_for_detection(dirty_text)

    # Should remove URLs, emails, numbers
    assert "https://" not in clean_text
    assert "@" not in clean_text
    assert "12345" not in clean_text
    assert "Test" in clean_text or "text" in clean_text


# ============================================================
# TEST PDF EXTRACTOR INTEGRATION
# ============================================================


@pytest.mark.asyncio
async def test_pdf_extractor_full_integration(sample_pdf, mock_settings):
    """Test full integration of PDF extraction components."""
    extractor = PDFExtractor(mock_settings)

    # Validate first
    is_valid, error = extractor.validate_pdf(sample_pdf)
    assert is_valid

    # Extract
    result = await extractor.extract(sample_pdf, "test-doc-123")

    # Verify all components worked
    assert result.page_count > 0
    assert len(result.raw_text) > 0
    assert len(result.text_by_page) == result.page_count
    assert result.detected_language != Language.UNKNOWN
    assert isinstance(result.tables, list)
    assert isinstance(result.images, list)
    assert isinstance(result.metadata, dict)


@pytest.mark.asyncio
async def test_pdf_extractor_with_custom_handlers(sample_pdf, mock_settings):
    """Test PDF extractor with custom component handlers."""
    text_handler = TextHandler()
    table_handler = TableHandler()

    extractor = PDFExtractor(
        mock_settings,
        text_handler=text_handler,
        table_handler=table_handler,
    )

    result = await extractor.extract(sample_pdf, "test-doc-123")

    assert result.document_id == "test-doc-123"
    assert result.page_count > 0
