from __future__ import annotations

import asyncio
import hashlib
import socket
from pathlib import Path

from aiohttp import web
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


def buildMultiFileTorrent(tmpPath: Path, files: dict[str, bytes]) -> tuple[bytes, dict[str, int]]:
    sourceRoot = tmpPath / "source"
    torrentDir = sourceRoot / "pack"
    torrentDir.mkdir(parents=True)
    for name, content in files.items():
        (torrentDir / name).write_bytes(content)

    fs = lt.list_files(str(torrentDir))
    ct = lt.create_torrent(fs, piece_size=16384)
    lt.set_piece_hashes(ct, str(sourceRoot))
    torrentData = lt.bencode(ct.generate())

    layout = lt.load_torrent_buffer(torrentData).ti.layout()
    indexByName = {
        Path(layout.file_path(i)).name: i
        for i in range(layout.num_files())
        if not (layout.file_flags(i) & lt.file_storage.flag_pad_file)
    }
    return torrentData, indexByName


async def startLocalSeeder(
    sourceRoot: Path, torrentData: bytes, startServer, *, uploadRateLimit: int = 0,
) -> tuple[lt.session, lt.torrent_handle, str]:
    seeder = lt.session({
        "listen_interfaces": "127.0.0.1:0",
        "enable_dht": False,
        "enable_lsd": False,
        "enable_upnp": False,
        "enable_natpmp": False,
        "upload_rate_limit": uploadRateLimit,
        "ignore_limits_on_local_network": uploadRateLimit == 0,
    })
    params = lt.load_torrent_buffer(torrentData)
    params.save_path = str(sourceRoot)
    handle = seeder.add_torrent(params)
    handle.resume()
    async with asyncio.timeout(5):
        while not handle.status().is_seeding:
            await asyncio.sleep(0.05)
    peer = socket.inet_aton("127.0.0.1") + seeder.listen_port().to_bytes(2, "big")
    body = lt.bencode({b"interval": 60, b"peers": peer})

    async def announce(_):
        return web.Response(body=body)

    trackerUrl = (await startServer(announce)).removesuffix("/file") + "/announce"
    return seeder, handle, trackerUrl


async def test_run_downloads_newly_selected_file_after_resume(config, startServer, tmp_path):
    payloads = {"a.bin": b"A" * 20000, "b.bin": b"B" * 20000, "c.bin": b"C" * 20000}
    torrentData, indexByName = buildMultiFileTorrent(tmp_path, payloads)
    seeder, seederHandle, trackerUrl = await startLocalSeeder(tmp_path / "source", torrentData, startServer)

    cfg.set(bittorrentConfig.enableDht, False)
    cfg.set(bittorrentConfig.enableLsd, False)

    saveDir = tmp_path / "downloads"
    session = BTSession()
    try:
        async with asyncio.timeout(10):
            resumeData = await session.run(
                "t1",
                TorrentParams(
                    torrentData=torrentData,
                    savePath=str(saveDir),
                    trackers=[trackerUrl],
                    selectedIndexes={indexByName["a.bin"]},
                ),
            )

        assert (saveDir / "pack" / "a.bin").read_bytes() == payloads["a.bin"]
        assert not (saveDir / "pack" / "b.bin").exists()
        assert not (saveDir / "pack" / "c.bin").exists()

        async with asyncio.timeout(10):
            await session.run(
                "t1",
                TorrentParams(
                    torrentData=torrentData,
                    savePath=str(saveDir),
                    resumeData=resumeData,
                    trackers=[trackerUrl],
                    selectedIndexes={indexByName["a.bin"], indexByName["b.bin"]},
                ),
            )

        assert (saveDir / "pack" / "a.bin").read_bytes() == payloads["a.bin"]
        assert (saveDir / "pack" / "b.bin").read_bytes() == payloads["b.bin"]
        assert not (saveDir / "pack" / "c.bin").exists()
    finally:
        await session.close()
        seeder.remove_torrent(seederHandle)


