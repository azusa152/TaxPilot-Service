"""Tests for api/bootstrap_routes.py — Bootstrap admin endpoints."""


class TestGetStatus:
    """Tests for GET /admin/bootstrap/status."""

    async def test_returns_empty_status_before_bootstrap(self, client):
        response = await client.get("/admin/bootstrap/status")
        assert response.status_code == 200

        data = response.json()
        assert data["bootstrap_completed"] is False
        assert data["registered_algorithms"] == []
        assert data["verification_available"] is False

    async def test_returns_registered_after_bootstrap(self, client):
        """After running bootstrap (skip crawl + skip verify), status shows registered algorithms."""
        run_resp = await client.post(
            "/admin/bootstrap/run?skip_crawl=true&skip_verification=true"
        )
        assert run_resp.status_code == 200

        response = await client.get("/admin/bootstrap/status")
        data = response.json()
        assert data["bootstrap_completed"] is True
        assert len(data["registered_algorithms"]) == 9


class TestPostRun:
    """Tests for POST /admin/bootstrap/run."""

    async def test_run_bootstrap_skip_all(self, client):
        """Running bootstrap with all skips should succeed."""
        response = await client.post(
            "/admin/bootstrap/run?skip_crawl=true&skip_verification=true"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["step2_seed"]["registered"] == 9
        assert data["step3_verify"] == "skipped"

    async def test_run_bootstrap_is_idempotent(self, client):
        """Running bootstrap twice should not duplicate entries."""
        await client.post(
            "/admin/bootstrap/run?skip_crawl=true&skip_verification=true"
        )
        response = await client.post(
            "/admin/bootstrap/run?skip_crawl=true&skip_verification=true"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["step2_seed"]["registered"] == 0
        assert data["step2_seed"]["skipped"] == 9


class TestGetReport:
    """Tests for GET /admin/bootstrap/report."""

    async def test_returns_empty_report_before_verification(self, client):
        response = await client.get("/admin/bootstrap/report")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 0
        assert data["reports"] == []
