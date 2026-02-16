async def test_calculate_tax_should_return_result(client):
    # Arrange: create user, income entries, and tax profile
    user_resp = await client.post("/users", json={"display_name": "Tanaka"})
    user_id = user_resp.json()["id"]

    for month in range(1, 13):
        await client.post(
            "/income-entries",
            json={
                "user_id": user_id,
                "payment_date": f"2024-{month:02d}-25",
                "income_type": "SALARY",
                "gross_amount": 500_000,
            },
        )

    await client.put(
        f"/tax-profiles/{user_id}/2024",
        json={
            "has_spouse": True,
            "dependents_count": 1,
            "social_insurance_premium": 600_000,
            "life_insurance_premium": 50_000,
            "ideco_monthly_contribution": 23_000,
        },
    )

    # Act
    response = await client.post(f"/tax/calculate/{user_id}/2024")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["gross_salary"] == 6_000_000
    assert data["income_tax"] > 0
    assert data["furusato_limit"] > 2_000
    assert data["taxable_income"] >= 0


async def test_calculate_tax_no_profile_should_return_404(client):
    user_resp = await client.post("/users", json={"display_name": "Test"})
    user_id = user_resp.json()["id"]

    response = await client.post(f"/tax/calculate/{user_id}/2024")
    assert response.status_code == 404
    assert response.json()["error_code"] == "TAX_PROFILE_NOT_FOUND"


async def test_register_algorithm_should_return_201(client):
    response = await client.post(
        "/algorithms",
        json={
            "function_name": "calc_salary_income_deduction",
            "version": "2024.1",
            "code_content": "def calc_salary_income_deduction(gross): return 550_000",
            "source_law_hash": "abc123",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["function_name"] == "calc_salary_income_deduction"
    assert data["status"] == "DRAFT"


async def test_activate_algorithm_should_archive_previous(client):
    # Register two versions
    resp1 = await client.post(
        "/algorithms",
        json={
            "function_name": "calc_basic_deduction",
            "version": "2024.1",
            "code_content": "def calc_basic_deduction(income): return 480_000",
        },
    )
    algo1_id = resp1.json()["id"]

    resp2 = await client.post(
        "/algorithms",
        json={
            "function_name": "calc_basic_deduction",
            "version": "2024.2",
            "code_content": "def calc_basic_deduction(income): return 480_000",
        },
    )
    algo2_id = resp2.json()["id"]

    # Activate first
    await client.put(f"/algorithms/{algo1_id}/activate")

    # Activate second — should archive first
    resp_activate = await client.put(f"/algorithms/{algo2_id}/activate")
    assert resp_activate.status_code == 200
    assert resp_activate.json()["status"] == "ACTIVE"

    # Get active — should be version 2024.2
    resp_get = await client.get("/algorithms/calc_basic_deduction")
    assert resp_get.status_code == 200
    assert resp_get.json()["version"] == "2024.2"


async def test_list_algorithms_should_return_200(client):
    response = await client.get("/algorithms")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
