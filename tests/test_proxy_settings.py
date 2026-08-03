"""BTSession._proxySettings scheme mapping tests."""
import libtorrent as lt
import pytest

from features.bittorrent_pack.session import BTSession
from app.config.cfg import cfg


@pytest.fixture
def proxy_setting():
    old = cfg.proxyServer.value
    yield
    cfg.proxyServer.value = old


def _settings(proxyUrl, proxy_setting):
    cfg.proxyServer.value = proxyUrl
    return BTSession()._proxySettings()


def test_no_proxy_when_off(proxy_setting):
    assert _settings("Off", proxy_setting) == {}


def test_socks5_mapping(proxy_setting):
    s = _settings("socks5://127.0.0.1:7897", proxy_setting)
    assert s["proxy_type"] == lt.proxy_type_t.socks5
    assert s["proxy_hostname"] == "127.0.0.1"
    assert s["proxy_port"] == 7897
    assert s["proxy_tracker_connections"] is True
    assert s["proxy_peer_connections"] is True


def test_socks5h_mapping(proxy_setting):
    s = _settings("socks5h://proxy.example.com:1080", proxy_setting)
    assert s["proxy_type"] == lt.proxy_type_t.socks5


def test_socks5_with_credentials(proxy_setting):
    s = _settings("socks5://user:pass@127.0.0.1:1080", proxy_setting)
    assert s["proxy_type"] == lt.proxy_type_t.socks5_pw
    assert s["proxy_username"] == "user"
    assert s["proxy_password"] == "pass"


def test_http_mapping(proxy_setting):
    # Windows 系统代理常为 http://127.0.0.1:7897，此前被静默丢弃
    s = _settings("http://127.0.0.1:7897", proxy_setting)
    assert s["proxy_type"] == lt.proxy_type_t.http
    assert s["proxy_hostname"] == "127.0.0.1"
    assert s["proxy_port"] == 7897


def test_http_with_credentials(proxy_setting):
    s = _settings("http://user:pass@127.0.0.1:7897", proxy_setting)
    assert s["proxy_type"] == lt.proxy_type_t.http_pw


def test_https_mapping(proxy_setting):
    # libtorrent 没有 https 代理类型，按 http（CONNECT 隧道）处理
    s = _settings("https://127.0.0.1:7897", proxy_setting)
    assert s["proxy_type"] == lt.proxy_type_t.http


def test_socks4_mapping(proxy_setting):
    # SOCKS4 协议不支持认证，带凭据也按 socks4
    s = _settings("socks4://127.0.0.1:1080", proxy_setting)
    assert s["proxy_type"] == lt.proxy_type_t.socks4
    s = _settings("socks4://user:pass@127.0.0.1:1080", proxy_setting)
    assert s["proxy_type"] == lt.proxy_type_t.socks4


def test_invalid_scheme_ignored(proxy_setting):
    assert _settings("ftp://127.0.0.1:21", proxy_setting) == {}


def test_missing_port_ignored(proxy_setting):
    assert _settings("socks5://127.0.0.1", proxy_setting) == {}
