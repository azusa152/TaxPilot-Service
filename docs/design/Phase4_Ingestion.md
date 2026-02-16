# Phase 4: Document Ingestion Pipeline
**Goal:** Integrate Microsoft MarkItDown to convert uploaded financial documents (PDF, Excel, images) into structured Markdown, and store the extracted content in the database.

**Depends on:** Phase 3 (CRUD API must be working; `IncomeEntry` model with `raw_content` column)
**Produces:** Upload endpoint, MarkItDown adapter, ingestion service, file validation

---

## Context

TaxPilot's **Universal Ingestion** pillar means users (or Agents) can upload salary slips, transaction logs, and other financial documents. The system converts them to Markdown text using **Microsoft MarkItDown**, preserving table structures for downstream parsing.

The extracted Markdown is stored in `IncomeEntry.raw_content` for audit trail and re-parsing if extraction logic improves.

**Data flow:**

```
Agent/UI                    API                    Ingestion Service           MarkItDown Adapter
   │                        │                            │                          │
   │── POST /ingestion/upload ──►│                       │                          │
   │   (file + user_id)     │── validate file type ──►   │                          │
   │                        │                     ── convert_to_markdown() ──►       │
   │                        │                            │          ── markitdown.convert() ──►│
   │                        │                            │◄── markdown_text ────────│
   │                        │                     ◄── store in DB ──────────        │
   │◄── IncomeEntryResponse │◄───────────────────────────│                          │
```

---

## Tasks

### Task 4.1: MarkItDown Adapter (Infrastructure Layer)

**File:** `backend/src/infrastructure/markitdown_adapter.py`

This adapter wraps the `markitdown` library. It is the **only** place that imports `markitdown` — the rest of the codebase depends on a clean interface.

```python
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
            logger.info(f"Successfully converted '{file_path}' to Markdown ({len(result.text_content)} chars)")
            return result.text_content
        except Exception as e:
            logger.error(f"MarkItDown conversion failed for '{file_path}': {e}")
            raise RuntimeError(f"Document conversion failed: {e}") from e
```

### Task 4.2: Ingestion Service (Application Layer)

**File:** `backend/src/application/ingestion_service.py`

Orchestrates: receive file -> save temp -> convert via adapter -> create IncomeEntry with raw_content.

```python
import tempfile
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.error_handlers import TaxPilotError
from src.application.user_service import get_user
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
        file: UploadFile,
    ) -> IncomeEntry:
        """Upload and convert a financial document to Markdown.

        Args:
            db: Database session.
            user_id: UUID of the user.
            file: Uploaded file (PDF, Excel, image).

        Returns:
            IncomeEntry with raw_content populated from MarkItDown conversion.
        """
        # Validate user exists
        await get_user(db, user_id)

        # Validate file type
        if not file.filename or not self._adapter.is_supported(file.filename):
            supported = ", ".join(sorted(self._adapter.SUPPORTED_EXTENSIONS))
            raise TaxPilotError(
                400,
                "UNSUPPORTED_FILE_TYPE",
                f"File type not supported. Supported formats: {supported}",
            )

        # Save to temp file for MarkItDown processing
        suffix = Path(file.filename).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            markdown_text = self._adapter.convert_to_markdown(tmp_path)
        except RuntimeError as e:
            raise TaxPilotError(500, "INGESTION_FAILED", str(e))
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        # Create IncomeEntry with raw_content (no financial fields yet — agent fills those)
        entry = IncomeEntry(
            user_id=user_id,
            payment_date=None,  # To be filled by agent after parsing markdown
            income_type="OTHER",
            gross_amount=0,
            source_file=file.filename,
            raw_content=markdown_text,
        )
        db.add(entry)
        await db.flush()

        logger.info(f"Ingested document '{file.filename}' for user {user_id}, entry_id={entry.id}")
        return entry
```

**Design note:** The ingestion endpoint creates an IncomeEntry with `raw_content` populated but financial fields zeroed out. The Agent (or user) then parses the Markdown and updates the entry with actual amounts via `PUT` or a future extraction endpoint.

### Task 4.3: Upload Endpoint

**File:** `backend/src/api/ingestion_routes.py`

```python
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ingestion_service import IngestionService
from src.domain.schemas import IncomeEntryResponse
from src.infrastructure.database import get_db

router = APIRouter(prefix="/ingestion", tags=["Ingestion"])

ingestion_service = IngestionService()


@router.post(
    "/upload",
    response_model=IncomeEntryResponse,
    status_code=201,
    summary="Upload a financial document for MarkItDown processing",
)
async def upload_document(
    user_id: str = Form(description="UUID of the user this document belongs to"),
    file: UploadFile = File(description="Financial document (PDF, Excel, or image)"),
    db: AsyncSession = Depends(get_db),
):
    entry = await ingestion_service.ingest_document(db, user_id, file)
    return entry
```

