from pathlib import Path

from markitdown import MarkItDown

from src.logging_config import get_logger

logger = get_logger(__name__)


class MarkItDownAdapter:
    """Adapter for Microsoft MarkItDown document-to-Markdown converter."""

    SUPPORTED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff"}

    def __init__(self):
        self._converter = MarkItDown()

    def is_supported(self, filename: str) -> bool:
        ext = Path(filename).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS

    def convert_to_markdown(self, file_path: str) -> str:
        """Convert a file to Markdown text.

        Args:
            file_path: Path to the file on disk.

        Returns:
            Extracted Markdown text preserving table structures.

        Raises:
            ValueError: If the file type is not supported.
            RuntimeError: If MarkItDown conversion fails.
        """
        if not self.is_supported(file_path):
            ext = Path(file_path).suffix
            raise ValueError(f"Unsupported file type: '{ext}'. Supported: {self.SUPPORTED_EXTENSIONS}")

        try:
            result = self._converter.convert(file_path)
            logger.info("Successfully converted '%s' to Markdown (%d chars)", file_path, len(result.text_content))
            return result.text_content
        except Exception as e:
            logger.error("MarkItDown conversion failed for '%s': %s", file_path, e)
            raise RuntimeError(f"Document conversion failed: {e}") from e
