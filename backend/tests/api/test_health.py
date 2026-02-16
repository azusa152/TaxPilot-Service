from unittest.mock import AsyncMock

from src.infrastructure.database import get_db
from src.main import app


async def test_health_should_return_healthy_when_db_connected(client):
    # Arrange
    mock_db = AsyncMock()
    mock_db.execute.return_value = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    # Act
    response = await client.get("/health")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"

    app.dependency_overrides.clear()


async def test_health_should_return_degraded_when_db_disconnected(client):
    # Arrange
    mock_db = AsyncMock()
    mock_db.execute.side_effect = Exception("Connection refused")

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    # Act
    response = await client.get("/health")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["database"] == "disconnected"

    app.dependency_overrides.clear()
