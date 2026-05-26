import asyncio
from base64 import b64decode, b64encode
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import libtorrent as lt
from loguru import logger

from app.bases.interfaces import Worker
from app.bases.models import TaskStage, TaskStatus
from app.services.core_service import coreService
from app.supports.config import VERSION
from .task import BTTask

BITTORRENT_USER_AGENT = f"GhostDownloader/{VERSION} libtorrent/{lt.__version__}"

_STATE_TEXT_MAP = {
    "checking_files": "校验已有文件",
    "checking_resume_data": "检查续传状态",
    "downloading_metadata": "获取元数据",
    "downloading": "下载中",
    "finished": "下载完成",
    "seeding": "做种中",
    "allocating": "分配文件中",
    "queued_for_checking": "等待校验",
}


def createSession(
    *,
    listenPort: int,
    connectionsLimit: int,
    downloadRateLimit: int,
    uploadRateLimit: int,
    enableDHT: bool,
    enableLSD: bool,
    enableUPnP: bool,
    enableNATPMP: bool,
    proxies: dict | None,
    extraSettings: dict[str, Any] | None = None,
) -> lt.session:
    settings: dict[str, Any] = {
        "user_agent": BITTORRENT_USER_AGENT,
        "listen_interfaces": f"0.0.0.0:{listenPort}",
        "connections_limit": connectionsLimit,
        "download_rate_limit": downloadRateLimit,
        "upload_rate_limit": uploadRateLimit,
        "enable_dht": enableDHT,
        "enable_lsd": enableLSD,
        "enable_upnp": enableUPnP,
        "enable_natpmp": enableNATPMP,
        "alert_mask": lt.alert.category_t.all_categories,
    }

    if proxies:
        proxyUrl = str(proxies.get("https") or proxies.get("http") or "").strip()
        if proxyUrl:
            parsed = urlsplit(proxyUrl)
            scheme = parsed.scheme.lower()
            # 只接受 SOCKS5: HTTP/HTTPS/SOCKS4 不支持 UDP, 配上反而会拖垮 DHT 与 UDP tracker
            if scheme == "socks5" and parsed.hostname and parsed.port:
                hasCredentials = bool(parsed.username or parsed.password)
                settings.update({
                    "proxy_type": lt.proxy_type_t.socks5_pw if hasCredentials else lt.proxy_type_t.socks5,
                    "proxy_hostname": parsed.hostname,
                    "proxy_port": parsed.port,
                    "proxy_username": parsed.username or "",
                    "proxy_password": parsed.password or "",
                    "proxy_hostnames": True,
                    "proxy_peer_connections": True,
                    "proxy_tracker_connections": True,
                    "force_proxy": False,
                })

    if extraSettings:
        settings.update(extraSettings)

    return lt.session(settings)


