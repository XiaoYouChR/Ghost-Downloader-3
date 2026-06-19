import asyncio
from base64 import b64decode, b64encode
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import gettempdir
from urllib.parse import urlsplit

import libtorrent as lt
from loguru import logger

from app.services.core_service import coreService
from app.supports.config import VERSION, cfg
from app.supports.utils import getProxies
from .config import bittorrentConfig
from .task import BTTask
from .trackers import mergeTrackers

USER_AGENT = f"GhostDownloader/{VERSION} libtorrent/{lt.__version__}"

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

_ERROR_ALERTS = (
    lt.file_error_alert,
    lt.metadata_failed_alert,
    lt.torrent_error_alert,
    lt.hash_failed_alert,
)


@dataclass(eq=False)
class _ActiveTorrent:
    task: BTTask
    handle: lt.torrent_handle
    done: asyncio.Future
    resumeWaiter: asyncio.Future | None = None
    appliedSelectionVersion: int = -1
    _seedBase: int = field(init=False)
    _seedStart: int | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self._seedBase = self.task.seedingTimeSeconds

    def seedingElapsed(self, isSeeding: bool, sessionSeconds: int) -> int:
        if isSeeding:
            if self._seedStart is None:
                self._seedStart = sessionSeconds
            return self._seedBase + max(0, sessionSeconds - self._seedStart)
        if self._seedStart is not None:
            self._seedBase += max(0, sessionSeconds - self._seedStart)
            self._seedStart = None
        return self._seedBase


