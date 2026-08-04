from __future__ import annotations

import asyncio
from base64 import b64decode, b64encode
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import gettempdir
from typing import TYPE_CHECKING, Callable
from urllib.parse import urlsplit

import libtorrent as lt
from loguru import logger
from PySide6.QtCore import QObject

from app.config.cfg import cfg, proxy
from app.models.task import TaskError

from .config import bittorrentConfig

if TYPE_CHECKING:
    pass

_STATE_TEXT = {
    "checking_files": "校验已有文件",
    "checking_resume_data": "检查续传状态",
    "downloading_metadata": "获取元数据",
    "downloading": "下载中",
    "finished": "下载完成",
    "seeding": "做种中",
    "allocating": "分配文件中",
    "queued_for_checking": "等待校验",
}

DHT_BOOTSTRAP_NODES = (
    "router.bittorrent.com:6881, router.utorrent.com:6881, "
    "dht.transmissionbt.com:6881, dht.libtorrent.org:25401"
)

ALERT_MASK = (
    lt.alert.category_t.error_notification
    | lt.alert.category_t.port_mapping_notification
    | lt.alert.category_t.storage_notification
    | lt.alert.category_t.status_notification
)

DHT_STATE_FILE = "bt_dht_state.dat"

_ERROR_ALERTS = (
    lt.file_error_alert,
    lt.metadata_failed_alert,
    lt.torrent_error_alert,
    lt.hash_failed_alert,
)

_RESUME_SAVE_INTERVAL = 30


@dataclass(frozen=True)
class TorrentParams:
    torrentData: bytes
    savePath: str
    resumeData: bytes = b""
    trackers: list[str] = field(default_factory=list)
    filePriorities: list[int] = field(default_factory=list)
    fileRenames: dict[int, str] = field(default_factory=dict)
    seedingTimeSeconds: int = 0


@dataclass(frozen=True)
class TorrentProgress:
    stateText: str
    peerCount: int
    seedCount: int
    isSeeding: bool
    downloadRate: int
    uploadRate: int
    shareRatioPercent: float
    seedingTimeSeconds: int
    progress: float
    receivedBytes: int
    totalWanted: int
    fileProgress: list[int]


@dataclass(eq=False)
class ActiveTorrent:
    handle: lt.torrent_handle
    done: asyncio.Future
    onProgress: Callable[[TorrentProgress], None] | None
    seedBase: int
    seedStart: int | None = None
    pollCount: int = 0
    resumeWaiter: asyncio.Future | None = None
    pendingPriorities: list[int] | None = None

    def seedingElapsed(self, isSeeding: bool, sessionSeconds: int) -> int:
        if isSeeding:
            if self.seedStart is None:
                self.seedStart = sessionSeconds
            return self.seedBase + max(0, sessionSeconds - self.seedStart)
        if self.seedStart is not None:
            self.seedBase += max(0, sessionSeconds - self.seedStart)
            self.seedStart = None
        return self.seedBase


