"""BT 只走 SOCKS5 代理：libtorrent 只有 SOCKS5 能转发 UDP（tracker、DHT）。

Seam: BTSession._proxySettings（替换全局 proxy()）
"""
from __future__ import annotations

import libtorrent as lt
import pytest

from features.bittorrent_pack import session as sessionModule
from features.bittorrent_pack.session import BTSession


@pytest.fixture()
def settingsFor(monkeypatch):
    def build(url):
        monkeypatch.setattr(sessionModule, "proxy", lambda: url)
        return BTSession()._proxySettings()
    return build


@pytest.mark.parametrize("url", [None, "http://127.0.0.1:7890", "https://127.0.0.1:7890", "socks4://127.0.0.1:1080"])
def test_non_socks5_proxy_means_direct(settingsFor, url):
    assert settingsFor(url) == {}


def test_socks5_carries_all_bt_traffic(settingsFor):
    settings = settingsFor("socks5://127.0.0.1:7890")

    assert settings["proxy_type"] == lt.proxy_type_t.socks5
    assert (settings["proxy_hostname"], settings["proxy_port"]) == ("127.0.0.1", 7890)
    assert settings["proxy_peer_connections"] and settings["proxy_tracker_connections"]


def test_socks5h_with_credentials_uses_password_auth(settingsFor):
    settings = settingsFor("socks5h://user:pass@proxy.example:1080")

    assert settings["proxy_type"] == lt.proxy_type_t.socks5_pw
    assert (settings["proxy_username"], settings["proxy_password"]) == ("user", "pass")
