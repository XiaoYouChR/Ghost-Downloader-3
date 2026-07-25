"""BTSession 集成测试。

Seam: BTSession.run / duplicate rejection / updatePriorities / close
使用合成本地种子，不依赖网络。
"""
from __future__ import annotations

import asyncio
import os
import tempfile

import libtorrent as lt
import pytest

from features.bittorrent_pack.session import BTSession, TorrentParams, TorrentProgress
from features.bittorrent_pack.config import bittorrentConfig


@pytest.fixture
def torrent_env():
    """创建一个包含两个小文件的本地种子和对应目录。"""
    with tempfile.TemporaryDirectory() as srcDir:
        root = os.path.join(srcDir, "test_torrent")
        os.makedirs(root)
        for name, size in [("a.txt", 16384), ("b.txt", 8192)]:
            with open(os.path.join(root, name), "wb") as f:
                f.write(os.urandom(size))

        fs = lt.file_storage()
        lt.add_files(fs, root)
        ct = lt.create_torrent(fs, piece_size=16384)
        lt.set_piece_hashes(ct, srcDir)
        torrentBytes = lt.bencode(ct.generate())

        with tempfile.TemporaryDirectory() as dlDir:
            yield torrentBytes, srcDir, dlDir


@pytest.fixture
async def session():
    s = BTSession()
    yield s
    await s.close()


def _params(torrentBytes, savePath, priorities=None):
    ti = lt.torrent_info(torrentBytes)
    return TorrentParams(
        torrentData=torrentBytes,
        savePath=savePath,
        filePriorities=priorities or [4] * ti.num_files(),
    )


async def test_run_downloads_and_enters_seeding(session, torrent_env):
    torrentBytes, srcDir, _dlDir = torrent_env
    params = _params(torrentBytes, srcDir)

    progressEvents: list[TorrentProgress] = []
    task = asyncio.create_task(
        session.run("run-1", params, onProgress=progressEvents.append)
    )

    seeding = False
    for _ in range(15):
        await asyncio.sleep(1)
        if any(p.isSeeding for p in progressEvents):
            seeding = True
            break

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert seeding, "torrent should enter seeding after verifying local files"
    assert len(progressEvents) > 0


async def test_run_completes_when_seed_limit_reached(session, torrent_env):
    torrentBytes, srcDir, _dlDir = torrent_env
    params = _params(torrentBytes, srcDir)

    old = bittorrentConfig.seedingTimeLimit.value
    bittorrentConfig.seedingTimeLimit.value = 1
    try:
        resumeData = await asyncio.wait_for(
            session.run("seed-limit-1", params),
            timeout=120,
        )
    finally:
        bittorrentConfig.seedingTimeLimit.value = old

    assert isinstance(resumeData, bytes)
    assert len(resumeData) > 0


async def test_cancel_cleans_active_entry(session, torrent_env):
    torrentBytes, _srcDir, dlDir = torrent_env
    params = _params(torrentBytes, dlDir)

    task = asyncio.create_task(session.run("cancel-1", params))
    await asyncio.sleep(2)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert "cancel-1" not in session._active


async def test_duplicate_info_hash_rejected(session, torrent_env):
    torrentBytes, srcDir, _dlDir = torrent_env
    params = _params(torrentBytes, srcDir)

    task1 = asyncio.create_task(session.run("dup-1", params))
    await asyncio.sleep(1)

    with pytest.raises(Exception, match="已在下载中"):
        await session.run("dup-2", params)

    task1.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task1


async def test_update_priorities_applied(session, torrent_env):
    torrentBytes, srcDir, _dlDir = torrent_env
    params = _params(torrentBytes, srcDir)

    task = asyncio.create_task(session.run("prio-1", params))
    await asyncio.sleep(1)

    session.updatePriorities("prio-1", [4, 0])
    await asyncio.sleep(2)

    entry = session._active.get("prio-1")
    assert entry is not None
    assert entry.pendingPriorities is None

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_update_priorities_noop_when_not_active(session):
    session.updatePriorities("nonexistent", [4, 0])


async def test_close_cleans_everything(session, torrent_env):
    torrentBytes, srcDir, _dlDir = torrent_env
    params = _params(torrentBytes, srcDir)

    task = asyncio.create_task(session.run("close-1", params))
    await asyncio.sleep(1)

    await session.close()

    assert len(session._active) == 0
    assert session._session is None

    with pytest.raises(asyncio.CancelledError):
        await task
