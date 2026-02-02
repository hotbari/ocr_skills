"""Table extraction from PDF using PyMuPDF."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import fitz
import structlog

from src.core.exceptions import TableExtractionError

logger = structlog.get_logger()


@dataclass
class ExtractedTable:
    """Extracted table with position and content."""

    page_number: int
    table_index: int
    bbox: tuple[float, float, float, float]
    rows: list[list[str]]
    header_row: Optional[list[str]] = None
    row_count: int = 0
    col_count: int = 0


@dataclass
class TableCanonicalJSON:
    """Canonical JSON representation of a table."""

    rows: int
    cols: int
    headers: list[str] = field(default_factory=list)
    data: list[list[str]] = field(default_factory=list)
    has_header: bool = False


class TableHandler:
    """Handles table extraction from PDF documents."""

    def __init__(self):
        self.logger = logger.bind(component="TableHandler")

    def extract_tables(self, pdf_path: Path) -> list[ExtractedTable]:
        """Extract all tables from PDF.

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of ExtractedTable objects

        Raises:
            TableExtractionError: If extraction fails
        """
        try:
            self.logger.info("Extracting tables from PDF", path=str(pdf_path))

            doc = fitz.open(str(pdf_path))
            all_tables = []
            table_index = 0

            for page_num in range(len(doc)):
                page = doc[page_num]

                # Use PyMuPDF's table finder
                tables = page.find_tables()

                for table in tables:
                    # Extract table data
                    table_data = table.extract()

                    if not table_data or len(table_data) == 0:
                        continue

                    # Determine header
                    header_row = None
                    rows = table_data

                    # Simple heuristic: if first row looks like headers
                    if len(table_data) > 1:
                        first_row = table_data[0]
                        if self._looks_like_header(first_row, table_data[1:]):
                            header_row = first_row
                            rows = table_data

                    extracted = ExtractedTable(
                        page_number=page_num + 1,
                        table_index=table_index,
                        bbox=table.bbox,
                        rows=rows,
                        header_row=header_row,
                        row_count=len(rows),
                        col_count=len(rows[0]) if rows else 0,
                    )

                    all_tables.append(extracted)
                    table_index += 1

            doc.close()

            self.logger.info("Table extraction complete", table_count=len(all_tables))
            return all_tables

        except Exception as e:
            self.logger.error("Table extraction failed", error=str(e))
            raise TableExtractionError(f"Failed to extract tables: {e}")

    def _looks_like_header(
        self, first_row: list[str], remaining_rows: list[list[str]]
    ) -> bool:
        """Heuristic to determine if first row is a header.

        Args:
            first_row: First row of table
            remaining_rows: Remaining rows

        Returns:
            True if first row appears to be a header
        """
        if not first_row or not remaining_rows:
            return False

        # Check if first row has different characteristics
        first_row_text = " ".join(str(cell) for cell in first_row if cell)

        # Headers are often shorter
        avg_first_len = len(first_row_text) / len(first_row) if first_row else 0

        # Check if numeric content differs
        first_has_numbers = any(
            any(c.isdigit() for c in str(cell)) for cell in first_row if cell
        )
        rest_has_numbers = any(
            any(c.isdigit() for c in str(cell))
            for row in remaining_rows[:3]
            for cell in row
            if cell
        )

        # If first row has no numbers but rest does, likely header
        if not first_has_numbers and rest_has_numbers:
            return True

        # If first row is shorter text, might be header
        if avg_first_len < 20:
            return True

        return False

    def table_to_canonical_json(self, table: ExtractedTable) -> dict[str, Any]:
        """Convert extracted table to canonical JSON format.

        Args:
            table: Extracted table

        Returns:
            Canonical JSON representation
        """
        headers = []
        data = []
        has_header = False

        if table.header_row:
            headers = [str(cell) if cell else "" for cell in table.header_row]
            has_header = True
            # Skip header row in data if it's the same as first row
            if table.rows and table.rows[0] == table.header_row:
                data = [
                    [str(cell) if cell else "" for cell in row]
                    for row in table.rows[1:]
                ]
            else:
                data = [
                    [str(cell) if cell else "" for cell in row] for row in table.rows
                ]
        else:
            data = [[str(cell) if cell else "" for cell in row] for row in table.rows]

        return {
            "rows": len(data),
            "cols": table.col_count,
            "headers": headers,
            "data": data,
            "has_header": has_header,
            "page_number": table.page_number,
            "bbox": {
                "x0": table.bbox[0],
                "y0": table.bbox[1],
                "x1": table.bbox[2],
                "y1": table.bbox[3],
            },
        }

    def table_to_markdown(self, table: ExtractedTable) -> str:
        """Convert extracted table to markdown format.

        Args:
            table: Extracted table

        Returns:
            Markdown representation
        """
        if not table.rows:
            return ""

        lines = []

        # Determine headers
        if table.header_row:
            headers = [str(cell) if cell else "" for cell in table.header_row]
            data_rows = (
                table.rows[1:]
                if table.rows and table.rows[0] == table.header_row
                else table.rows
            )
        else:
            # Use first row as header
            headers = [str(cell) if cell else "" for cell in table.rows[0]]
            data_rows = table.rows[1:]

        # Header row
        lines.append("| " + " | ".join(headers) + " |")

        # Separator
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

        # Data rows
        for row in data_rows:
            cells = [str(cell) if cell else "" for cell in row]
            # Ensure same number of columns
            while len(cells) < len(headers):
                cells.append("")
            cells = cells[: len(headers)]  # Truncate if too many
            lines.append("| " + " | ".join(cells) + " |")

        return "\n".join(lines)

    def table_to_text(self, table: ExtractedTable) -> str:
        """Convert extracted table to plain text for retrieval.

        Args:
            table: Extracted table

        Returns:
            Plain text representation
        """
        if not table.rows:
            return ""

        text_parts = []

        # Add header info if present
        if table.header_row:
            headers = [str(cell) for cell in table.header_row if cell]
            text_parts.append(f"Table with columns: {', '.join(headers)}")

        # Add row summaries
        for i, row in enumerate(table.rows[:5]):  # First 5 rows for retrieval
            cells = [str(cell) for cell in row if cell]
            if cells:
                text_parts.append(f"Row {i + 1}: {', '.join(cells)}")

        if len(table.rows) > 5:
            text_parts.append(f"... and {len(table.rows) - 5} more rows")

        return ". ".join(text_parts)
