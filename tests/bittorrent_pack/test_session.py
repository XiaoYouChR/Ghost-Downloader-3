from __future__ import annotations

import libtorrent as lt
import pytest

from app.config.cfg import cfg
from features.bittorrent_pack.config import bittorrentConfig
from features.bittorrent_pack.session import BTSession, buildSettings


@pytest.fixture()
def settingsForProxy(monkeypatch):
    def build(url):
        monkeypatch.setattr(cfg.proxyServer, "value", url or "Off")
        assert cfg.proxyServer.value == (url or "Off")
        return buildSettings()
    return build


@pytest.mark.parametrize("url", [None, "http://127.0.0.1:7890", "https://127.0.0.1:7890", "socks4://127.0.0.1:1080"])
def test_build_direct_for_non_socks5_proxy(settingsForProxy, url):
    assert settingsForProxy(url)["proxy_type"] == lt.proxy_type_t.none


def test_build_socks5_for_all_traffic(settingsForProxy):
    settings = settingsForProxy("socks5://127.0.0.1:7890")

    assert settings["proxy_type"] == lt.proxy_type_t.socks5
    assert (settings["proxy_hostname"], settings["proxy_port"]) == ("127.0.0.1", 7890)
    assert settings["proxy_peer_connections"] and settings["proxy_tracker_connections"]


def test_build_socks5_with_password(settingsForProxy):
    settings = settingsForProxy("socks5h://user:pass@proxy.local:1080")

    assert settings["proxy_type"] == lt.proxy_type_t.socks5_pw
    assert (settings["proxy_username"], settings["proxy_password"]) == ("user", "pass")


@pytest.mark.parametrize("isEnabled", [True, False])
def test_build_utp_for_both_directions(monkeypatch, isEnabled):
    monkeypatch.setattr(bittorrentConfig.enableUtp, "value", isEnabled)

    settings = buildSettings()

    assert (settings["enable_incoming_utp"], settings["enable_outgoing_utp"]) == (isEnabled, isEnabled)


@pytest.mark.parametrize(
    ("mode", "policy", "level", "preferRc4"),
    [
        ("enabled", lt.enc_policy.pe_enabled, lt.enc_level.pe_both, True),
        ("forced", lt.enc_policy.pe_forced, lt.enc_level.pe_rc4, True),
        ("disabled", lt.enc_policy.pe_disabled, lt.enc_level.pe_both, False),
    ],
)
def test_build_encryption_mode(monkeypatch, mode, policy, level, preferRc4):
    monkeypatch.setattr(bittorrentConfig.encryptionMode, "value", mode)

    settings = buildSettings()

    assert (
        settings["in_enc_policy"],
        settings["out_enc_policy"],
        settings["allowed_enc_level"],
        settings["prefer_rc4"],
    ) == (policy, policy, level, preferRc4)


async def test_set_config_updates_open_session(config):
    session = BTSession()
    session.open()
    try:
        cfg.set(bittorrentConfig.enableUtp, False)
        cfg.set(bittorrentConfig.encryptionMode, "forced")
        cfg.set(bittorrentConfig.enableDht, False)

        assert await session.probeDhtNodes() is None
    finally:
        await session.close()
