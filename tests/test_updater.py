from unittest.mock import AsyncMock, patch
import pytest
from cyc.updater import (
    parse_semver,
    is_newer_version,
    fetch_latest_version,
    detect_install_method,
    perform_update,
)

def test_semver_parsing_and_comparison():
    assert parse_semver("1.4.0") == (1, 4, 0)
    assert parse_semver("v1.4.1") == (1, 4, 1)
    assert parse_semver("2.0.0-alpha") == (2, 0, 0)
    assert parse_semver("invalid") == (0, 0, 0)

    assert is_newer_version("1.4.0", "1.4.1") is True
    assert is_newer_version("1.4.0", "1.5.0") is True
    assert is_newer_version("1.4.0", "2.0.0") is True
    assert is_newer_version("1.4.0", "1.4.0") is False
    assert is_newer_version("1.4.1", "1.4.0") is False


@pytest.mark.asyncio
async def test_fetch_latest_version_mocked():
    # 1. Successful check
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = '[project]\nname = "cyc"\nversion = "9.9.9"\n'
        mock_get.return_value = mock_resp

        res = await fetch_latest_version()
        assert res.error is None
        assert res.latest_version == "9.9.9"
        assert res.has_update is True

    # 2. HTTP error
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        res = await fetch_latest_version()
        assert res.has_update is False
        assert "404" in (res.error or "")


def test_detect_install_method():
    method = detect_install_method()
    assert method in ("git_repo", "uv_tool", "uv_tool_local", "pipx", "pip")


@pytest.mark.asyncio
async def test_perform_update_already_up_to_date():
    with patch("cyc.updater.fetch_latest_version", new_callable=AsyncMock) as mock_fetch:
        from cyc.updater import UpdateCheckResult
        mock_fetch.return_value = UpdateCheckResult(
            current_version="1.4.0",
            latest_version="1.4.0",
            has_update=False,
        )
        success = await perform_update(force=False)
        assert success is True
