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
    content = await file.read()
    entry = await ingestion_service.ingest_document(db, user_id, file.filename or "", content)
    return entry
