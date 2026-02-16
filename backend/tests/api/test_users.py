async def test_create_user_should_return_201(client):
    # Act
    response = await client.post("/users", json={"display_name": "Tanaka"})

    # Assert
    assert response.status_code == 201
    data = response.json()
    assert data["display_name"] == "Tanaka"
    assert "id" in data
    assert "created_at" in data


async def test_create_user_with_no_name_should_return_201(client):
    # Act
    response = await client.post("/users", json={})

    # Assert
    assert response.status_code == 201
    data = response.json()
    assert data["display_name"] is None


async def test_get_user_should_return_200(client):
    # Arrange
    create_resp = await client.post("/users", json={"display_name": "Suzuki"})
    user_id = create_resp.json()["id"]

    # Act
    response = await client.get(f"/users/{user_id}")

    # Assert
    assert response.status_code == 200
    assert response.json()["display_name"] == "Suzuki"


async def test_get_user_not_found_should_return_404(client):
    # Act
    response = await client.get("/users/nonexistent-id")

    # Assert
    assert response.status_code == 404
    assert response.json()["error_code"] == "USER_NOT_FOUND"
