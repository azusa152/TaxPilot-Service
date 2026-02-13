"""Document ingestion using Microsoft MarkItDown."""

from markitdown import MarkItDown

from src.logging_config import get_logger

logger = get_logger(__name__)


class DocumentIngestor:
    """Converts financial documents to Markdown text.

    Uses Microsoft MarkItDown to extract structured text content
    from PDF, Excel, and image files while preserving table structures.
    """

    def __init__(self) -> None:
        """Initialize the MarkItDown converter."""
        self._converter = MarkItDown()
        logger.info("DocumentIngestor initialized")

    def convert_to_markdown(self, file_path: str) -> str:
        """Convert a document file to Markdown text.

        Args:
            file_path: Path to the input file (PDF, Image, Excel, etc.).

        Returns:
            Extracted Markdown text content preserving table structures.

        Raises:
            FileNotFoundError: If the specified file does not exist.
            ValueError: If the file format is not supported.
        """
        logger.info("Converting file to markdown: %s", file_path)
        result = self._converter.convert(file_path)
        logger.info("Conversion complete: %s", file_path)
        return result.text_content
