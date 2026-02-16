from unittest.mock import AsyncMock, patch

from src.infrastructure.nta_monitor import NtaMonitor


@patch("src.infrastructure.nta_monitor.httpx.AsyncClient")
async def test_check_for_changes_first_run_should_return_no_changes(mock_client_class):
    mock_response = AsyncMock()
    mock_response.content = b"<html>tax rates page</html>"
    mock_response.raise_for_status = lambda: None

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client_class.return_value = mock_client

    monitor = NtaMonitor()
    changes = await monitor.check_for_changes()

    # First run: no previous hash, so no changes detected
    assert changes == []
    assert len(monitor.get_known_hashes()) > 0


@patch("src.infrastructure.nta_monitor.httpx.AsyncClient")
async def test_check_for_changes_second_run_with_change_should_detect(mock_client_class):
    call_count = 0

    async def mock_get(url):
        nonlocal call_count
        call_count += 1
        response = AsyncMock()
        # Return different content on second call cycle
        if call_count <= 2:
            response.content = b"<html>original content</html>"
        else:
            response.content = b"<html>updated content</html>"
        response.raise_for_status = lambda: None
        return response

    mock_client = AsyncMock()
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client_class.return_value = mock_client

    monitor = NtaMonitor()

    # First run: establish baseline
    changes1 = await monitor.check_for_changes()
    assert changes1 == []

    # Second run: content changed
    changes2 = await monitor.check_for_changes()
    assert len(changes2) > 0
    assert changes2[0]["name"] in ("income_tax_rates", "salary_deduction")
