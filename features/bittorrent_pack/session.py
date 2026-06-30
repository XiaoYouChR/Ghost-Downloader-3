from __future__ import annotations

import asyncio
from base64 import b64decode, b64encode
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from loguru import logger
from PySide6.QtCore import QObject, Signal

from app.config.cfg import cfg, proxy

from .config import bittorrentConfig

if TYPE_CHECKING:
    import libtorrent as lt
    from .task import BTTask


class BTSession(QObject):
    alertReceived = Signal(object)
    seedingUpdated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session: lt.session | None = None
        self._supervisor = None
        self._seedingTasks: dict[str, tuple[BTTask, lt.torrent_handle]] = {}
        self._resumeWaiters: dict[str, asyncio.Future] = {}
        for item in (
            bittorrentConfig.maxUploadSpeed,
            bittorrentConfig.maxConnections,
            cfg.isSpeedLimitEnabled,
            cfg.speedLimitation,
        ):
            item.valueChanged.connect(self._onLimitChanged)
        cfg.proxyServer.valueChanged.connect(self._onProxyChanged)

    def open(self):
        if self._session is not None:
            import libtorrent as lt
            settings = self._proxySettings()
            self._session.apply_settings(
                settings or {"proxy_type": lt.proxy_type_t.none}
            )
            return
        import libtorrent as lt
        from app.config.constants import VERSION
        self._session = lt.session({
            "user_agent": f"GhostDownloader/{VERSION} libtorrent/{lt.__version__}",
            "listen_interfaces": f"0.0.0.0:{bittorrentConfig.listenPort.value}",
            "connections_limit": bittorrentConfig.maxConnections.value,
            "download_rate_limit": self._downloadLimit(),
            "upload_rate_limit": int(bittorrentConfig.maxUploadSpeed.value),
            "enable_dht": bittorrentConfig.enableDht.value,
            "enable_lsd": bittorrentConfig.enableLsd.value,
            "announce_to_all_trackers": True,
            "announce_to_all_tiers": True,
            "alert_mask": lt.alert.category_t.all_categories,
            **self._proxySettings(),
        })
        self._supervisor = asyncio.get_running_loop().create_task(self._supervise())

    async def close(self):
        for taskId in list(self._seedingTasks):
            await self._removeSeedingTorrent(taskId)
        if self._supervisor is not None:
            self._supervisor.cancel()
            try:
                await self._supervisor
            except asyncio.CancelledError:
                pass
            self._supervisor = None
        self._session = None

    def session(self):
        return self._session

    # -- seeding lifecycle --

    def registerSeeding(self, task: BTTask, handle: lt.torrent_handle) -> None:
        task.shouldSeed = True
        task.isSeeding = True
        self._seedingTasks[task.taskId] = (task, handle)

    def stopSeeding(self, task: BTTask) -> None:
        if task.taskId not in self._seedingTasks:
            return
        task.shouldSeed = False
        task.isSeeding = False
        task.uploadRate = 0
        task.stateText = ""
        from app.services.coroutine_runner import coroutineRunner
        coroutineRunner.submit(self._removeSeedingTorrent(task.taskId))

    def startSeeding(self, task: BTTask) -> None:
        if task.taskId in self._seedingTasks:
            return
        if not task.resumeData or self._session is None:
            return
        import libtorrent as lt
        try:
            params = lt.read_resume_data(b64decode(task.resumeData))
            params.save_path = str(task.outputFolder)
            params.flags |= lt.torrent_flags.upload_mode
            handle = self._session.add_torrent(params)
        except Exception as e:
            logger.opt(exception=e).warning("恢复做种失败 {}", task.name)
            return
        task.shouldSeed = True
        task.isSeeding = True
        self._seedingTasks[task.taskId] = (task, handle)

    async def resumeAllSeeding(self, tasks) -> None:
        from app.models.task import TaskStatus
        from .task import BTTask
        for task in tasks:
            if isinstance(task, BTTask) and task.status == TaskStatus.COMPLETED and task.shouldSeed and task.resumeData:
                self.open()
                self.startSeeding(task)

    async def _removeSeedingTorrent(self, taskId: str) -> None:
        entry = self._seedingTasks.pop(taskId, None)
        if entry is None:
            return
        task, handle = entry
        await self._saveSeedingResume(task, handle)
        try:
            self._session.remove_torrent(handle)
        except Exception:
            pass

    async def _saveSeedingResume(self, task: BTTask, handle: lt.torrent_handle) -> None:
        import libtorrent as lt
        try:
            handle.save_resume_data(
                lt.save_resume_flags_t.flush_disk_cache | lt.save_resume_flags_t.save_info_dict
            )
        except Exception:
            return
        waiter = asyncio.get_running_loop().create_future()
        self._resumeWaiters[task.taskId] = waiter
        try:
            await asyncio.wait_for(waiter, timeout=10)
        except asyncio.TimeoutError:
            pass
        finally:
            self._resumeWaiters.pop(task.taskId, None)

    # -- config change handlers --

    def _onLimitChanged(self, _value=None):
        if self._session is None:
            return
        self._session.apply_settings({
            "download_rate_limit": self._downloadLimit(),
            "upload_rate_limit": int(bittorrentConfig.maxUploadSpeed.value),
            "connections_limit": bittorrentConfig.maxConnections.value,
        })

    def _onProxyChanged(self, _value=None):
        if self._session is None:
            return
        import libtorrent as lt
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
        import libtorrent as lt
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

    # -- supervise loop --

    async def _supervise(self):
        while self._session is not None:
            for alert in self._session.pop_alerts():
                if not self._routeSeedingAlert(alert):
                    self.alertReceived.emit(alert)
            self._refreshSeedingTasks()
            await asyncio.sleep(1)

    def _routeSeedingAlert(self, alert) -> bool:
        import libtorrent as lt
        if not hasattr(alert, "handle"):
            return False
        for taskId, (task, handle) in self._seedingTasks.items():
            if alert.handle != handle:
                continue
            if isinstance(alert, lt.save_resume_data_alert):
                task.resumeData = b64encode(lt.write_resume_data_buf(alert.params)).decode()
                waiter = self._resumeWaiters.get(taskId)
                if waiter is not None and not waiter.done():
                    waiter.set_result(True)
            elif isinstance(alert, lt.save_resume_data_failed_alert):
                task.resumeData = ""
                waiter = self._resumeWaiters.get(taskId)
                if waiter is not None and not waiter.done():
                    waiter.set_result(False)
            return True
        return False

    def _refreshSeedingTasks(self) -> None:
        if not self._seedingTasks:
            return
        for taskId in list(self._seedingTasks):
            task, handle = self._seedingTasks[taskId]
            try:
                status = handle.status()
                task.isSeeding = status.is_seeding
                task.uploadRate = status.upload_rate
                task.peerCount = status.num_peers
                task.seedCount = status.num_seeds
                task.stateText = "做种中" if status.is_seeding else ""
                downloaded = status.all_time_download or status.total_wanted_done or status.total_done
                task.shareRatioPercent = (status.all_time_upload / downloaded * 100) if downloaded > 0 else 0.0
                sessionSeconds = int(status.seeding_duration.total_seconds())
                task.seedingTimeSeconds = max(task.seedingTimeSeconds, sessionSeconds)
                if self._isSeedingLimitReached(task):
                    logger.info("{} 自动暂停做种: 分享率 {:.2f}%, 做种时间 {}s",
                                task.name, task.shareRatioPercent, task.seedingTimeSeconds)
                    self.stopSeeding(task)
            except Exception:
                pass
        self.seedingUpdated.emit()

    def _isSeedingLimitReached(self, task: BTTask) -> bool:
        if not task.isSeeding:
            return False
        ratioLimit = bittorrentConfig.seedingRatioLimit.value
        if ratioLimit > 0 and task.shareRatioPercent >= ratioLimit:
            return True
        timeLimitMinutes = bittorrentConfig.seedingTimeLimit.value
        if timeLimitMinutes > 0 and task.seedingTimeSeconds >= timeLimitMinutes * 60:
            return True
        return False


btSession = BTSession()
