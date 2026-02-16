async def test_upsert_tax_profile_should_return_200(client):
    # Arrange
    user_resp = await client.post("/users", json={"display_name": "Test"})
    user_id = user_resp.json()["id"]

    # Act
    response = await client.put(
        f"/tax-profiles/{user_id}/2024",
        json={
            "has_spouse": True,
            "dependents_count": 2,
            "social_insurance_premium": 600000,
            "additional_attributes": {"fixed_tax_cut_eligible": True},
        },
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["has_spouse"] is True
    assert data["dependents_count"] == 2
    assert data["additional_attributes"]["fixed_tax_cut_eligible"] is True


async def test_upsert_tax_profile_should_be_idempotent(client):
    # Arrange
    user_resp = await client.post("/users", json={"display_name": "Test"})
    user_id = user_resp.json()["id"]

    payload = {
        "has_spouse": False,
        "dependents_count": 1,
        "social_insurance_premium": 400000,
    }

    # Act — create
    first_resp = await client.put(f"/tax-profiles/{user_id}/2024", json=payload)
    first_id = first_resp.json()["id"]

    # Act — update same profile
    payload["dependents_count"] = 3
    second_resp = await client.put(f"/tax-profiles/{user_id}/2024", json=payload)

    # Assert — same record updated
    assert second_resp.status_code == 200
    assert second_resp.json()["id"] == first_id
    assert second_resp.json()["dependents_count"] == 3


async def test_get_tax_profile_should_return_200(client):
    # Arrange
    user_resp = await client.post("/users", json={"display_name": "Test"})
    user_id = user_resp.json()["id"]
    await client.put(
        f"/tax-profiles/{user_id}/2024",
        json={"has_spouse": True, "dependents_count": 1},
    )

    # Act
    response = await client.get(f"/tax-profiles/{user_id}/2024")

    # Assert
    assert response.status_code == 200
    assert response.json()["has_spouse"] is True


async def test_get_tax_profile_not_found_should_return_404(client):
    # Arrange
    user_resp = await client.post("/users", json={"display_name": "Test"})
    user_id = user_resp.json()["id"]

    # Act
    response = await client.get(f"/tax-profiles/{user_id}/2024")

    # Assert
    assert response.status_code == 404
    assert response.json()["error_code"] == "TAX_PROFILE_NOT_FOUND"


async def test_get_tax_profile_for_nonexistent_user_should_return_404(client):
    # Act
    response = await client.get("/tax-profiles/nonexistent-id/2024")

    # Assert
    assert response.status_code == 404
    assert response.json()["error_code"] == "USER_NOT_FOUND"


async def test_get_profile_definition_not_found_should_return_404(client):
    # Act
    response = await client.get("/profile-definition/9999")

    # Assert
    assert response.status_code == 404
    assert response.json()["error_code"] == "PROFILE_DEFINITION_NOT_FOUND"
