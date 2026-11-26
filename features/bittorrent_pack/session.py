from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from tempfile import gettempdir
from urllib.parse import urlsplit

import libtorrent as lt
from loguru import logger

from app.config.cfg import cfg, proxy
from app.config.constants import VERSION
from app.config.paths import APP_DATA_DIR
from app.models.task import TaskError
from app.signal import Signal

from .config import bittorrentConfig
from .swarm import PeerInfo, SwarmInfo, TrackerInfo, toPeers, toSourceTrackers, toSwarmInfo, toTracker

DHT_BOOTSTRAP_NODES = (
    "dht.transmissionbt.com:6881, router.bt.ouinet.work:6881, dht.libtorrent.org:25401, "
    "router.bittorrent.com:6881, router.utorrent.com:6881"
)

ALERT_MASK = (
    lt.alert.category_t.error_notification
    | lt.alert.category_t.peer_notification
    | lt.alert.category_t.port_mapping_notification
    | lt.alert.category_t.storage_notification
    | lt.alert.category_t.tracker_notification
    | lt.alert.category_t.status_notification
    | lt.alert.category_t.dht_notification
    | lt.alert.category_t.performance_warning
)

DHT_STATE_FILE = "bt_dht_state.dat"

PROXY_SCHEMES = frozenset({"socks5", "socks5h"})

ERROR_ALERTS = (
    lt.file_error_alert,
    lt.torrent_error_alert,
)

RESUME_SAVE_INTERVAL = 30
IDLE_CLOSE_DELAY = 300.0


class SessionState(StrEnum):
    STOPPED = "stopped"
    IDLE = "idle"
    BUSY = "busy"

LIVE_SETTINGS = (
    bittorrentConfig.listenPort,
    bittorrentConfig.maxConnections,
    bittorrentConfig.maxUploadSpeed,
    bittorrentConfig.enableDht,
    bittorrentConfig.enableLsd,
    bittorrentConfig.enableUtp,
    bittorrentConfig.encryptionMode,
    cfg.isSpeedLimitEnabled,
    cfg.speedLimitation,
    cfg.proxyServer,
)

ENCRYPTION_MODES = {
    "enabled": (lt.enc_policy.pe_enabled, lt.enc_level.pe_both, True),
    "forced": (lt.enc_policy.pe_forced, lt.enc_level.pe_rc4, True),
    "disabled": (lt.enc_policy.pe_disabled, lt.enc_level.pe_both, False),
}


def buildProxySettings() -> dict:
    url = proxy(PROXY_SCHEMES)
    parsed = urlsplit(url) if url else None
    if not parsed or not parsed.hostname or not parsed.port:
        return {"proxy_type": lt.proxy_type_t.none}
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


def buildSettings() -> dict:
    port = bittorrentConfig.listenPort.value
    enableUtp = bittorrentConfig.enableUtp.value
    encPolicy, encLevel, preferRc4 = ENCRYPTION_MODES[bittorrentConfig.encryptionMode.value]
    return {
        "user_agent": f"GhostDownloader/{VERSION} libtorrent/{lt.__version__}",
        "listen_interfaces": f"0.0.0.0:{port},[::]:{port}",
        "connections_limit": bittorrentConfig.maxConnections.value,
        # libtorrent high_performance_seed 预设值，默认 500 会把单个 peer 限制在约 2.7 MB/s
        "max_out_request_queue": 1500,
        "download_rate_limit": int(cfg.speedLimitation.value) if cfg.isSpeedLimitEnabled.value else 0,
        "upload_rate_limit": int(bittorrentConfig.maxUploadSpeed.value),
        "enable_dht": bittorrentConfig.enableDht.value,
        "enable_lsd": bittorrentConfig.enableLsd.value,
        "enable_incoming_utp": enableUtp,
        "enable_outgoing_utp": enableUtp,
        "in_enc_policy": encPolicy,
        "out_enc_policy": encPolicy,
        "allowed_enc_level": encLevel,
        "prefer_rc4": preferRc4,
        "dht_bootstrap_nodes": DHT_BOOTSTRAP_NODES,
        "announce_to_all_trackers": True,
        "announce_to_all_tiers": True,
        "active_downloads": -1,
        "active_seeds": -1,
        "active_limit": -1,
        "active_checking": -1,
        "mixed_mode_algorithm": lt.bandwidth_mixed_algo_t.prefer_tcp,
        "enable_upnp": True,
        "enable_natpmp": True,
        "alert_mask": ALERT_MASK,
        **buildProxySettings(),
    }


