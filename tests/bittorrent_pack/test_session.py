from __future__ import annotations

import libtorrent as lt
import pytest

from app.config.cfg import cfg
from features.bittorrent_pack.session import BTSession


@pytest.fixture()
def buildSettings():
    saved = cfg.proxyServer.value

    def build(url):
        cfg.proxyServer.value = url or "Off"
        assert cfg.proxyServer.value == (url or "Off")
        return BTSession().buildProxySettings()
    yield build
    cfg.proxyServer.value = saved


@pytest.mark.parametrize("url", [None, "http://127.0.0.1:7890", "https://127.0.0.1:7890", "socks4://127.0.0.1:1080"])
def test_build_direct_for_non_socks5_proxy(buildSettings, url):
    assert buildSettings(url) == {}


def test_build_socks5_for_all_traffic(buildSettings):
    settings = buildSettings("socks5://127.0.0.1:7890")

    assert settings["proxy_type"] == lt.proxy_type_t.socks5
    assert (settings["proxy_hostname"], settings["proxy_port"]) == ("127.0.0.1", 7890)
    assert settings["proxy_peer_connections"] and settings["proxy_tracker_connections"]


def test_build_socks5_with_password(buildSettings):
    settings = buildSettings("socks5h://user:pass@proxy.local:1080")

    assert settings["proxy_type"] == lt.proxy_type_t.socks5_pw
    assert (settings["proxy_username"], settings["proxy_password"]) == ("user", "pass")
