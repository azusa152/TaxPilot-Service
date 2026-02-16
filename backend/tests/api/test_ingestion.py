from unittest.mock import patch


async def test_upload_unsupported_file_should_return_400(client):
    # Arrange: create user
    user_resp = await client.post("/users", json={"display_name": "Test"})
    user_id = user_resp.json()["id"]

    # Act: upload a .txt file (unsupported)
    response = await client.post(
        "/ingestion/upload",
        data={"user_id": user_id},
        files={"file": ("notes.txt", b"some text content", "text/plain")},
    )

    # Assert
    assert response.status_code == 400
    assert response.json()["error_code"] == "UNSUPPORTED_FILE_TYPE"


@patch("src.api.ingestion_routes.ingestion_service._adapter")
async def test_upload_pdf_should_return_201(mock_adapter, client):
    # Arrange
    user_resp = await client.post("/users", json={"display_name": "Test"})
    user_id = user_resp.json()["id"]

    mock_adapter.is_supported.return_value = True
    mock_adapter.convert_to_markdown.return_value = "| Month | Salary |\n| Jan | 500000 |"

    # Act
    response = await client.post(
        "/ingestion/upload",
        data={"user_id": user_id},
        files={"file": ("salary.pdf", b"%PDF-fake-content", "application/pdf")},
    )

    # Assert
    assert response.status_code == 201
    data = response.json()
    assert data["source_file"] == "salary.pdf"
    assert "raw_content" in data