class BTSessionService:
    def __init__(self) -> None:
        self._session: lt.session | None = None
        self._poller: asyncio.Task | None = None
        self._active: dict[str, _ActiveTorrent] = {}
        self._pendingMetadata: list[tuple[lt.torrent_handle, asyncio.Future]] = []
        self._bind()

    def _bind(self) -> None:
        for item in (
            bittorrentConfig.downloadRateLimit,
            bittorrentConfig.uploadRateLimit,
            bittorrentConfig.connectionsLimit,
            cfg.enableSpeedLimitation,
            cfg.speedLimitation,
        ):
            item.valueChanged.connect(self._onLimitsChanged)

    async def lease(self, task: BTTask) -> None:
        if task.countSelected <= 0:
            raise RuntimeError("至少需要选择一个文件")

        self._prepareTarget(task)
        self._saveMagnetFile(task)
        self._open()

        handle = self._addTorrent(task)
        handle.resume()
        self._announce(handle)

        active = _ActiveTorrent(task, handle, asyncio.get_running_loop().create_future())
        self._active[task.taskId] = active
        try:
            await active.done
        finally:
            await asyncio.shield(self._removeTorrent(active))

    async def resolveMetadata(
        self, magnetUri: str, webTrackers: list[str]
    ) -> tuple[bytes, lt.torrent_info, list[str]]:
        self._open()

        params = lt.parse_magnet_uri(magnetUri)
        params.trackers = mergeTrackers(params.trackers, webTrackers)
        tempDir = Path(gettempdir()) / "ghost_downloader_bt_metadata"
        tempDir.mkdir(parents=True, exist_ok=True)
        params.save_path = str(tempDir)
        params.storage_mode = lt.storage_mode_t.storage_mode_sparse
        params.flags |= lt.torrent_flags.default_dont_download | lt.torrent_flags.update_subscribe

        handle = self._addToSession(params)
        self._announce(handle)

        waiter = asyncio.get_running_loop().create_future()
        self._pendingMetadata.append((handle, waiter))
        try:
            torrentInfo = await asyncio.wait_for(waiter, timeout=bittorrentConfig.metadataTimeout.value)
            torrentBytes = lt.bencode(lt.create_torrent(torrentInfo).generate())
        except asyncio.TimeoutError:
            raise TimeoutError("等待 magnet 元数据超时")
        finally:
            self._pendingMetadata.remove((handle, waiter))
            try:
                self._session.remove_torrent(handle)
            except Exception:
                pass

        return torrentBytes, torrentInfo, params.trackers.copy()

    def shutdown(self) -> None:
        if self._session is None:
            return
        try:
            coreService.runBlocking(self._shutdown(), timeout=15)
        except Exception as e:
            logger.opt(exception=e).warning("BitTorrent session 关闭异常")

    async def _shutdown(self) -> None:
        actives = list(self._active.values())
        if actives:
            await asyncio.gather(
                *(self._saveResume(active) for active in actives),
                return_exceptions=True,
            )

        if self._poller is not None:
            self._poller.cancel()
            try:
                await self._poller
            except asyncio.CancelledError:
                pass
            self._poller = None

        session, self._session = self._session, None
        if session is not None:
            for active in actives:
                try:
                    session.remove_torrent(active.handle)
                except Exception:
                    pass
        self._active.clear()

    def _open(self) -> None:
        if self._session is None:
            self._session = lt.session(self._sessionSettings())
        if self._poller is None or self._poller.done():
            self._poller = asyncio.get_running_loop().create_task(self._pollLoop())

    def _sessionSettings(self) -> dict:
        settings = {
            "user_agent": USER_AGENT,
            "listen_interfaces": f"0.0.0.0:{bittorrentConfig.listenPort.value}",
            "connections_limit": bittorrentConfig.connectionsLimit.value,
            "download_rate_limit": self._downloadLimit(),
            "upload_rate_limit": bittorrentConfig.uploadRateLimit.value,
            "enable_dht": bittorrentConfig.enableDHT.value,
            "enable_lsd": bittorrentConfig.enableLSD.value,
            "enable_upnp": bittorrentConfig.enableUPnP.value,
            "enable_natpmp": bittorrentConfig.enableNATPMP.value,
            "announce_to_all_trackers": True,
            "announce_to_all_tiers": True,
            "alert_mask": lt.alert.category_t.all_categories,
        }
        settings.update(self._proxySettings(getProxies()))
        return settings

    def _proxySettings(self, proxies: dict | None) -> dict:
        if not proxies:
            return {}
        proxyUrl = str(proxies.get("https") or proxies.get("http") or "").strip()
        if not proxyUrl:
            return {}
        parsed = urlsplit(proxyUrl)
        if parsed.scheme.lower() != "socks5" or not parsed.hostname or not parsed.port:
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

    def _onLimitsChanged(self, _=None) -> None:
        if self._session is None:
            return
        self._session.apply_settings({
            "download_rate_limit": self._downloadLimit(),
            "upload_rate_limit": bittorrentConfig.uploadRateLimit.value,
            "connections_limit": bittorrentConfig.connectionsLimit.value,
        })

    def _downloadLimit(self) -> int:
        btLimit = bittorrentConfig.downloadRateLimit.value
        if not cfg.enableSpeedLimitation.value:
            return btLimit
        globalLimit = cfg.speedLimitation.value
        if btLimit <= 0:
            return globalLimit
        return min(btLimit, globalLimit)

    def _addTorrent(self, task: BTTask) -> lt.torrent_handle:
        params = None
        if task.resumeData:
            try:
                params = lt.read_resume_data(b64decode(task.resumeData))
            except Exception as e:
                logger.opt(exception=e).warning("读取 BitTorrent resume 数据失败,改用种子元数据 {}", task.title)

        if params is None:
            params = lt.add_torrent_params()
            params.ti = lt.torrent_info(b64decode(task.torrentData))
            params.flags |= lt.torrent_flags.update_subscribe

        params.save_path = str(task.path)
        params.storage_mode = (
            lt.storage_mode_t.storage_mode_allocate
            if bittorrentConfig.storageMode.value == "allocate"
            else lt.storage_mode_t.storage_mode_sparse
        )
        params.file_priorities = task.priorities()
        if bittorrentConfig.sequentialDownload.value:
            params.flags |= lt.torrent_flags.sequential_download
        else:
            params.flags &= ~lt.torrent_flags.sequential_download
        if task.trackers:
            params.trackers = task.trackers.copy()

        handle = self._addToSession(params)
        for file in task.files:
            mappedPath = task.mapPath(file)
            if mappedPath != file.path:
                handle.rename_file(file.index, mappedPath)
        return handle

    def _addToSession(self, params: lt.add_torrent_params) -> lt.torrent_handle:
        infoHash = params.ti.info_hashes().v1 if params.ti is not None else params.info_hashes.v1
        if self._session.find_torrent(infoHash).is_valid():
            raise RuntimeError("该种子已在下载中")
        return self._session.add_torrent(params)

    def _announce(self, handle: lt.torrent_handle) -> None:
        handle.force_reannounce(0, -1, lt.reannounce_flags_t.ignore_min_interval)
        if bittorrentConfig.enableDHT.value:
            handle.force_dht_announce()

    def _prepareTarget(self, task: BTTask) -> None:
        target = Path(task.outputFolder)
        if target.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch() if task.isSingleFile else target.mkdir()

    def _saveMagnetFile(self, task: BTTask) -> None:
        if task.sourceType != "magnet" or not bittorrentConfig.saveMagnetTorrentFile.value:
            return
        try:
            task.magnetTorrentPath.write_bytes(b64decode(task.torrentData))
        except Exception as e:
            logger.opt(exception=e).warning("保存 magnet 种子文件失败 {}", task.title)

    async def _removeTorrent(self, active: _ActiveTorrent) -> None:
        await self._saveResume(active)
        self._active.pop(active.task.taskId, None)
        if self._session is not None:
            try:
                self._session.remove_torrent(active.handle)
            except Exception:
                pass

    async def _saveResume(self, active: _ActiveTorrent) -> None:
        if self._session is None:
            active.task.resumeData = ""
            return

        try:
            active.handle.save_resume_data(
                lt.save_resume_flags_t.flush_disk_cache | lt.save_resume_flags_t.save_info_dict
            )
        except Exception as e:
            logger.opt(exception=e).warning("保存 BitTorrent resume 数据失败 {}", active.task.title)
            active.task.resumeData = ""
            return

        active.resumeWaiter = asyncio.get_running_loop().create_future()
        try:
            await asyncio.wait_for(active.resumeWaiter, timeout=10)
        except asyncio.TimeoutError:
            logger.warning("等待 BitTorrent resume 数据超时 {}", active.task.title)
            active.task.resumeData = ""
        finally:
            active.resumeWaiter = None

    def _onResumeData(self, handle: lt.torrent_handle, resumeData: str) -> None:
        active = self._activeOf(handle)
        if active is None or active.resumeWaiter is None or active.resumeWaiter.done():
            return
        active.task.resumeData = resumeData
        active.resumeWaiter.set_result(bool(resumeData))

    async def _pollLoop(self) -> None:
        while self._session is not None:
            try:
                for alert in self._session.pop_alerts():
                    self._handleAlert(alert)
                for active in list(self._active.values()):
                    self._updateTask(active)
            except Exception as e:
                logger.opt(exception=e).error("BitTorrent 轮询循环异常")
            await asyncio.sleep(1)

    def _updateTask(self, active: _ActiveTorrent) -> None:
        task = active.task
        status = active.handle.status()
        wasSeeding = task.isSeeding

        task.stateText = _STATE_TEXT.get(status.state.name, status.state.name)
        task.peerCount = status.num_peers
        task.seedCount = status.num_seeds
        task.isSeeding = status.is_seeding
        task.downloadRate = status.download_rate
        task.uploadRate = status.upload_rate
        cfg.globalSpeed += status.download_rate
        task._updateSlot()

        downloaded = status.all_time_download or status.total_wanted_done or status.total_done
        task.shareRatioPercent = (status.all_time_upload / downloaded * 100) if downloaded > 0 else 0.0
        task.seedingTimeSeconds = active.seedingElapsed(
            task.isSeeding, int(status.seeding_duration.total_seconds())
        )

        self._updateStage(task, status)
        task.updateProgress(active.handle.file_progress())

        if active.appliedSelectionVersion != task.fileSelectionVersion:
            active.handle.prioritize_files(task.priorities())
            active.appliedSelectionVersion = task.fileSelectionVersion

        if wasSeeding != task.isSeeding:
            coreService.rebalance()

        if self._seedingLimitReached(task) and not active.done.done():
            active.done.set_result(None)

    def _updateStage(self, task: BTTask, status: lt.torrent_status) -> None:
        task.stage.speed = status.download_rate
        task.stage.receivedBytes = status.total_wanted_done
        if status.total_wanted > 0:
            task.fileSize = status.total_wanted
            task.stage.progress = status.total_wanted_done / status.total_wanted * 100
        elif task.fileSize > 0:
            task.stage.progress = task.stage.receivedBytes / task.fileSize * 100
        else:
            task.stage.progress = 0

    def _seedingLimitReached(self, task: BTTask) -> bool:
        if not task.isSeeding:
            return False

        ratioLimit = bittorrentConfig.seedRatioLimitPercent.value
        if ratioLimit > 0 and task.shareRatioPercent >= ratioLimit:
            logger.info(
                "{} 自动暂停做种: 分享率达到 {:.2f}% / {}%",
                task.title, task.shareRatioPercent, ratioLimit,
            )
            return True

        timeLimitMinutes = bittorrentConfig.seedTimeLimitMinutes.value
        if timeLimitMinutes > 0 and task.seedingTimeSeconds >= timeLimitMinutes * 60:
            logger.info(
                "{} 自动暂停做种: 做种时间达到 {} / {} 分钟",
                task.title, round(task.seedingTimeSeconds / 60), timeLimitMinutes,
            )
            return True

        return False

    def _handleAlert(self, alert: lt.alert) -> None:
        if isinstance(alert, lt.metadata_received_alert):
            self._onMetadata(alert)
            return

        if isinstance(alert, lt.save_resume_data_alert):
            self._onResumeData(alert.handle, b64encode(lt.write_resume_data_buf(alert.params)).decode())
            return

        if isinstance(alert, lt.save_resume_data_failed_alert):
            logger.warning("保存 BitTorrent resume 数据失败: {}", alert.message())
            self._onResumeData(alert.handle, "")
            return

        if isinstance(alert, lt.file_completed_alert):
            active = self._activeOf(alert.handle)
            if active is not None:
                for file in active.task.files:
                    if file.index == alert.index:
                        file.completed = True
                        file.downloadedBytes = file.size
                        break
            return

        if isinstance(alert, lt.fastresume_rejected_alert):
            active = self._activeOf(alert.handle)
            if active is not None:
                active.task.resumeData = ""
            logger.warning("BitTorrent fastresume 被拒绝: {}", alert.message())
            return

        if isinstance(alert, _ERROR_ALERTS):
            self._failTorrent(alert)

    def _onMetadata(self, alert: lt.metadata_received_alert) -> None:
        for handle, waiter in self._pendingMetadata:
            if handle == alert.handle and not waiter.done():
                torrentInfo = handle.torrent_file()
                if torrentInfo is not None and torrentInfo.is_valid():
                    waiter.set_result(torrentInfo)
                else:
                    waiter.set_exception(RuntimeError("magnet 元数据无效"))
                return

    def _failTorrent(self, alert: lt.alert) -> None:
        active = self._activeOf(alert.handle)
        if active is not None:
            if not active.done.done():
                active.done.set_exception(RuntimeError(alert.message()))
            return
        for handle, waiter in self._pendingMetadata:
            if handle == alert.handle and not waiter.done():
                waiter.set_exception(RuntimeError(alert.message()))
                return

    def _activeOf(self, handle: lt.torrent_handle) -> _ActiveTorrent | None:
        for active in self._active.values():
            if active.handle == handle:
                return active
        return None


btSessionService = BTSessionService()
