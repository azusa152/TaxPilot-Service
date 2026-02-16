import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.bootstrap_routes import router as bootstrap_router
from src.api.error_handlers import register_error_handlers
from src.api.evolution_routes import router as evolution_router
from src.api.health_routes import router as health_router
from src.api.income_routes import router as income_router
from src.api.ingestion_routes import router as ingestion_router
from src.api.llm_config_routes import router as llm_config_router
from src.api.notification_routes import router as notification_router
from src.api.nta_routes import router as nta_router
from src.api.profile_routes import router as profile_router
from src.api.tax_routes import router as tax_router
from src.api.user_routes import router as user_router
from src.logging_config import get_logger

logger = get_logger(__name__)


def create_app() -> FastAPI:
    application = FastAPI(
        title="TaxPilot Service",
        description="Self-Evolving, Agent-First Backend for Japanese Tax Calculation",
        version="0.1.0",
    )
    cors_origins = os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(application)
    application.include_router(health_router)
    application.include_router(user_router)
    application.include_router(income_router)
    application.include_router(profile_router)
    application.include_router(ingestion_router)
    application.include_router(tax_router)
    application.include_router(llm_config_router)
    application.include_router(nta_router)
    application.include_router(bootstrap_router)
    application.include_router(evolution_router)
    application.include_router(notification_router)
    return application


app = create_app()

logger.info("TaxPilot Service started")
