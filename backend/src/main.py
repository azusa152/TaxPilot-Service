"""FastAPI application entry point for TaxPilot Service."""

from fastapi import FastAPI

from src.api.routes import router

app = FastAPI(
    title="TaxPilot Service",
    description="Self-Evolving Agent-First Backend for Japanese Tax Calculation",
    version="0.1.0",
)

app.include_router(router)
