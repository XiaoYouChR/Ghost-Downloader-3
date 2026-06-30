from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import gettempdir

import libtorrent as lt

from .config import bittorrentConfig


async def fetchTorrentBytes(magnetUri: str, webTrackers: list[str]) -> bytes:
    from .session import btSession
    btSession.open()
    session = btSession.session()

    params = lt.parse_magnet_uri(magnetUri)
    params.trackers = list(dict.fromkeys(t for g in (params.trackers, webTrackers) for t in g if t))
    tempDir = Path(gettempdir()) / "ghost_downloader_bt_metadata"
    tempDir.mkdir(parents=True, exist_ok=True)
    params.save_path = str(tempDir)
    params.storage_mode = lt.storage_mode_t.storage_mode_sparse
    params.flags |= lt.torrent_flags.default_dont_download | lt.torrent_flags.update_subscribe

    infoHash = params.info_hashes.v1 if params.ti is None else params.ti.info_hashes().v1
    if session.find_torrent(infoHash).is_valid():
        raise RuntimeError("该种子已在下载中")
    handle = session.add_torrent(params)

    handle.force_reannounce(0, -1, lt.reannounce_flags_t.ignore_min_interval)
    if bittorrentConfig.enableDht.value:
        handle.force_dht_announce()

    waiter: asyncio.Future[lt.torrent_info] = asyncio.get_running_loop().create_future()

    def onAlert(alert):
        if not hasattr(alert, "handle") or alert.handle != handle:
            return
        if isinstance(alert, lt.metadata_received_alert):
            ti = handle.torrent_file()
            if ti is not None and ti.is_valid() and not waiter.done():
                waiter.set_result(ti)
        elif isinstance(alert, (lt.metadata_failed_alert, lt.torrent_error_alert)):
            if not waiter.done():
                waiter.set_exception(RuntimeError(alert.message()))

    btSession.alertReceived.connect(onAlert)
    try:
        torrentInfo = await asyncio.wait_for(waiter, timeout=bittorrentConfig.metadataTimeout.value)
        return lt.bencode(lt.create_torrent(torrentInfo).generate())
    except asyncio.TimeoutError:
        raise TimeoutError("等待 magnet 元数据超时")
    finally:
        btSession.alertReceived.disconnect(onAlert)
        try:
            session.remove_torrent(handle)
        except Exception:
            pass
