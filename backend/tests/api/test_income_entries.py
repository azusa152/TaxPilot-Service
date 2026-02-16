async def test_create_income_entry_should_return_201(client):
    # Arrange
    user_resp = await client.post("/users", json={"display_name": "Test"})
    user_id = user_resp.json()["id"]

    # Act
    response = await client.post(
        "/income-entries",
        json={
            "user_id": user_id,
            "payment_date": "2024-01-25",
            "income_type": "SALARY",
            "gross_amount": 500000,
            "social_insurance": 40000,
            "withholding_tax": 15000,
        },
    )

    # Assert
    assert response.status_code == 201
    data = response.json()
    assert data["gross_amount"] == 500000
    assert data["income_type"] == "SALARY"


async def test_create_income_entry_invalid_type_should_return_422(client):
    # Arrange
    user_resp = await client.post("/users", json={"display_name": "Test"})
    user_id = user_resp.json()["id"]

    # Act
    response = await client.post(
        "/income-entries",
        json={
            "user_id": user_id,
            "payment_date": "2024-01-25",
            "income_type": "INVALID",
            "gross_amount": 500000,
        },
    )

    # Assert
    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"


async def test_create_income_entry_for_nonexistent_user_should_return_404(client):
    # Act
    response = await client.post(
        "/income-entries",
        json={
            "user_id": "nonexistent-id",
            "payment_date": "2024-01-25",
            "income_type": "SALARY",
            "gross_amount": 500000,
        },
    )

    # Assert
    assert response.status_code == 404
    assert response.json()["error_code"] == "USER_NOT_FOUND"


async def test_list_income_entries_should_return_200(client):
    # Arrange
    user_resp = await client.post("/users", json={"display_name": "Test"})
    user_id = user_resp.json()["id"]
    await client.post(
        "/income-entries",
        json={"user_id": user_id, "payment_date": "2024-01-25", "income_type": "SALARY", "gross_amount": 500000},
    )
    await client.post(
        "/income-entries",
        json={"user_id": user_id, "payment_date": "2024-02-25", "income_type": "SALARY", "gross_amount": 500000},
    )

    # Act
    response = await client.get(f"/income-entries/{user_id}")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


async def test_list_income_entries_for_nonexistent_user_should_return_404(client):
    # Act
    response = await client.get("/income-entries/nonexistent-id")

    # Assert
    assert response.status_code == 404


async def test_get_income_entry_should_return_200(client):
    # Arrange
    user_resp = await client.post("/users", json={"display_name": "Test"})
    user_id = user_resp.json()["id"]
    entry_resp = await client.post(
        "/income-entries",
        json={"user_id": user_id, "payment_date": "2024-01-25", "income_type": "SALARY", "gross_amount": 500000},
    )
    entry_id = entry_resp.json()["id"]

    # Act
    response = await client.get(f"/income-entries/{user_id}/{entry_id}")

    # Assert
    assert response.status_code == 200
    assert response.json()["id"] == entry_id


async def test_get_income_entry_not_found_should_return_404(client):
    # Arrange
    user_resp = await client.post("/users", json={"display_name": "Test"})
    user_id = user_resp.json()["id"]

    # Act
    response = await client.get(f"/income-entries/{user_id}/99999")

    # Assert
    assert response.status_code == 404
    assert response.json()["error_code"] == "INCOME_ENTRY_NOT_FOUND"


async def test_delete_income_entry_should_return_204(client):
    # Arrange
    user_resp = await client.post("/users", json={"display_name": "Test"})
    user_id = user_resp.json()["id"]
    entry_resp = await client.post(
        "/income-entries",
        json={"user_id": user_id, "payment_date": "2024-06-15", "income_type": "BONUS", "gross_amount": 1000000},
    )
    entry_id = entry_resp.json()["id"]

    # Act
    response = await client.delete(f"/income-entries/{user_id}/{entry_id}")

    # Assert
    assert response.status_code == 204

    # Verify it's gone
    get_resp = await client.get(f"/income-entries/{user_id}/{entry_id}")
    assert get_resp.status_code == 404
