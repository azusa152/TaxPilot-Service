import tempfile
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from src.application.user_service import get_user
from src.domain.exceptions import TaxPilotError
from src.infrastructure.markitdown_adapter import MarkItDownAdapter
from src.infrastructure.models import IncomeEntry
from src.logging_config import get_logger

logger = get_logger(__name__)


class IngestionService:
    def __init__(self):
        self._adapter = MarkItDownAdapter()

    async def ingest_document(
        self,
        db: AsyncSession,
        user_id: str,
        filename: str,
        file_content: bytes,
    ) -> IncomeEntry:
        """Convert a financial document to Markdown and store it.

        Args:
            db: Database session.
            user_id: UUID of the user.
            filename: Original filename of the uploaded document.
            file_content: Raw bytes of the uploaded file.

        Returns:
            IncomeEntry with raw_content populated from MarkItDown conversion.
        """
        await get_user(db, user_id)

        if not filename or not self._adapter.is_supported(filename):
            supported = ", ".join(sorted(self._adapter.SUPPORTED_EXTENSIONS))
            raise TaxPilotError(
                400,
                "UNSUPPORTED_FILE_TYPE",
                f"File type not supported. Supported formats: {supported}",
            )

        suffix = Path(filename).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            markdown_text = self._adapter.convert_to_markdown(tmp_path)
        except RuntimeError as e:
            raise TaxPilotError(500, "INGESTION_FAILED", str(e)) from e
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        entry = IncomeEntry(
            user_id=user_id,
            payment_date=None,
            income_type="OTHER",
            gross_amount=0,
            source_file=filename,
            raw_content=markdown_text,
        )
        db.add(entry)
        await db.flush()

        logger.info("Ingested document '%s' for user %s, entry_id=%s", filename, user_id, entry.id)
        return entry
