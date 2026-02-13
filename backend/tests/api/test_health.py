"""Smoke tests for API health check endpoint."""

import pytest


@pytest.mark.asyncio
async def test_health_should_return_healthy_status(client):
    """Verify health endpoint returns healthy status.

    Arrange: Test client connected to the FastAPI app.
    Act: Send GET request to /health.
    Assert: Response is 200 with expected status fields.
    """
    # Act
    response = await client.get("/health")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
