from __future__ import annotations

import asyncio
from base64 import b64decode, b64encode
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import libtorrent as lt
from loguru import logger
from PySide6.QtCore import QObject, Signal

from app.config.cfg import cfg, proxy
from app.models.task import TaskError, TaskStatus

from .config import bittorrentConfig

if TYPE_CHECKING:
    from .task import BTTask, BTTaskStep

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

_RESUME_SAVE_INTERVAL = 30


@dataclass(eq=False)
class ActiveTorrent:
    task: BTTask
    step: BTTaskStep
    handle: lt.torrent_handle
    done: asyncio.Future
    seedBase: int
    seedStart: int | None = None
    appliedSelectionVersion: int = -1
    pollCount: int = 0
    resumeWaiter: asyncio.Future | None = None

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
    alertReceived = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session: lt.session | None = None
        self._poller: asyncio.Task | None = None
        self._active: dict[str, ActiveTorrent] = {}
        self._reportSpeed = None
        for item in (
            bittorrentConfig.maxUploadSpeed,
            bittorrentConfig.maxConnections,
            cfg.isSpeedLimitEnabled,
            cfg.speedLimitation,
        ):
            item.valueChanged.connect(self._onLimitChanged)
        cfg.proxyServer.valueChanged.connect(self._onProxyChanged)

    # ── public interface ──

    def setReportSpeed(self, reportSpeed):
        self._reportSpeed = reportSpeed

    async def run(self, task: BTTask, step: BTTaskStep) -> None:
        self.open()
        handle = self._addTorrent(task)

        handle.resume()
        handle.force_reannounce(0, -1, lt.reannounce_flags_t.ignore_min_interval)
        if bittorrentConfig.enableDht.value:
            handle.force_dht_announce()

        done = asyncio.get_running_loop().create_future()
        entry = ActiveTorrent(
            task=task, step=step, handle=handle,
            done=done, seedBase=task.seedingTimeSeconds,
        )
        self._active[task.taskId] = entry

        cancelled = False
        try:
            await done
        except asyncio.CancelledError:
            cancelled = True
            task.stateText = "已暂停做种" if task.isSeeding else "已暂停下载"
            task.isSeeding = False
            raise
        finally:
            if cancelled:
                self._active.pop(task.taskId, None)
                try:
                    self._session.remove_torrent(handle)
                except Exception:
                    pass
            else:
                await self._saveResumeAndRemove(entry)
                self._active.pop(task.taskId, None)

    def stop(self, taskId: str) -> None:
        entry = self._active.get(taskId)
        if entry is None or entry.done.done():
            return
        entry.task.shouldSeed = False
        entry.task.isSeeding = False
        entry.task.stateText = "已停止做种"
        entry.done.set_result(None)

    def session(self) -> lt.session | None:
        return self._session

    async def close(self) -> None:
        for entry in list(self._active.values()):
            if not entry.done.done():
                entry.done.cancel()
            try:
                self._session.remove_torrent(entry.handle)
            except Exception:
                pass
        self._active.clear()

        if self._poller is not None:
            self._poller.cancel()
            try:
                await self._poller
            except asyncio.CancelledError:
                pass
            self._poller = None
        self._session = None

    # ── session lifecycle ──

    def open(self) -> None:
        if self._session is None:
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
        if self._poller is None or self._poller.done():
            self._poller = asyncio.get_running_loop().create_task(self._supervise())

    # ── torrent management ──

    def _addTorrent(self, task: BTTask) -> lt.torrent_handle:
        params = None
        if task.resumeData:
            try:
                params = lt.read_resume_data(b64decode(task.resumeData))
            except Exception as e:
                logger.opt(exception=e).warning("读取 BitTorrent resume 数据失败 {}", task.name)

        if params is None:
            params = lt.add_torrent_params()
            params.ti = lt.torrent_info(b64decode(task.torrentData))
            params.flags |= lt.torrent_flags.update_subscribe

        params.save_path = str(task.outputFolder)
        params.storage_mode = (
            lt.storage_mode_t.storage_mode_allocate
            if bittorrentConfig.storageMode.value == "allocate"
            else lt.storage_mode_t.storage_mode_sparse
        )
        params.file_priorities = task.priorities()
        if bittorrentConfig.enableSequentialDownload.value:
            params.flags |= lt.torrent_flags.sequential_download
        else:
            params.flags &= ~lt.torrent_flags.sequential_download
        if task.trackers:
            params.trackers = task.trackers.copy()

        hashes = params.ti.info_hashes() if params.ti is not None else params.info_hashes
        stale = None
        if hashes.has_v1():
            stale = self._session.find_torrent(hashes.v1)
        if (stale is None or not stale.is_valid()) and hashes.has_v2():
            stale = self._session.find_torrent(hashes.v2)
        if stale is not None and stale.is_valid():
            self._session.remove_torrent(stale)

        handle = self._session.add_torrent(params)

        for f in task.files:
            mapped = task.toRelativePath(f)
            if mapped != f.relativePath:
                handle.rename_file(f.index, mapped)

        return handle

    async def _saveResumeAndRemove(self, entry: ActiveTorrent) -> None:
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
            logger.warning("等待 BitTorrent resume 数据超时 {}", entry.task.name)
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
                    self._updateTorrent(entry)
            except Exception as e:
                logger.opt(exception=e).error("BitTorrent poll 异常")
            await asyncio.sleep(1)

    def _routeAlert(self, alert) -> None:
        if not hasattr(alert, "handle"):
            self.alertReceived.emit(alert)
            return

        for entry in self._active.values():
            if alert.handle != entry.handle:
                continue

            if isinstance(alert, lt.save_resume_data_alert):
                entry.task.resumeData = b64encode(lt.write_resume_data_buf(alert.params)).decode()
                if entry.resumeWaiter is not None and not entry.resumeWaiter.done():
                    entry.resumeWaiter.set_result(True)
                return

            if isinstance(alert, lt.save_resume_data_failed_alert):
                entry.task.resumeData = ""
                if entry.resumeWaiter is not None and not entry.resumeWaiter.done():
                    entry.resumeWaiter.set_result(False)
                return

            if isinstance(alert, lt.file_completed_alert):
                for f in entry.task.files:
                    if f.index == alert.index:
                        f.completed = True
                        f.downloadedBytes = f.size
                        break
                return

            if isinstance(alert, lt.fastresume_rejected_alert):
                entry.task.resumeData = ""
                return

            if isinstance(alert, _ERROR_ALERTS):
                if not entry.done.done():
                    entry.done.set_exception(
                        TaskError("BitTorrent 错误：{detail}", detail=alert.message())
                    )
                return

            return

        self.alertReceived.emit(alert)

    def _updateTorrent(self, entry: ActiveTorrent) -> None:
        task = entry.task
        step = entry.step
        status = entry.handle.status()

        task.stateText = _STATE_TEXT.get(status.state.name, status.state.name)
        task.peerCount = status.num_peers
        task.seedCount = status.num_seeds
        task.isSeeding = status.is_seeding
        task.downloadRate = status.download_rate
        task.uploadRate = status.upload_rate
        if self._reportSpeed is not None:
            self._reportSpeed(status.download_rate)

        downloaded = status.all_time_download or status.total_wanted_done or status.total_done
        task.shareRatioPercent = (status.all_time_upload / downloaded * 100) if downloaded > 0 else 0.0
        task.seedingTimeSeconds = entry.seedingElapsed(
            status.is_seeding, int(status.seeding_duration.total_seconds())
        )

        step.speed = status.download_rate
        step.receivedBytes = status.total_wanted_done
        if status.total_wanted > 0:
            task.fileSize = status.total_wanted
            step.progress = status.total_wanted_done / status.total_wanted * 100
        elif task.fileSize > 0:
            step.progress = step.receivedBytes / task.fileSize * 100
        else:
            step.progress = 0

        fileBytes = entry.handle.file_progress()
        for f in task.files:
            if not f.selected:
                f.downloadedBytes = 0
                f.completed = False
                continue
            dl = fileBytes[f.index] if f.index < len(fileBytes) else 0
            f.downloadedBytes = dl
            f.completed = f.size > 0 and dl >= f.size

        if entry.appliedSelectionVersion != task._fileSelectionVersion:
            entry.handle.prioritize_files(task.priorities())
            entry.appliedSelectionVersion = task._fileSelectionVersion

        if status.is_seeding and not entry.done.done():
            if not task.shouldSeed:
                entry.done.set_result(None)
            elif self._isSeedingLimitReached(task):
                logger.info("{} 自动暂停做种: 分享率 {:.2f}%, 做种时间 {}s",
                            task.name, task.shareRatioPercent, task.seedingTimeSeconds)
                task.stateText = "已自动暂停做种"
                task.shouldSeed = False
                task.isSeeding = False
                entry.done.set_result(None)

        entry.pollCount += 1
        if entry.pollCount % _RESUME_SAVE_INTERVAL == 0:
            try:
                entry.handle.save_resume_data(
                    lt.save_resume_flags_t.flush_disk_cache | lt.save_resume_flags_t.save_info_dict
                )
            except Exception:
                pass

    def _isSeedingLimitReached(self, task: BTTask) -> bool:
        ratioLimit = bittorrentConfig.seedingRatioLimit.value
        if ratioLimit > 0 and task.shareRatioPercent >= ratioLimit:
            return True
        timeLimitMinutes = bittorrentConfig.seedingTimeLimit.value
        if timeLimitMinutes > 0 and task.seedingTimeSeconds >= timeLimitMinutes * 60:
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