def loadDhtState() -> lt.session_params:
    path = APP_DATA_DIR / DHT_STATE_FILE
    if path.exists():
        try:
            return lt.read_session_params(path.read_bytes(), lt.save_state_flags_t.save_dht_state)
        except Exception as e:
            logger.warning("加载 DHT 状态失败: {}", e)
    return lt.session_params()


def saveDhtState(session: lt.session) -> None:
    try:
        state = session.session_state(lt.save_state_flags_t.save_dht_state)
        (APP_DATA_DIR / DHT_STATE_FILE).write_bytes(
            lt.write_session_params_buf(state, lt.save_state_flags_t.save_dht_state)
        )
    except Exception as e:
        logger.warning("保存 DHT 状态失败: {}", e)


def isSeedingLimitReached(shareRatioPercent: float, seedingTimeSeconds: int) -> bool:
    ratioLimit = bittorrentConfig.seedingRatioLimit.value
    timeLimit = bittorrentConfig.seedingTimeLimit.value
    return (ratioLimit > 0 and shareRatioPercent >= ratioLimit) or (
        timeLimit > 0 and seedingTimeSeconds >= timeLimit * 60
    )


def toFilePriorities(selectedIndexes: set[int], fileCount: int) -> list[int]:
    return [4 if i in selectedIndexes else 0 for i in range(fileCount)]


@dataclass(frozen=True)
class TorrentParams:
    torrentData: bytes
    savePath: str
    resumeData: bytes = b""
    trackers: list[str] = field(default_factory=list)
    selectedIndexes: set[int] | None = None
    fileRenames: dict[int, str] = field(default_factory=dict)
    seedingTimeSeconds: int = 0


@dataclass(frozen=True)
class TorrentProgress:
    stateText: str
    peerCount: int
    totalPeerCount: int
    seedCount: int
    isSeeding: bool
    isFinished: bool
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
    isDone: Callable[[TorrentProgress], bool]
    seedBase: int
    onResumeData: Callable[[bytes], None] | None = None
    seedStart: int | None = None
    pollCount: int = 0
    resumeWaiter: asyncio.Future | None = None
    pendingSelection: set[int] | None = None

    def seedingElapsed(self, isSeeding: bool, sessionSeconds: int) -> int:
        if isSeeding:
            if self.seedStart is None:
                self.seedStart = sessionSeconds
            return self.seedBase + max(0, sessionSeconds - self.seedStart)
        if self.seedStart is not None:
            self.seedBase += max(0, sessionSeconds - self.seedStart)
            self.seedStart = None
        return self.seedBase


