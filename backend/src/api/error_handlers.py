from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.domain.exceptions import TaxPilotError
from src.logging_config import get_logger

logger = get_logger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(TaxPilotError)
    async def taxpilot_error_handler(request: Request, exc: TaxPilotError):
        logger.warning("TaxPilotError: %s - %s", exc.error_code, exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error_code": exc.error_code, "detail": exc.detail},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error_code": "HTTP_ERROR", "detail": str(exc.detail)},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        detail = "; ".join(f"{e['loc'][-1]}: {e['msg']}" for e in errors)
        return JSONResponse(
            status_code=422,
            content={"error_code": "VALIDATION_ERROR", "detail": detail},
        )
