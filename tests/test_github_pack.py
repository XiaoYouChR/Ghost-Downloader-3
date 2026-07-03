"""Tests for features.github_pack.config — pure logic, no Qt/network."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from features.github_pack.config import (
    GITHUB_PROXY_SITES,
    PROBE_TARGET,
    PROBE_UNAVAILABLE,
    PROBE_TIMEOUT,
    toProxySite,
    GitHubProxySiteValidator,
)


# -- toProxySite --

def test_toProxySite_strips_and_adds_scheme():
    assert toProxySite("  example.com  ") == "https://example.com"

def test_toProxySite_preserves_existing_scheme():
    assert toProxySite("http://example.com") == "http://example.com"

def test_toProxySite_strips_trailing_slash():
    assert toProxySite("https://example.com/") == "https://example.com"

def test_toProxySite_empty_and_none():
    assert toProxySite("") == ""
    assert toProxySite(None) == ""


# -- GitHubProxySiteValidator --

def test_validator_accepts_valid_sites():
    v = GitHubProxySiteValidator()
    assert v.validate("https://example.com") is True
    assert v.validate("http://proxy.local") is True
    assert v.validate("example.com") is True

def test_validator_rejects_invalid_sites():
    v = GitHubProxySiteValidator()
    assert v.validate("") is False
    assert v.validate("ftp://example.com") is False
    assert v.validate("https://example.com?foo=bar") is False
    assert v.validate("https://example.com#anchor") is False

def test_validator_correct_returns_normalized_or_empty():
    v = GitHubProxySiteValidator()
    assert v.correct("  example.com/  ") == "https://example.com"
    assert v.correct("") == ""


# -- Constants --

def test_proxy_sites_updated():
    assert "https://gh-proxy.com" in GITHUB_PROXY_SITES
    assert "https://gh-proxy.org" in GITHUB_PROXY_SITES
    assert "https://gh.ddlc.top" in GITHUB_PROXY_SITES
    assert "https://ghfast.top" in GITHUB_PROXY_SITES
    assert "ghproxy.vip" not in str(GITHUB_PROXY_SITES)
    assert "gh.llkk.cc" not in str(GITHUB_PROXY_SITES)
    assert "ghproxy.homeboyc.cn" not in str(GITHUB_PROXY_SITES)

def test_probe_target_is_release_url():
    assert "releases/download" in PROBE_TARGET

def test_probe_sentinel_values():
    assert PROBE_UNAVAILABLE != PROBE_TIMEOUT
    assert PROBE_UNAVAILABLE < 0
    assert PROBE_TIMEOUT < 0


# -- probeProxyLatencies --

def test_probe_returns_latency_on_success():
    from features.github_pack.config import probeProxyLatencies

    mock_response = MagicMock()
    mock_response.status.as_int.return_value = 200

    mock_client = MagicMock()
    mock_client.head = AsyncMock(return_value=mock_response)
    mock_client.close = MagicMock()

    with patch("features.github_pack.config.buildClient", return_value=mock_client), \
         patch("features.github_pack.config.githubConfig") as mock_cfg:
        mock_cfg.customSite.value = ""
        result = asyncio.run(probeProxyLatencies())

    for site in GITHUB_PROXY_SITES:
        assert site in result
        assert result[site] >= 0

def test_probe_returns_unavailable_on_http_error():
    from features.github_pack.config import probeProxyLatencies

    mock_response = MagicMock()
    mock_response.status.as_int.return_value = 403

    mock_client = MagicMock()
    mock_client.head = AsyncMock(return_value=mock_response)
    mock_client.close = MagicMock()

    with patch("features.github_pack.config.buildClient", return_value=mock_client), \
         patch("features.github_pack.config.githubConfig") as mock_cfg:
        mock_cfg.customSite.value = ""
        result = asyncio.run(probeProxyLatencies())

    for site in GITHUB_PROXY_SITES:
        assert result[site] == PROBE_UNAVAILABLE

def test_probe_returns_timeout_on_timeout():
    from features.github_pack.config import probeProxyLatencies

    mock_client = MagicMock()
    mock_client.head = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_client.close = MagicMock()

    with patch("features.github_pack.config.buildClient", return_value=mock_client), \
         patch("features.github_pack.config.githubConfig") as mock_cfg:
        mock_cfg.customSite.value = ""
        result = asyncio.run(probeProxyLatencies())

    for site in GITHUB_PROXY_SITES:
        assert result[site] == PROBE_TIMEOUT

def test_probe_returns_timeout_on_connection_error():
    from features.github_pack.config import probeProxyLatencies

    mock_client = MagicMock()
    mock_client.head = AsyncMock(side_effect=ConnectionError("refused"))
    mock_client.close = MagicMock()

    with patch("features.github_pack.config.buildClient", return_value=mock_client), \
         patch("features.github_pack.config.githubConfig") as mock_cfg:
        mock_cfg.customSite.value = ""
        result = asyncio.run(probeProxyLatencies())

    for site in GITHUB_PROXY_SITES:
        assert result[site] == PROBE_TIMEOUT

def test_probe_includes_custom_site():
    from features.github_pack.config import probeProxyLatencies

    mock_response = MagicMock()
    mock_response.status.as_int.return_value = 200

    mock_client = MagicMock()
    mock_client.head = AsyncMock(return_value=mock_response)
    mock_client.close = MagicMock()

    with patch("features.github_pack.config.buildClient", return_value=mock_client), \
         patch("features.github_pack.config.githubConfig") as mock_cfg:
        mock_cfg.customSite.value = "https://my-custom-proxy.com"
        result = asyncio.run(probeProxyLatencies())

    assert "https://my-custom-proxy.com" in result
    assert result["https://my-custom-proxy.com"] >= 0


if __name__ == "__main__":
    test_toProxySite_strips_and_adds_scheme()
    test_toProxySite_preserves_existing_scheme()
    test_toProxySite_strips_trailing_slash()
    test_toProxySite_empty_and_none()
    test_validator_accepts_valid_sites()
    test_validator_rejects_invalid_sites()
    test_validator_correct_returns_normalized_or_empty()
    test_proxy_sites_updated()
    test_probe_target_is_release_url()
    test_probe_sentinel_values()
    test_probe_returns_latency_on_success()
    test_probe_returns_unavailable_on_http_error()
    test_probe_returns_timeout_on_timeout()
    test_probe_returns_timeout_on_connection_error()
    test_probe_includes_custom_site()
    print("\nAll GitHub pack tests passed.")
