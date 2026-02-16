from fastapi import FastAPI

from src.api.error_handlers import register_error_handlers
from src.api.health_routes import router as health_router
from src.api.income_routes import router as income_router
from src.api.ingestion_routes import router as ingestion_router
from src.api.profile_routes import router as profile_router
from src.api.user_routes import router as user_router
from src.logging_config import get_logger

logger = get_logger(__name__)


def create_app() -> FastAPI:
    application = FastAPI(
        title="TaxPilot Service",
        description="Self-Evolving, Agent-First Backend for Japanese Tax Calculation",
        version="0.1.0",
    )
    register_error_handlers(application)
    application.include_router(health_router)
    application.include_router(user_router)
    application.include_router(income_router)
    application.include_router(profile_router)
    application.include_router(ingestion_router)
    return application


app = create_app()

logger.info("TaxPilot Service started")
