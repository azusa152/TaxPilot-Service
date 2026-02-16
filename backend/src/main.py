from fastapi import FastAPI

from src.api.health_routes import router as health_router
from src.logging_config import get_logger

logger = get_logger(__name__)


def create_app() -> FastAPI:
    application = FastAPI(
        title="TaxPilot Service",
        description="Self-Evolving, Agent-First Backend for Japanese Tax Calculation",
        version="0.1.0",
    )
    application.include_router(health_router)
    return application


app = create_app()

logger.info("TaxPilot Service started")