async def test_set_selection_downloads_newly_selected_file(config, startServer, tmp_path):
    payloads = {"a.bin": b"A" * 20000, "b.bin": b"B" * 20000, "c.bin": b"C" * 20000}
    torrentData, indexByName = buildMultiFileTorrent(tmp_path, payloads)
    seeder, seederHandle, trackerUrl = await startLocalSeeder(
        tmp_path / "source", torrentData, startServer, uploadRateLimit=16384,
    )

    cfg.set(bittorrentConfig.enableDht, False)
    cfg.set(bittorrentConfig.enableLsd, False)

    saveDir = tmp_path / "downloads"
    session = BTSession()
    didSelect = False

    def onProgress(_):
        nonlocal didSelect
        if not didSelect:
            didSelect = True
            session.setSelection("t1", {indexByName["a.bin"], indexByName["b.bin"]})

    try:
        async with asyncio.timeout(10):
            await session.run(
                "t1",
                TorrentParams(
                    torrentData=torrentData,
                    savePath=str(saveDir),
                    trackers=[trackerUrl],
                    selectedIndexes={indexByName["a.bin"]},
                ),
                onProgress=onProgress,
            )

        assert (saveDir / "pack" / "a.bin").read_bytes() == payloads["a.bin"]
        assert (saveDir / "pack" / "b.bin").read_bytes() == payloads["b.bin"]
        assert not (saveDir / "pack" / "c.bin").exists()
    finally:
        await session.close()
        seeder.remove_torrent(seederHandle)


async def test_close_preserves_seeding_share_ratio(config, tmp_path):
    torrentData, _ = buildMultiFileTorrent(tmp_path, {"a.bin": b"A" * 32768})
    sourceRoot = tmp_path / "source"

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        listenPort = probe.getsockname()[1]

    cfg.set(bittorrentConfig.listenPort, listenPort)
    cfg.set(bittorrentConfig.enableDht, False)
    cfg.set(bittorrentConfig.enableLsd, False)

    ready, uploaded, restored = asyncio.Event(), asyncio.Event(), asyncio.Event()
    restoredRatio = 0.0

    def onSeeding(p):
        if p.isSeeding:
            ready.set()
            if p.shareRatioPercent > 0:
                uploaded.set()

    def onRestored(p):
        nonlocal restoredRatio
        if p.isSeeding:
            restoredRatio = p.shareRatioPercent
            restored.set()

    session, restarted = BTSession(), BTSession()
    leecher = lt.session({
        "listen_interfaces": "127.0.0.1:0", "enable_dht": False, "enable_lsd": False,
        "enable_upnp": False, "enable_natpmp": False, "ignore_limits_on_local_network": True,
    })
    leecherHandle = seedingTask = restartedTask = None
    try:
        seedingTask = asyncio.create_task(session.runSeeding(
            "t1", TorrentParams(torrentData=torrentData, savePath=str(sourceRoot)),
            isManual=True, onProgress=onSeeding,
        ))
        async with asyncio.timeout(5):
            await ready.wait()

        params = lt.load_torrent_buffer(torrentData)
        params.save_path = str(tmp_path / "leecher")
        leecherHandle = leecher.add_torrent(params)
        leecherHandle.resume()
        leecherHandle.connect_peer(("127.0.0.1", listenPort))

        async with asyncio.timeout(10):
            await uploaded.wait()

        await session.close()
        assert seedingTask.done()
        resumeData = session.lastResumeData("t1")
        assert resumeData

        restartedTask = asyncio.create_task(restarted.runSeeding(
            "t1", TorrentParams(torrentData=torrentData, savePath=str(sourceRoot), resumeData=resumeData),
            isManual=True, onProgress=onRestored,
        ))
        async with asyncio.timeout(10):
            await restored.wait()
        assert restoredRatio > 0
    finally:
        for task in (restartedTask, seedingTask):
            if task is not None and not task.done():
                await cancelRun(task)
        await restarted.close()
        await session.close()
        if leecherHandle is not None:
            leecher.remove_torrent(leecherHandle)