class BTSession:
    stateChanged = Signal()

    def __init__(self, *, idleTimeout: float = IDLE_CLOSE_DELAY):
        self._post: Callable[[Callable[[], object]], None] = lambda fn: fn()
        self._idleTimeout = idleTimeout
        self._session: lt.session | None = None
        self._poller: asyncio.Task | None = None
        self._idleTimer: asyncio.TimerHandle | None = None
        self._busyCount = 0
        self._active: dict[str, ActiveTorrent] = {}
        self._metadataWaiters: dict[int, tuple[lt.torrent_handle, asyncio.Future]] = {}
        self._resumeCache: dict[str, bytes] = {}
        self._statsWaiter: asyncio.Future | None = None

    # ── public interface ──

    @property
    def state(self) -> SessionState:
        if self._session is None:
            return SessionState.STOPPED
        return SessionState.BUSY if self._busyCount > 0 else SessionState.IDLE

    def setPost(self, post: Callable[[Callable[[], object]], None]) -> None:
        self._post = post

    async def stop(self) -> None:
        if self.state == SessionState.IDLE:
            await self.close()

    async def run(self, taskId: str, params: TorrentParams,
                  onProgress: Callable[[TorrentProgress], None] | None = None) -> bytes:
        return await self._run(taskId, params, onProgress, isDone=lambda p: p.isFinished)

    async def runSeeding(self, taskId: str, params: TorrentParams, isManual: bool,
                         onProgress: Callable[[TorrentProgress], None] | None = None,
                         onResumeData: Callable[[bytes], None] | None = None) -> bytes:
        def isDone(p: TorrentProgress) -> bool:
            return not isManual and p.isSeeding and isSeedingLimitReached(
                p.shareRatioPercent, p.seedingTimeSeconds)
        return await self._run(taskId, params, onProgress, isDone, onResumeData)

    async def _run(self, taskId: str, params: TorrentParams,
                   onProgress: Callable[[TorrentProgress], None] | None,
                   isDone: Callable[[TorrentProgress], bool],
                   onResumeData: Callable[[bytes], None] | None = None) -> bytes:
        with self._hold():
            handle = self._addTorrent(params)
            handle.resume()
            handle.force_reannounce(0, -1, lt.reannounce_flags_t.ignore_min_interval)
            if bittorrentConfig.enableDht.value:
                handle.force_dht_announce()

            done = asyncio.get_running_loop().create_future()
            entry = ActiveTorrent(
                handle=handle, done=done, onProgress=onProgress, isDone=isDone,
                seedBase=params.seedingTimeSeconds, onResumeData=onResumeData,
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
                    if self._session is not None:
                        with suppress(Exception):
                            self._session.remove_torrent(handle)
                else:
                    await self._saveResumeAndRemove(entry)
                    self._active.pop(taskId, None)

        return self._resumeCache.pop(taskId, b"")

    async def fetchMetadata(self, magnetUri: str, trackers: list[str]) -> bytes:
        params = lt.parse_magnet_uri(magnetUri)
        magnetTrackers = list(params.trackers)
        params.trackers = list(dict.fromkeys(
            t for g in (magnetTrackers, trackers) for t in g if t
        ))
        tempDir = Path(gettempdir()) / "ghost_downloader_bt_metadata"
        tempDir.mkdir(parents=True, exist_ok=True)
        params.save_path = str(tempDir)
        params.storage_mode = lt.storage_mode_t.storage_mode_sparse
        params.flags |= lt.torrent_flags.default_dont_download

        with self._hold():
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
                torrent = lt.add_torrent_params()
                torrent.ti = ti
                torrent.trackers = magnetTrackers
                return lt.bencode(lt.write_torrent_file(torrent, lt.write_flags.allow_missing_piece_layer))
            except asyncio.TimeoutError:
                raise TimeoutError("等待 magnet 元数据超时")
            finally:
                self._metadataWaiters.pop(id(handle), None)
                if self._session is not None:
                    with suppress(Exception):
                        self._session.remove_torrent(handle)

    async def probeDhtNodes(self) -> int | None:
        if self._session is None or not self._session.is_dht_running():
            return None
        if self._statsWaiter is None or self._statsWaiter.done():
            self._statsWaiter = asyncio.get_running_loop().create_future()
            self._session.post_session_stats()
        try:
            return await asyncio.wait_for(asyncio.shield(self._statsWaiter), timeout=5)
        except TimeoutError:
            return None

    def setSelection(self, taskId: str, selectedIndexes: set[int]) -> None:
        entry = self._active.get(taskId)
        if entry is not None:
            entry.pendingSelection = selectedIndexes

    def lastResumeData(self, taskId: str) -> bytes | None:
        return self._resumeCache.pop(taskId, None)

    @property
    def hasActiveTorrents(self) -> bool:
        return bool(self._active)

    def swarmInfo(self, taskId: str) -> SwarmInfo | None:
        entry = self._active.get(taskId)
        return toSwarmInfo(entry.handle.status()) if entry else None

    def peers(self, taskId: str) -> tuple[PeerInfo, ...]:
        entry = self._active.get(taskId)
        return toPeers(entry.handle.get_peer_info()) if entry else ()

    def trackers(self, taskId: str) -> tuple[TrackerInfo, ...]:
        entry = self._active.get(taskId)
        if entry is None:
            return ()
        info = entry.handle.torrent_file()
        sourceTrackers = toSourceTrackers(
            entry.handle.get_peer_info(), bittorrentConfig.enableDht.value, bittorrentConfig.enableLsd.value,
            bool(info and info.priv()))
        return (*sourceTrackers, *(toTracker(raw) for raw in entry.handle.trackers()))

    async def close(self) -> None:
        if self._session is None:
            return
        for item in LIVE_SETTINGS:
            item.valueChanged.disconnect(self._onSettingsChanged)
        saveDhtState(self._session)
        waiters = []
        for entry in list(self._active.values()):
            with suppress(Exception):
                entry.handle.save_resume_data(
                    lt.save_resume_flags_t.flush_disk_cache | lt.save_resume_flags_t.save_info_dict
                )
                entry.resumeWaiter = asyncio.get_running_loop().create_future()
                waiters.append(entry.resumeWaiter)

        if waiters:
            await asyncio.wait(waiters, timeout=5)

        for entry in list(self._active.values()):
            if not entry.done.done():
                entry.done.cancel()
            with suppress(Exception):
                self._session.remove_torrent(entry.handle)
        self._active.clear()

        for _key, (handle, waiter) in list(self._metadataWaiters.items()):
            if not waiter.done():
                waiter.cancel()
            with suppress(Exception):
                self._session.remove_torrent(handle)
        self._metadataWaiters.clear()

        self._cancelIdleTimer()
        self._session = None
        if self._statsWaiter is not None and not self._statsWaiter.done():
            self._statsWaiter.set_result(None)
        self._statsWaiter = None
        poller, self._poller = self._poller, None
        self._post(self.stateChanged.emit)
        if poller is not None:
            poller.cancel()
            with suppress(asyncio.CancelledError):
                await poller

    # ── lifecycle ──

    @contextmanager
    def _hold(self) -> Iterator[None]:
        if self._session is None:
            params = loadDhtState()
            params.settings = buildSettings()
            self._session = lt.session(params)
            self._poller = asyncio.get_running_loop().create_task(self._supervise())
            for item in LIVE_SETTINGS:
                item.valueChanged.connect(self._onSettingsChanged)
        self._busyCount += 1
        if self._busyCount == 1:
            self._cancelIdleTimer()
            self._post(self.stateChanged.emit)
        try:
            yield
        finally:
            self._busyCount -= 1
            if self._busyCount == 0 and self._session is not None:
                self._startIdleTimer()
                self._post(self.stateChanged.emit)

    def _startIdleTimer(self) -> None:
        self._cancelIdleTimer()
        self._idleTimer = asyncio.get_running_loop().call_later(
            self._idleTimeout, lambda: asyncio.ensure_future(self.stop()),
        )

    def _cancelIdleTimer(self) -> None:
        if self._idleTimer is not None:
            self._idleTimer.cancel()
            self._idleTimer = None

    # ── torrent management ──

    def _addTorrent(self, params: TorrentParams) -> lt.torrent_handle:
        ltParams = None
        if params.resumeData:
            try:
                ltParams = lt.read_resume_data(params.resumeData)
            except Exception as e:
                logger.opt(exception=e).warning("读取 BitTorrent resume 数据失败")

        torrentParams = lt.load_torrent_buffer(params.torrentData)
        if ltParams is None:
            ltParams = torrentParams
        elif ltParams.ti is None:
            ltParams.ti = torrentParams.ti

        ltParams.save_path = params.savePath
        ltParams.storage_mode = (
            lt.storage_mode_t.storage_mode_allocate
            if bittorrentConfig.storageMode.value == "allocate"
            else lt.storage_mode_t.storage_mode_sparse
        )
        if params.selectedIndexes is not None:
            # resumeData 携带旧的 piece_priorities，不清空会覆盖新的 file_priorities
            ltParams.piece_priorities = []
            ltParams.file_priorities = toFilePriorities(params.selectedIndexes, ltParams.ti.num_files())
        ltParams.renamed_files = params.fileRenames
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

        return self._session.add_torrent(ltParams)

    async def _saveResumeAndRemove(self, entry: ActiveTorrent) -> None:
        try:
            entry.handle.save_resume_data(
                lt.save_resume_flags_t.flush_disk_cache | lt.save_resume_flags_t.save_info_dict
            )
        except Exception:
            if self._session is not None:
                with suppress(Exception):
                    self._session.remove_torrent(entry.handle)
            return

        entry.resumeWaiter = asyncio.get_running_loop().create_future()
        try:
            await asyncio.wait_for(entry.resumeWaiter, timeout=10)
        except asyncio.TimeoutError:
            logger.warning("等待 BitTorrent resume 数据超时")
        finally:
            entry.resumeWaiter = None
            if self._session is not None:
                with suppress(Exception):
                    self._session.remove_torrent(entry.handle)

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
        if isinstance(alert, lt.session_stats_alert):
            if self._statsWaiter is not None and not self._statsWaiter.done():
                self._statsWaiter.set_result(alert.values["dht.dht_nodes"])
            return

        if isinstance(alert, lt.performance_alert):
            logger.warning("BitTorrent 性能警告: {}", alert.message())
            return

        if not hasattr(alert, "handle"):
            return

        for taskId, entry in self._active.items():
            if alert.handle != entry.handle:
                continue

            if isinstance(alert, lt.save_resume_data_alert):
                resumeData = lt.write_resume_data_buf(alert.params)
                self._resumeCache[taskId] = resumeData
                if entry.onResumeData is not None:
                    # The shutdown path flushes task records after the session closes.
                    entry.onResumeData(resumeData)
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

            if isinstance(alert, lt.hash_failed_alert):
                logger.debug("BitTorrent 分片校验失败，将重新下载: {}", alert.message())
                return

            if isinstance(alert, ERROR_ALERTS):
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
        if entry.pendingSelection is not None:
            fileCount = entry.handle.torrent_file().num_files()
            entry.handle.prioritize_files(toFilePriorities(entry.pendingSelection, fileCount))
            entry.pendingSelection = None
            return

        status = entry.handle.status()

        isSeeding = status.is_seeding
        downloaded = status.all_time_download or status.total_wanted_done or status.total_done
        shareRatioPercent = (status.all_time_upload / downloaded * 100) if downloaded > 0 else 0.0
        seedingTimeSeconds = entry.seedingElapsed(
            isSeeding, int(status.seeding_duration.total_seconds())
        )

        receivedBytes = status.total_wanted_done
        totalWanted = status.total_wanted
        progress = (receivedBytes / totalWanted * 100) if totalWanted > 0 else 0

        torrentProgress = TorrentProgress(
            stateText=status.state.name,
            peerCount=status.num_peers,
            totalPeerCount=max(status.num_peers, status.list_peers),
            seedCount=status.num_seeds,
            isSeeding=isSeeding,
            isFinished=status.is_finished,
            downloadRate=status.download_rate,
            uploadRate=status.upload_rate,
            shareRatioPercent=shareRatioPercent,
            seedingTimeSeconds=seedingTimeSeconds,
            progress=progress,
            receivedBytes=receivedBytes,
            totalWanted=totalWanted,
            fileProgress=list(entry.handle.file_progress()),
        )
        if entry.onProgress is not None:
            entry.onProgress(torrentProgress)

        if not entry.done.done() and entry.isDone(torrentProgress):
            entry.done.set_result(None)

        entry.pollCount += 1
        if entry.pollCount % RESUME_SAVE_INTERVAL == 0:
            with suppress(Exception):
                entry.handle.save_resume_data(
                    lt.save_resume_flags_t.flush_disk_cache | lt.save_resume_flags_t.save_info_dict
                )

    # ── config handlers ──

    def _onSettingsChanged(self, *_) -> None:
        if self._session is not None:
            self._session.apply_settings(buildSettings())


btSession = BTSession()
