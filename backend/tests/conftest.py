"""Shared pytest fixtures for TaxPilot backend tests."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def client():
    """Provide an async test client for the FastAPI app.

    Yields:
        AsyncClient bound to the FastAPI app via ASGITransport.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