class BTSession(QObject):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session: lt.session | None = None
        self._poller: asyncio.Task | None = None
        self._active: dict[str, ActiveTorrent] = {}
        self._metadataWaiters: dict[int, tuple[lt.torrent_handle, asyncio.Future]] = {}
        self._resumeCache: dict[str, bytes] = {}
        for item in (
            bittorrentConfig.maxUploadSpeed,
            bittorrentConfig.maxConnections,
            cfg.isSpeedLimitEnabled,
            cfg.speedLimitation,
        ):
            item.valueChanged.connect(self._onLimitChanged)
        cfg.proxyServer.valueChanged.connect(self._onProxyChanged)

    # ── public interface ──

    def open(self) -> None:
        self._ensureSession()

    async def run(self, taskId: str, params: TorrentParams,
                  onProgress: Callable[[TorrentProgress], None] | None = None) -> bytes:
        self._ensureSession()
        handle = self._addTorrent(params)

        handle.resume()
        handle.force_reannounce(0, -1, lt.reannounce_flags_t.ignore_min_interval)
        if bittorrentConfig.enableDht.value:
            handle.force_dht_announce()

        done = asyncio.get_running_loop().create_future()
        entry = ActiveTorrent(
            handle=handle, done=done, onProgress=onProgress,
            seedBase=params.seedingTimeSeconds,
        )
        self._active[taskId] = entry

        cancelled = False
        try:
            await done
        except asyncio.CancelledError:
            cancelled = True
            raise
        finally:
            if cancelled:
                self._active.pop(taskId, None)
                try:
                    if self._session is not None:
                        self._session.remove_torrent(handle)
                except Exception:
                    pass
            else:
                await self._saveResumeAndRemove(entry, taskId)
                self._active.pop(taskId, None)

        return self._resumeCache.pop(taskId, b"")

    async def fetchMetadata(self, magnetUri: str, trackers: list[str]) -> bytes:
        self._ensureSession()

        params = lt.parse_magnet_uri(magnetUri)
        params.trackers = list(dict.fromkeys(
            t for g in (params.trackers, trackers) for t in g if t
        ))
        tempDir = Path(gettempdir()) / "ghost_downloader_bt_metadata"
        tempDir.mkdir(parents=True, exist_ok=True)
        params.save_path = str(tempDir)
        params.storage_mode = lt.storage_mode_t.storage_mode_sparse
        params.flags |= lt.torrent_flags.default_dont_download | lt.torrent_flags.update_subscribe

        hashes = params.info_hashes if params.ti is None else params.ti.info_hashes()
        if hashes.has_v1() and self._session.find_torrent(hashes.v1).is_valid():
            raise TaskError("该种子已在下载中")
        if hashes.has_v2() and self._session.find_torrent(hashes.v2).is_valid():
            raise TaskError("该种子已在下载中")

        handle = self._session.add_torrent(params)
        handle.force_reannounce(0, -1, lt.reannounce_flags_t.ignore_min_interval)
        if bittorrentConfig.enableDht.value:
            handle.force_dht_announce()

        waiter: asyncio.Future[lt.torrent_info] = asyncio.get_running_loop().create_future()
        self._metadataWaiters[id(handle)] = (handle, waiter)

        try:
            ti = await asyncio.wait_for(waiter, timeout=bittorrentConfig.metadataTimeout.value)
            return lt.bencode(lt.create_torrent(ti).generate())
        except asyncio.TimeoutError:
            raise TimeoutError("等待 magnet 元数据超时")
        finally:
            self._metadataWaiters.pop(id(handle), None)
            try:
                self._session.remove_torrent(handle)
            except Exception:
                pass

    def updatePriorities(self, taskId: str, priorities: list[int]) -> None:
        entry = self._active.get(taskId)
        if entry is None:
            return
        entry.pendingPriorities = priorities

    def lastResumeData(self, taskId: str) -> bytes | None:
        return self._resumeCache.pop(taskId, None)

    async def close(self) -> None:
        self._saveDhtState()
        waiters = []
        for entry in list(self._active.values()):
            try:
                entry.handle.save_resume_data(
                    lt.save_resume_flags_t.flush_disk_cache | lt.save_resume_flags_t.save_info_dict
                )
                entry.resumeWaiter = asyncio.get_running_loop().create_future()
                waiters.append(entry.resumeWaiter)
            except Exception:
                pass

        if waiters:
            await asyncio.wait(waiters, timeout=5)

        for entry in list(self._active.values()):
            if not entry.done.done():
                entry.done.cancel()
            try:
                self._session.remove_torrent(entry.handle)
            except Exception:
                pass
        self._active.clear()

        for _key, (handle, waiter) in list(self._metadataWaiters.items()):
            if not waiter.done():
                waiter.cancel()
            try:
                self._session.remove_torrent(handle)
            except Exception:
                pass
        self._metadataWaiters.clear()

        if self._poller is not None:
            self._poller.cancel()
            try:
                await self._poller
            except asyncio.CancelledError:
                pass
            self._poller = None
        self._session = None

    # ── session lifecycle ──

    def _ensureSession(self) -> None:
        if self._session is None:
            from app.config.constants import VERSION
            params = self._loadDhtState()
            params.settings = {
                "user_agent": f"GhostDownloader/{VERSION} libtorrent/{lt.__version__}",
                "listen_interfaces": f"0.0.0.0:{bittorrentConfig.listenPort.value}",
                "connections_limit": bittorrentConfig.maxConnections.value,
                "download_rate_limit": self._downloadLimit(),
                "upload_rate_limit": int(bittorrentConfig.maxUploadSpeed.value),
                "enable_dht": bittorrentConfig.enableDht.value,
                "enable_lsd": bittorrentConfig.enableLsd.value,
                "dht_bootstrap_nodes": DHT_BOOTSTRAP_NODES,
                "announce_to_all_trackers": True,
                "announce_to_all_tiers": True,
                "enable_upnp": True,
                "enable_natpmp": True,
                "alert_mask": ALERT_MASK,
                **self._proxySettings(),
            }
            self._session = lt.session(params)
        if self._poller is None or self._poller.done():
            self._poller = asyncio.get_running_loop().create_task(self._supervise())

    def _loadDhtState(self) -> lt.session_params:
        from app.config.paths import APP_DATA_DIR
        path = Path(APP_DATA_DIR) / DHT_STATE_FILE
        if path.exists():
            try:
                return lt.read_session_params(
                    path.read_bytes(), lt.save_state_flags_t.save_dht_state
                )
            except Exception as e:
                logger.warning("加载 DHT 状态失败: {}", e)
        return lt.session_params()

    def _saveDhtState(self) -> None:
        if self._session is None:
            return
        from app.config.paths import APP_DATA_DIR
        try:
            state = self._session.save_state(
                lt.save_state_flags_t.save_dht_state
            )
            (Path(APP_DATA_DIR) / DHT_STATE_FILE).write_bytes(
                lt.bencode(state)
            )
        except Exception as e:
            logger.warning("保存 DHT 状态失败: {}", e)

    # ── torrent management ──

    def _addTorrent(self, params: TorrentParams) -> lt.torrent_handle:
        ltParams = None
        if params.resumeData:
            try:
                ltParams = lt.read_resume_data(params.resumeData)
            except Exception as e:
                logger.opt(exception=e).warning("读取 BitTorrent resume 数据失败")

        if ltParams is None:
            ltParams = lt.add_torrent_params()
            ltParams.ti = lt.torrent_info(params.torrentData)
            ltParams.flags |= lt.torrent_flags.update_subscribe

        ltParams.save_path = params.savePath
        ltParams.storage_mode = (
            lt.storage_mode_t.storage_mode_allocate
            if bittorrentConfig.storageMode.value == "allocate"
            else lt.storage_mode_t.storage_mode_sparse
        )
        ltParams.file_priorities = params.filePriorities
        if bittorrentConfig.enableSequentialDownload.value:
            ltParams.flags |= lt.torrent_flags.sequential_download
        else:
            ltParams.flags &= ~lt.torrent_flags.sequential_download
        if params.trackers:
            ltParams.trackers = list(params.trackers)

        hashes = ltParams.ti.info_hashes() if ltParams.ti is not None else ltParams.info_hashes
        stale = None
        if hashes.has_v1():
            stale = self._session.find_torrent(hashes.v1)
        if (stale is None or not stale.is_valid()) and hashes.has_v2():
            stale = self._session.find_torrent(hashes.v2)
        if stale is not None and stale.is_valid():
            for entry in self._active.values():
                if entry.handle == stale:
                    raise TaskError("该种子已在下载中")
            self._session.remove_torrent(stale)

        handle = self._session.add_torrent(ltParams)

        for index, newPath in params.fileRenames.items():
            handle.rename_file(index, newPath)

        return handle

    async def _saveResumeAndRemove(self, entry: ActiveTorrent, taskId: str) -> None:
        try:
            entry.handle.save_resume_data(
                lt.save_resume_flags_t.flush_disk_cache | lt.save_resume_flags_t.save_info_dict
            )
        except Exception:
            try:
                self._session.remove_torrent(entry.handle)
            except Exception:
                pass
            return

        entry.resumeWaiter = asyncio.get_running_loop().create_future()
        try:
            await asyncio.wait_for(entry.resumeWaiter, timeout=10)
        except asyncio.TimeoutError:
            logger.warning("等待 BitTorrent resume 数据超时")
        finally:
            entry.resumeWaiter = None
            try:
                self._session.remove_torrent(entry.handle)
            except Exception:
                pass

    # ── poll loop ──

    async def _supervise(self) -> None:
        while self._session is not None:
            try:
                for alert in self._session.pop_alerts():
                    self._routeAlert(alert)
                for entry in list(self._active.values()):
                    self._updateEntry(entry)
            except Exception as e:
                logger.opt(exception=e).error("BitTorrent poll 异常")
            await asyncio.sleep(1)

    def _routeAlert(self, alert) -> None:
        if not hasattr(alert, "handle"):
            return

        for taskId, entry in self._active.items():
            if alert.handle != entry.handle:
                continue

            if isinstance(alert, lt.save_resume_data_alert):
                self._resumeCache[taskId] = lt.write_resume_data_buf(alert.params)
                if entry.resumeWaiter is not None and not entry.resumeWaiter.done():
                    entry.resumeWaiter.set_result(True)
                return

            if isinstance(alert, lt.save_resume_data_failed_alert):
                self._resumeCache.pop(taskId, None)
                if entry.resumeWaiter is not None and not entry.resumeWaiter.done():
                    entry.resumeWaiter.set_result(False)
                return

            if isinstance(alert, lt.fastresume_rejected_alert):
                self._resumeCache.pop(taskId, None)
                return

            if isinstance(alert, _ERROR_ALERTS):
                if not entry.done.done():
                    entry.done.set_exception(
                        TaskError("BitTorrent 错误：{detail}", detail=alert.message())
                    )
                return

            return

        for key, (handle, waiter) in list(self._metadataWaiters.items()):
            if alert.handle != handle:
                continue
            if isinstance(alert, lt.metadata_received_alert):
                ti = handle.torrent_file()
                if ti is not None and ti.is_valid() and not waiter.done():
                    waiter.set_result(ti)
            elif isinstance(alert, (lt.metadata_failed_alert, lt.torrent_error_alert)):
                if not waiter.done():
                    waiter.set_exception(RuntimeError(alert.message()))
            return

    def _updateEntry(self, entry: ActiveTorrent) -> None:
        status = entry.handle.status()

        stateText = _STATE_TEXT.get(status.state.name, status.state.name)
        isSeeding = status.is_seeding
        downloadRate = status.download_rate
        uploadRate = status.upload_rate

        downloaded = status.all_time_download or status.total_wanted_done or status.total_done
        shareRatioPercent = (status.all_time_upload / downloaded * 100) if downloaded > 0 else 0.0
        seedingTimeSeconds = entry.seedingElapsed(
            isSeeding, int(status.seeding_duration.total_seconds())
        )

        receivedBytes = status.total_wanted_done
        totalWanted = status.total_wanted
        progress = (receivedBytes / totalWanted * 100) if totalWanted > 0 else 0

        if entry.onProgress is not None:
            entry.onProgress(TorrentProgress(
                stateText=stateText,
                peerCount=status.num_peers,
                seedCount=status.num_seeds,
                isSeeding=isSeeding,
                downloadRate=downloadRate,
                uploadRate=uploadRate,
                shareRatioPercent=shareRatioPercent,
                seedingTimeSeconds=seedingTimeSeconds,
                progress=progress,
                receivedBytes=receivedBytes,
                totalWanted=totalWanted,
                fileProgress=list(entry.handle.file_progress()),
            ))

        if entry.pendingPriorities is not None:
            entry.handle.prioritize_files(entry.pendingPriorities)
            entry.pendingPriorities = None

        if isSeeding and not entry.done.done():
            if self._isSeedingLimitReached(shareRatioPercent, seedingTimeSeconds):
                logger.info("自动暂停做种: 分享率 {:.2f}%, 做种时间 {}s",
                            shareRatioPercent, seedingTimeSeconds)
                entry.done.set_result(None)

        entry.pollCount += 1
        if entry.pollCount % _RESUME_SAVE_INTERVAL == 0:
            try:
                entry.handle.save_resume_data(
                    lt.save_resume_flags_t.flush_disk_cache | lt.save_resume_flags_t.save_info_dict
                )
            except Exception:
                pass

    def _isSeedingLimitReached(self, shareRatioPercent: float, seedingTimeSeconds: int) -> bool:
        ratioLimit = bittorrentConfig.seedingRatioLimit.value
        if ratioLimit > 0 and shareRatioPercent >= ratioLimit:
            return True
        timeLimitMinutes = bittorrentConfig.seedingTimeLimit.value
        if timeLimitMinutes > 0 and seedingTimeSeconds >= timeLimitMinutes * 60:
            return True
        return False

    # ── config handlers ──

    def _onLimitChanged(self, _value=None) -> None:
        if self._session is None:
            return
        self._session.apply_settings({
            "download_rate_limit": self._downloadLimit(),
            "upload_rate_limit": int(bittorrentConfig.maxUploadSpeed.value),
            "connections_limit": bittorrentConfig.maxConnections.value,
        })

    def _onProxyChanged(self, _value=None) -> None:
        if self._session is None:
            return
        settings = self._proxySettings()
        self._session.apply_settings(
            settings or {"proxy_type": lt.proxy_type_t.none}
        )

    def _downloadLimit(self) -> int:
        if not cfg.isSpeedLimitEnabled.value:
            return 0
        return int(cfg.speedLimitation.value)

    def _proxySettings(self) -> dict:
        url = proxy()
        if not url:
            return {}
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"socks5", "socks5h"} or not parsed.hostname or not parsed.port:
            return {}
        hasCredentials = bool(parsed.username or parsed.password)
        return {
            "proxy_type": lt.proxy_type_t.socks5_pw if hasCredentials else lt.proxy_type_t.socks5,
            "proxy_hostname": parsed.hostname,
            "proxy_port": parsed.port,
            "proxy_username": parsed.username or "",
            "proxy_password": parsed.password or "",
            "proxy_hostnames": True,
            "proxy_peer_connections": True,
            "proxy_tracker_connections": True,
            "force_proxy": False,
        }


btSession = BTSession()