class BTWorker(Worker):
    def __init__(self, stage: TaskStage):
        super().__init__(stage)
        self.stage = stage
        self.task: BTTask = stage._task
        self.session: lt.session | None = None
        self.handle: lt.torrent_handle | None = None
        self._appliedSettingsVersion = -1
        self._seedingTimeBaseSeconds = self.task.seedingTimeSeconds
        self._sessionSeedingStartSeconds: int | None = None

    def _buildArgs(self) -> lt.add_torrent_params:
        if self.task.resumeData:
            try:
                params = lt.read_resume_data(b64decode(self.task.resumeData))
            except Exception as e:
                logger.opt(exception=e).warning("读取 BitTorrent resume 数据失败,改用种子元数据 {}", self.task.title)
                params = None
        else:
            params = None

        if params is None:
            params = lt.add_torrent_params()
            params.ti = lt.torrent_info(b64decode(self.task.torrentData))
            if self.task.sequentialDownload:
                params.flags |= lt.torrent_flags.sequential_download
            else:
                params.flags &= ~lt.torrent_flags.sequential_download
            params.flags |= lt.torrent_flags.update_subscribe

        # 即使从 resume 恢复也要覆盖参数,确保用户修改的设置生效
        params.save_path = str(self.task.path)
        params.storage_mode = lt.storage_mode_t.storage_mode_allocate if self.task.storageMode == "allocate" else lt.storage_mode_t.storage_mode_sparse
        params.file_priorities = self.task.priorities()
        params.download_limit = self.task.downloadRateLimit
        params.upload_limit = self.task.uploadRateLimit
        params.max_connections = self.task.connectionsLimit
        if self.task.trackers:
            params.trackers = self.task.trackers.copy()
        return params

    def _mapFiles(self):
        if self.handle is None:
            return
        for file in self.task.files:
            mappedPath = self.task.mapPath(file)
            if mappedPath == file.path:
                continue
            self.handle.rename_file(file.index, mappedPath)

    def _updateSettings(self):
        if self.handle is None or self._appliedSettingsVersion == self.task.fileSelectionVersion:
            return
        self.handle.prioritize_files(self.task.priorities())
        self.handle.set_sequential_download(self.task.sequentialDownload)
        self.handle.set_max_connections(self.task.connectionsLimit)
        self.handle.set_download_limit(self.task.downloadRateLimit)
        self.handle.set_upload_limit(self.task.uploadRateLimit)
        self._appliedSettingsVersion = self.task.fileSelectionVersion

    def _updateStatus(self, status: lt.torrent_status):
        wasSeeding = self.task.isSeeding
        totalWanted = status.total_wanted
        totalWantedDone = status.total_wanted_done
        isSeeding = status.is_seeding
        sessionSeedingSeconds = int(status.seeding_duration.total_seconds())

        self.task.stateText = _STATE_TEXT_MAP.get(status.state.name, status.state.name)
        self.task.peerCount = status.num_peers
        self.task.seedCount = status.num_seeds
        self.task.isSeeding = isSeeding
        self.task._updateSlot()
        self.task.downloadRate = status.download_rate
        self.task.uploadRate = status.upload_rate

        downloaded = status.all_time_download or status.total_wanted_done or status.total_done
        self.task.shareRatioPercent = (status.all_time_upload / downloaded * 100) if downloaded > 0 else 0.0

        if isSeeding:
            if not wasSeeding:
                self._seedingTimeBaseSeconds = self.task.seedingTimeSeconds
                self._sessionSeedingStartSeconds = sessionSeedingSeconds
            elif self._sessionSeedingStartSeconds is None:
                self._sessionSeedingStartSeconds = sessionSeedingSeconds
            self.task.seedingTimeSeconds = self._seedingTimeBaseSeconds + max(
                0,
                sessionSeedingSeconds - self._sessionSeedingStartSeconds,
            )
        elif wasSeeding:
            self._seedingTimeBaseSeconds = self.task.seedingTimeSeconds
            self._sessionSeedingStartSeconds = None

        self.stage.speed = self.task.downloadRate
        self.stage.receivedBytes = totalWantedDone

        if totalWanted > 0:
            self.task.fileSize = totalWanted
            self.stage.progress = totalWantedDone / totalWanted * 100
        elif self.task.fileSize > 0:
            self.stage.progress = self.stage.receivedBytes / self.task.fileSize * 100
        else:
            self.stage.progress = 0

        if wasSeeding != self.task.isSeeding:
            coreService.rebalance()

    def _updateFiles(self):
        if self.handle is None:
            return
        self.task.updateProgress(self.handle.file_progress())

    def _shouldStopSeeding(self) -> bool:
        if not self.task.isSeeding:
            return False

        ratioLimit = self.task.seedRatioLimitPercent
        if ratioLimit > 0 and self.task.shareRatioPercent >= ratioLimit:
            logger.info(
                "{} 自动暂停做种: 分享率达到 {:.2f}% / {}%",
                self.task.title, self.task.shareRatioPercent, ratioLimit,
            )
            return True

        timeLimitMinutes = self.task.seedTimeLimitMinutes
        if timeLimitMinutes > 0 and self.task.seedingTimeSeconds >= timeLimitMinutes * 60:
            logger.info(
                "{} 自动暂停做种: 做种时间达到 {} / {} 分钟",
                self.task.title, round(self.task.seedingTimeSeconds / 60), timeLimitMinutes,
            )
            return True

        return False

    def _handleAlerts(self, alerts: list[lt.alert], *, raiseOnError: bool = True):
        for alert in alerts:
            if isinstance(alert, lt.file_completed_alert):
                for file in self.task.files:
                    if file.index == alert.index:
                        file.completed = True
                        file.downloadedBytes = file.size
                        break
                continue

            if isinstance(alert, lt.fastresume_rejected_alert):
                logger.warning("BitTorrent fastresume 被拒绝 {}: {}", self.task.title, alert.message())
                self.task.resumeData = ""
                continue

            if not raiseOnError:
                continue

            if isinstance(
                alert,
                (
                    lt.file_error_alert,
                    lt.metadata_failed_alert,
                    lt.torrent_error_alert,
                    lt.hash_failed_alert,
                ),
            ):
                raise RuntimeError(alert.message())

    async def _saveResume(self):
        if self.handle is None or self.session is None:
            self.task.resumeData = ""
            return

        try:
            self.handle.save_resume_data(
                lt.save_resume_flags_t.flush_disk_cache | lt.save_resume_flags_t.save_info_dict
            )
        except Exception as e:
            logger.opt(exception=e).warning("保存 BitTorrent resume 数据失败 {}", self.task.title)
            self.task.resumeData = ""
            return

        deadline = asyncio.get_running_loop().time() + 10
        while asyncio.get_running_loop().time() < deadline:
            alerts = list(self.session.pop_alerts())
            for alert in alerts:
                if isinstance(alert, lt.save_resume_data_alert):
                    self.task.resumeData = b64encode(lt.write_resume_data_buf(alert.params)).decode()
                    return
                if isinstance(alert, lt.save_resume_data_failed_alert):
                    logger.warning("保存 BitTorrent resume 数据失败 {}: {}", self.task.title, alert.message())
                    self.task.resumeData = ""
                    return
            self._handleAlerts(alerts, raiseOnError=False)
            await asyncio.sleep(0.1)

        logger.warning("等待 BitTorrent resume 数据超时 {}", self.task.title)
        self.task.resumeData = ""

    def _saveMagnetFile(self):
        torrentPath = self.task.magnetTorrentPath
        if torrentPath is None:
            return
        try:
            torrentPath.write_bytes(b64decode(self.task.torrentData))
        except Exception as e:
            logger.opt(exception=e).warning("保存 magnet 种子文件失败 {}", self.task.title)

    async def run(self):
        if self.task.countSelected <= 0:
            self.stage.setStatus(TaskStatus.FAILED)
            raise RuntimeError("至少需要选择一个文件")

        target = Path(self.task.outputFolder)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch() if self.task.isSingleFile else target.mkdir()
        self._saveMagnetFile()

        self.session = createSession(
            listenPort=self.task.listenPort,
            connectionsLimit=self.task.connectionsLimit,
            downloadRateLimit=self.task.downloadRateLimit,
            uploadRateLimit=self.task.uploadRateLimit,
            enableDHT=self.task.enableDHT,
            enableLSD=self.task.enableLSD,
            enableUPnP=self.task.enableUPnP,
            enableNATPMP=self.task.enableNATPMP,
            proxies=self.task.proxies,
        )

        try:
            params = self._buildArgs()
            self.handle = self.session.add_torrent(params)
            self._mapFiles()
            self._updateSettings()
            self.session.resume()
            self.handle.resume()
            self.handle.force_reannounce(0, -1, lt.reannounce_flags_t.ignore_min_interval)
            if self.task.enableDHT:
                self.handle.force_dht_announce()

            while True:
                alerts = list(self.session.pop_alerts())
                self._handleAlerts(alerts)
                self._updateSettings()

                status = self.handle.status()
                self._updateStatus(status)
                self._updateFiles()

                if self._shouldStopSeeding():
                    await self._saveResume()
                    self.task.isSeeding = False
                    self.task.stateText = "已自动暂停做种"
                    self.stage.setStatus(TaskStatus.COMPLETED)
                    self.stage.progress = 100
                    self.stage.speed = 0
                    return

                await asyncio.sleep(1)
        except asyncio.CancelledError:
            await asyncio.shield(self._saveResume())
            wasSeeding = self.task.isSeeding
            self.task.stateText = "已暂停做种" if wasSeeding else "已暂停下载"
            self.stage.setStatus(TaskStatus.PAUSED)
            raise
        except Exception as e:
            await self._saveResume()
            self.stage.setError(e)
            raise
        finally:
            if self.session is not None and self.handle is not None:
                try:
                    self.session.remove_torrent(self.handle)
                except Exception:
                    pass
            self.handle = None
            self.session = None
