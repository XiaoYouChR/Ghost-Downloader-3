from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import libtorrent as lt
import pytest

from app.config.cfg import cfg
from features.bittorrent_pack.config import bittorrentConfig
from features.bittorrent_pack.session import BTSession, SessionState, TorrentParams, buildSettings


def buildParams(tmpPath: Path) -> TorrentParams:
    payload = b"hello world"
    torrentData = lt.bencode({
        b"info": {
            b"name": b"sample.bin",
            b"length": len(payload),
            b"piece length": 16384,
            b"pieces": hashlib.sha1(payload).digest(),
        },
    })
    return TorrentParams(torrentData=torrentData, savePath=str(tmpPath))


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


async def startRun(session: BTSession, taskId: str, params: TorrentParams) -> asyncio.Task:
    task = asyncio.create_task(session.run(taskId, params))
    await asyncio.sleep(0)
    return task


async def cancelRun(task: asyncio.Task) -> None:
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_set_config_updates_open_session(config, tmp_path):
    session = BTSession()
    running = await startRun(session, "t1", buildParams(tmp_path))
    try:
        cfg.set(bittorrentConfig.enableUtp, False)
        cfg.set(bittorrentConfig.encryptionMode, "forced")
        cfg.set(bittorrentConfig.enableDht, False)

        assert await session.probeDhtNodes() is None
    finally:
        await cancelRun(running)
        await session.close()


async def test_stop_closes_idle_session_only(config, tmp_path):
    states: list[SessionState] = []
    session = BTSession()
    session.setPost(lambda fn: fn())
    assert session.state == SessionState.STOPPED
    session.stateChanged.connect(lambda: states.append(session.state))

    running = await startRun(session, "t1", buildParams(tmp_path))
    try:
        await session.stop()
        assert session.state == SessionState.BUSY
        assert not running.done()

        await cancelRun(running)
        assert session.state == SessionState.IDLE

        await session.stop()
        assert session.state == SessionState.STOPPED
        assert states == [SessionState.BUSY, SessionState.IDLE, SessionState.STOPPED]
    finally:
        await session.close()


async def test_cancel_run_closes_session_after_idle(config, tmp_path):
    stopped = asyncio.Event()
    session = BTSession(idleTimeout=0.05)
    session.stateChanged.connect(lambda: session.state == SessionState.STOPPED and stopped.set())
    params = buildParams(tmp_path)

    try:
        await cancelRun(await startRun(session, "t1", params))
        assert session.state == SessionState.IDLE

        second = await startRun(session, "t2", params)
        await asyncio.sleep(0.08)
        assert session.state == SessionState.BUSY
        assert not stopped.is_set()

        await cancelRun(second)
        async with asyncio.timeout(1):
            await stopped.wait()
        assert session.state == SessionState.STOPPED
    finally:
        await session.close()