**Update `backend/src/main.py`** to include the ingestion router:

```python
from src.api.ingestion_routes import router as ingestion_router

# Inside create_app():
application.include_router(ingestion_router)
```

### Task 4.4: Model Update (if needed)

The `IncomeEntry` model from Phase 2 already has `payment_date` as non-nullable. For ingestion, we need to allow `None` initially since the document hasn't been parsed yet.

**Option A:** Make `payment_date` nullable in the model:

```python
payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
```

**Option B:** Set a placeholder date during ingestion and require the agent to update it.

**Recommendation:** Option A — nullable `payment_date` is cleaner. Generate a new Alembic migration if changing the column.

### Task 4.5: Tests

**File:** `backend/tests/infrastructure/test_markitdown_adapter.py`

```python
from unittest.mock import MagicMock, patch

import pytest

from src.infrastructure.markitdown_adapter import MarkItDownAdapter


def test_is_supported_should_accept_pdf():
    adapter = MarkItDownAdapter()
    assert adapter.is_supported("salary_slip.pdf") is True


def test_is_supported_should_reject_txt():
    adapter = MarkItDownAdapter()
    assert adapter.is_supported("notes.txt") is False


def test_is_supported_should_accept_xlsx():
    adapter = MarkItDownAdapter()
    assert adapter.is_supported("transactions.xlsx") is True


@patch("src.infrastructure.markitdown_adapter.MarkItDown")
def test_convert_should_return_markdown(mock_markitdown_class):
    mock_instance = MagicMock()
    mock_result = MagicMock()
    mock_result.text_content = "| Date | Amount |\n|---|---|\n| 2024-01 | 500000 |"
    mock_instance.convert.return_value = mock_result
    mock_markitdown_class.return_value = mock_instance

    adapter = MarkItDownAdapter()
    adapter._converter = mock_instance

    result = adapter.convert_to_markdown("salary.pdf")
    assert "500000" in result


def test_convert_unsupported_should_raise_value_error():
    adapter = MarkItDownAdapter()
    with pytest.raises(ValueError, match="Unsupported file type"):
        adapter.convert_to_markdown("readme.txt")
```

**File:** `backend/tests/api/test_ingestion.py`

```python
from unittest.mock import AsyncMock, patch

import pytest


async def test_upload_unsupported_file_should_return_400(client):
    # Arrange: create user
    user_resp = await client.post("/users", json={"display_name": "Test"})
    user_id = user_resp.json()["id"]

    # Act: upload a .txt file (unsupported)
    response = await client.post(
        "/ingestion/upload",
        data={"user_id": user_id},
        files={"file": ("notes.txt", b"some text content", "text/plain")},
    )

    # Assert
    assert response.status_code == 400
    assert response.json()["error_code"] == "UNSUPPORTED_FILE_TYPE"


@patch("src.application.ingestion_service.MarkItDownAdapter")
async def test_upload_pdf_should_return_201(mock_adapter_class, client):
    # Arrange
    user_resp = await client.post("/users", json={"display_name": "Test"})
    user_id = user_resp.json()["id"]

    mock_instance = mock_adapter_class.return_value
    mock_instance.is_supported.return_value = True
    mock_instance.convert_to_markdown.return_value = "| Month | Salary |\n| Jan | 500000 |"

    # Act
    response = await client.post(
        "/ingestion/upload",
        data={"user_id": user_id},
        files={"file": ("salary.pdf", b"%PDF-fake-content", "application/pdf")},
    )

    # Assert
    assert response.status_code == 201
    data = response.json()
    assert data["source_file"] == "salary.pdf"
    assert "raw_content" in data
```

---

## Acceptance Criteria

1. `POST /ingestion/upload` with a PDF file returns 201 and the response includes `raw_content` with Markdown text.
2. Uploading an unsupported file type (e.g., `.txt`) returns 400 with `error_code: "UNSUPPORTED_FILE_TYPE"`.
3. If MarkItDown fails to convert, the endpoint returns 500 with `error_code: "INGESTION_FAILED"`.
4. The `source_file` field on the created IncomeEntry stores the original filename.
5. MarkItDown is only imported in `markitdown_adapter.py` — nowhere else in the codebase.
6. `make test` passes all ingestion tests.
