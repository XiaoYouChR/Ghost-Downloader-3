import asyncio
from base64 import b64decode, b64encode
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path, PurePosixPath
from tempfile import gettempdir
from typing import Any
from urllib.parse import unquote, urlparse, urlsplit
from urllib.request import url2pathname

import libtorrent as lt
import niquests
from loguru import logger

from app.bases.interfaces import Worker
from app.bases.models import Task, TaskStage, TaskStatus
from app.supports.config import DEFAULT_HEADERS, VERSION, cfg
from app.supports.utils import getProxies, sanitizeFilename
from .config import bittorrentConfig, getCachedWebTrackers, refreshConfiguredWebTrackers
from .trackers import mergeTrackers

BITTORRENT_USER_AGENT = f"GhostDownloader/{VERSION} libtorrent/{lt.__version__}"


def _storageMode(mode: str) -> int:
    if mode == "allocate":
        return lt.storage_mode_t.storage_mode_allocate
    return lt.storage_mode_t.storage_mode_sparse

def _normalizeTorrentPath(path: str) -> str:
    return str(PurePosixPath(str(path).replace("\\", "/")))


def resolveLocalTorrentPath(source: str) -> Path | None:
    text = str(source).strip()
    if not text:
        return None

    parsed = urlparse(text)
    if parsed.scheme.lower() == "file":
        location = f"//{parsed.netloc}{parsed.path}" if parsed.netloc else parsed.path
        path = Path(url2pathname(unquote(location))).expanduser()
        return path if path.suffix.lower() == ".torrent" else None

    if "://" in text or parsed.scheme.lower() == "magnet":
        return None

    path = Path(text).expanduser()
    return path if path.suffix.lower() == ".torrent" else None


def _encodeBytes(data: bytes) -> str:
    return b64encode(data).decode("ascii")


def _decodeBytes(data: str) -> bytes:
    return b64decode(data.encode("ascii"))


def _proxyTypeForScheme(scheme: str) -> int:
    lowered = scheme.lower()
    if lowered == "http":
        return lt.proxy_type_t.http
    if lowered == "https":
        return lt.proxy_type_t.http_pw
    if lowered == "socks4":
        return lt.proxy_type_t.socks4
    if lowered == "socks5":
        return lt.proxy_type_t.socks5
    return lt.proxy_type_t.none


def _sessionProxySettings(proxies: dict | None) -> dict[str, Any]:
    if proxies is None:
        return {}

    proxyUrl = ""
    for key in ("https", "http"):
        value = str(proxies.get(key) or "").strip()
        if value:
            proxyUrl = value
            break

    if not proxyUrl:
        return {}

    parsed = urlsplit(proxyUrl)
    if not parsed.hostname or not parsed.port:
        return {}

    return {
        "proxy_type": _proxyTypeForScheme(parsed.scheme),
        "proxy_hostname": parsed.hostname,
        "proxy_port": parsed.port,
        "proxy_username": parsed.username or "",
        "proxy_password": parsed.password or "",
        "proxy_hostnames": True,
        "proxy_peer_connections": True,
        "proxy_tracker_connections": True,
        "force_proxy": False,
    }


def _sessionSettings(
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
) -> dict[str, Any]:
    settings = {
        "user_agent": BITTORRENT_USER_AGENT,
        "listen_interfaces": f"0.0.0.0:{listenPort}",
        "connections_limit": connectionsLimit,
        "download_rate_limit": downloadRateLimit,
        "upload_rate_limit": uploadRateLimit,
        "enable_dht": enableDHT,
        "enable_lsd": enableLSD,
        "enable_upnp": enableUPnP,
        "enable_natpmp": enableNATPMP,
    }
    settings.update(_sessionProxySettings(proxies))
    return settings


def _startDiscoveryServices(
    session: lt.session,
    *,
    enableDHT: bool,
    enableLSD: bool,
    enableUPnP: bool,
    enableNATPMP: bool,
):
    if enableDHT:
        session.start_dht()
    if enableLSD:
        session.start_lsd()
    if enableUPnP:
        session.start_upnp()
    if enableNATPMP:
        session.start_natpmp()


def _createSession(
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
    settings = _sessionSettings(
        listenPort=listenPort,
        connectionsLimit=connectionsLimit,
        downloadRateLimit=downloadRateLimit,
        uploadRateLimit=uploadRateLimit,
        enableDHT=enableDHT,
        enableLSD=enableLSD,
        enableUPnP=enableUPnP,
        enableNATPMP=enableNATPMP,
        proxies=proxies,
    )
    if extraSettings:
        settings.update(extraSettings)

    session = lt.session(settings)
    session.set_alert_mask(int(lt.alert.category_t.all_categories))
    _startDiscoveryServices(
        session,
        enableDHT=enableDHT,
        enableLSD=enableLSD,
        enableUPnP=enableUPnP,
        enableNATPMP=enableNATPMP,
    )
    return session


def _torrentBytesFromInfo(ti: lt.torrent_info) -> bytes:
    return lt.bencode(lt.create_torrent(ti).generate())


def _extractTrackers(ti: lt.torrent_info) -> list[str]:
    trackers: list[str] = []
    for tracker in list(ti.trackers()):
        url = str(tracker.url).strip()
        if url and url not in trackers:
            trackers.append(url)
    return trackers


def _isPadFile(files: lt.file_storage, index: int) -> bool:
    return bool(files.file_flags(index) & lt.file_storage.flag_pad_file)


def _metadataTempPath() -> Path:
    return Path(gettempdir()) / "ghost_downloader_bt_metadata"


def _forceMetadataPeerDiscovery(handle: lt.torrent_handle, *, enableDHT: bool):
    try:
        handle.force_reannounce(0, -1, lt.reannounce_flags_t.ignore_min_interval)
    except Exception:
        handle.force_reannounce()

    if enableDHT:
        try:
            handle.force_dht_announce()
        except Exception:
            pass


def _addTrackersToHandle(handle: lt.torrent_handle, trackers: list[str], knownTrackers: set[str]) -> bool:
    added = False
    for tracker in trackers:
        if tracker in knownTrackers:
            continue
        handle.add_tracker({"url": tracker, "tier": 0})
        knownTrackers.add(tracker)
        added = True
    return added


def _shareRatioPercent(status: lt.torrent_status) -> float:
    downloaded = int(status.all_time_download or status.total_wanted_done or status.total_done)
    if downloaded == 0:
        return 0.0
    return status.all_time_upload / downloaded * 100


def _durationSeconds(value: int | float | timedelta) -> int:
    if isinstance(value, timedelta):
        return int(value.total_seconds())
    return int(value)


def _seedingSeconds(status: lt.torrent_status) -> int:
    return _durationSeconds(status.seeding_duration or status.seeding_time)


async def _resolveAdditionalTrackers() -> list[str]:
    if not bittorrentConfig.enableWebTrackers.value:
        return []

    if bittorrentConfig.autoRefreshWebTrackers.value:
        try:
            return await refreshConfiguredWebTrackers()
        except Exception as e:
            logger.opt(exception=e).warning("刷新 Web Tracker 失败，回退到缓存 {}", repr(e))

    return getCachedWebTrackers()


@dataclass
class BitTorrentFile:
    index: int
    path: str
    size: int
    selected: bool = True
    priority: int = 4
    downloadedBytes: int = 0
    completed: bool = False

    def __post_init__(self):
        self.path = _normalizeTorrentPath(self.path)


@dataclass
class BitTorrentTaskStage(TaskStage):
    resolvePath: str

    def __post_init__(self):
        self.stateText = ""
        self.peerCount = 0
        self.seedCount = 0
        self.downloadRate = 0
        self.uploadRate = 0

    def reset(self, notifyTask: bool = True):
        super().reset(notifyTask=notifyTask)
        self.stateText = ""
        self.peerCount = 0
        self.seedCount = 0
        self.downloadRate = 0
        self.uploadRate = 0


@dataclass
class BitTorrentTask(Task):
    sourceType: str
    torrentData: str
    resumeData: str = field(default="")
    trackers: list[str] = field(default_factory=list)
    files: list[BitTorrentFile] = field(default_factory=list)
    proxies: dict | None = field(default_factory=getProxies)
    listenPort: int = field(default_factory=lambda: bittorrentConfig.listenPort.value)
    connectionsLimit: int = field(default_factory=lambda: bittorrentConfig.connectionsLimit.value)
    downloadRateLimit: int = field(default_factory=lambda: bittorrentConfig.downloadRateLimit.value)
    uploadRateLimit: int = field(default_factory=lambda: bittorrentConfig.uploadRateLimit.value)
    enableDHT: bool = field(default_factory=lambda: bittorrentConfig.enableDHT.value)
    enableLSD: bool = field(default_factory=lambda: bittorrentConfig.enableLSD.value)
    enableUPnP: bool = field(default_factory=lambda: bittorrentConfig.enableUPnP.value)
    enableNATPMP: bool = field(default_factory=lambda: bittorrentConfig.enableNATPMP.value)
    sequentialDownload: bool = field(default_factory=lambda: bittorrentConfig.sequentialDownload.value)
    storageMode: str = field(default_factory=lambda: bittorrentConfig.storageMode.value)
    seedRatioLimitPercent: int = field(default_factory=lambda: bittorrentConfig.seedRatioLimitPercent.value)
    seedTimeLimitMinutes: int = field(default_factory=lambda: bittorrentConfig.seedTimeLimitMinutes.value)
    saveMagnetTorrentFile: bool = field(default_factory=lambda: bittorrentConfig.saveMagnetTorrentFile.value)
    shareRatioPercent: float = field(default=0)
    seedingTimeSeconds: int = field(default=0)
    isSeeding: bool = field(default=False)

    def __post_init__(self):
        self.files = [
            item if isinstance(item, BitTorrentFile) else BitTorrentFile(**item)
            for item in self.files
        ]
        self.fileSelectionVersion = 0
        self.title = sanitizeFilename(self.title, fallback="torrent")
        super().__post_init__()
        self._recalculateSelection()
        self.syncStagePaths()

    @property
    def resolvePath(self) -> str:
        return str(self.path / self.title)

    @property
    def stage(self) -> BitTorrentTaskStage:
        return self.stages[0]

    @property
    def magnetTorrentPath(self) -> Path | None:
        if self.sourceType != "magnet" or not self.saveMagnetTorrentFile:
            return None
        return self.path / f"{self.title}.torrent"

    @property
    def selectedFileCount(self) -> int:
        return sum(1 for file in self.files if file.selected)

    @property
    def totalFileCount(self) -> int:
        return len(self.files)

    @property
    def isSingleFileTorrent(self) -> bool:
        return len(self.files) == 1

    @property
    def hasUnselectedFiles(self) -> bool:
        return self.selectedFileCount < self.totalFileCount

    def syncStagePaths(self):
        self.stage.resolvePath = self.resolvePath

    def mappedRelativePath(self, file: BitTorrentFile) -> str:
        if self.isSingleFileTorrent:
            return self.title.replace("\\", "/")

        parts = list(PurePosixPath(file.path).parts)
        parts[0] = self.title
        return str(PurePosixPath(*parts))

    def filePriorities(self) -> list[int]:
        return [file.priority if file.selected else 0 for file in self.files]

    def _recalculateSelection(self):
        self.fileSize = sum(file.size for file in self.files if file.selected)

    def updateSelectedFiles(self, selectedIndexes: set[int]):
        if not selectedIndexes:
            raise ValueError("至少需要选择一个文件")

        changed = False
        for file in self.files:
            selected = file.index in selectedIndexes
            priority = 4 if selected else 0
            if file.selected != selected or file.priority != priority:
                changed = True
            file.selected = selected
            file.priority = priority
            if not selected:
                file.downloadedBytes = 0
                file.completed = False

        if not changed:
            return

        self.fileSelectionVersion += 1
        self._recalculateSelection()

    def reopenForAdditionalFiles(self) -> bool:
        if self.stage.status != TaskStatus.COMPLETED:
            return False

        if not any(file.selected and not file.completed for file in self.files):
            return False

        self.isSeeding = False
        self.stage.stateText = "已添加新的下载文件"
        self.stage.setStatus(TaskStatus.PAUSED)
        self.stage.receivedBytes = sum(file.downloadedBytes for file in self.files if file.selected)
        if self.fileSize > 0:
            self.stage.progress = self.stage.receivedBytes / self.fileSize * 100
        else:
            self.stage.progress = 0
        return True

    def updateFileProgress(self, progresses: list[int]):
        for file in self.files:
            if not file.selected:
                file.downloadedBytes = 0
                file.completed = False
                continue
            downloaded = int(progresses[file.index]) if file.index < len(progresses) else 0
            file.downloadedBytes = downloaded
            file.completed = file.size > 0 and downloaded >= file.size

    def applyPayloadToTask(self, payload: dict[str, Any]):
        super().applyPayloadToTask(payload)
        if "proxies" in payload:
            self.proxies = payload.get("proxies")
        self.syncStagePaths()

    def reset(self) -> TaskStatus:
        result = super().reset()
        self.resumeData = ""
        self.shareRatioPercent = 0
        self.seedingTimeSeconds = 0
        self.isSeeding = False
        for file in self.files:
            file.downloadedBytes = 0
            file.completed = False
        return result

    def occupiesDownloadSlot(self) -> bool:
        return self.status == TaskStatus.RUNNING and not self.isSeeding

    def willOccupyDownloadSlotWhenStarted(self) -> bool:
        return not self.isSeeding

    async def run(self):
        try:
            for stage in self.iterRunnableStages():
                await BitTorrentWorker(stage).run()
        except asyncio.CancelledError:
            logger.info(f"{self.title} 停止下载")
            raise
        except Exception as e:
            if not self.stage.error:
                self.stage.setError(e)
            logger.opt(exception=e).error("{} 下载失败", self.title)
            raise

    def __hash__(self):
        return hash(self.taskId)


class BitTorrentWorker(Worker):
    def __init__(self, stage: BitTorrentTaskStage):
        super().__init__(stage)
        self.stage = stage
        self.task: BitTorrentTask = stage._task
        self.session: lt.session | None = None
        self.handle: lt.torrent_handle | None = None
        self._appliedSelectionVersion = -1
        self._seedingTimeBaseSeconds = self.task.seedingTimeSeconds
        self._sessionSeedingStartSeconds: int | None = None

    def _applyTaskParams(self, params: lt.add_torrent_params):
        params.save_path = str(self.task.path)
        params.storage_mode = _storageMode(self.task.storageMode)
        params.file_priorities = self.task.filePriorities()
        params.download_limit = self.task.downloadRateLimit
        params.upload_limit = self.task.uploadRateLimit
        params.max_connections = self.task.connectionsLimit
        if self.task.trackers:
            params.trackers = self.task.trackers.copy()

    def _buildAddTorrentParams(self) -> lt.add_torrent_params:
        if self.task.resumeData:
            try:
                params = lt.read_resume_data(_decodeBytes(self.task.resumeData))
            except Exception as e:
                logger.opt(exception=e).warning("读取 BitTorrent resume 数据失败，改用种子元数据 {}", self.task.title)
            else:
                self._applyTaskParams(params)
                return params

        params = lt.add_torrent_params()
        params.ti = lt.torrent_info(_decodeBytes(self.task.torrentData))
        self._applyTaskParams(params)
        if self.task.sequentialDownload:
            params.flags = int(params.flags) | int(lt.torrent_flags.sequential_download)
        else:
            params.flags = int(params.flags) & ~int(lt.torrent_flags.sequential_download)
        params.flags = int(params.flags) | int(lt.torrent_flags.update_subscribe)
        return params

    def _applyRenameMapping(self):
        if self.handle is None:
            return

        for file in self.task.files:
            mappedPath = self.task.mappedRelativePath(file)
            if mappedPath == file.path:
                continue
            self.handle.rename_file(file.index, mappedPath)

    def _applyFileSelection(self):
        if self.handle is None or self._appliedSelectionVersion == self.task.fileSelectionVersion:
            return
        self.handle.prioritize_files(self.task.filePriorities())
        self.handle.set_sequential_download(self.task.sequentialDownload)
        self.handle.set_max_connections(self.task.connectionsLimit)
        self.handle.set_download_limit(self.task.downloadRateLimit)
        self.handle.set_upload_limit(self.task.uploadRateLimit)
        self._appliedSelectionVersion = self.task.fileSelectionVersion

    def _stateText(self, status: lt.torrent_status) -> str:
        mapping = {
            "checking_files": "校验已有文件",
            "checking_resume_data": "检查续传状态",
            "downloading_metadata": "获取元数据",
            "downloading": "下载中",
            "finished": "下载完成",
            "seeding": "做种中",
            "allocating": "分配文件中",
            "queued_for_checking": "等待校验",
        }
        return mapping.get(status.state.name, status.state.name)

    def _syncFromStatus(self, status: lt.torrent_status):
        wasSeeding = self.task.isSeeding
        totalWanted = int(status.total_wanted)
        totalWantedDone = int(status.total_wanted_done)
        isSeeding = bool(status.is_seeding)
        sessionSeedingSeconds = _seedingSeconds(status)
        self.stage.stateText = self._stateText(status)
        self.stage.peerCount = int(status.num_peers)
        self.stage.seedCount = int(status.num_seeds)
        self.task.isSeeding = isSeeding
        self.stage.downloadRate = int(status.download_rate)
        self.stage.uploadRate = int(status.upload_rate)
        self.task.shareRatioPercent = _shareRatioPercent(status)
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
        self.stage.speed = self.stage.downloadRate
        self.stage.receivedBytes = totalWantedDone

        if totalWanted > 0:
            self.task.fileSize = totalWanted
            self.stage.progress = totalWantedDone / totalWanted * 100
        elif self.task.fileSize > 0:
            self.stage.progress = self.stage.receivedBytes / self.task.fileSize * 100
        else:
            self.stage.progress = 0

        if wasSeeding != self.task.isSeeding:
            from app.services.core_service import coreService

            coreService.notifyTaskSchedulingChanged()

    def _syncFileProgress(self):
        if self.handle is None:
            return
        try:
            progresses = list(self.handle.file_progress())
        except Exception:
            return
        self.task.updateFileProgress(progresses)

    def _seedPauseReason(self) -> str:
        if not self.task.isSeeding:
            return ""

        ratioLimit = self.task.seedRatioLimitPercent
        if ratioLimit > 0 and self.task.shareRatioPercent >= ratioLimit:
            return "分享率达到 {0:.2f}% / {1}%".format(self.task.shareRatioPercent, ratioLimit)

        timeLimitMinutes = self.task.seedTimeLimitMinutes
        if timeLimitMinutes > 0 and self.task.seedingTimeSeconds >= timeLimitMinutes * 60:
            return "做种时间达到 {0} / {1} 分钟".format(
                round(self.task.seedingTimeSeconds / 60),
                timeLimitMinutes,
            )

        return ""

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

    async def _saveResumeData(self) -> str:
        if self.handle is None or self.session is None:
            return ""

        try:
            self.handle.save_resume_data(
                lt.save_resume_flags_t.flush_disk_cache | lt.save_resume_flags_t.save_info_dict
            )
        except Exception as e:
            logger.opt(exception=e).warning("保存 BitTorrent resume 数据失败 {}", self.task.title)
            return ""

        deadline = asyncio.get_running_loop().time() + 10
        while asyncio.get_running_loop().time() < deadline:
            alerts = list(self.session.pop_alerts())
            for alert in alerts:
                if isinstance(alert, lt.save_resume_data_alert):
                    return _encodeBytes(lt.write_resume_data_buf(alert.params))
                if isinstance(alert, lt.save_resume_data_failed_alert):
                    logger.warning("保存 BitTorrent resume 数据失败 {}: {}", self.task.title, alert.message())
                    return ""
            self._handleAlerts(alerts, raiseOnError=False)
            await asyncio.sleep(0.1)

        logger.warning("等待 BitTorrent resume 数据超时 {}", self.task.title)
        return ""

    async def _shutdownSession(self):
        if self.handle is None or self.session is None:
            return
        try:
            self.session.remove_torrent(self.handle)
        except Exception:
            pass

    def _saveMagnetTorrentFile(self):
        torrentPath = self.task.magnetTorrentPath
        if torrentPath is None:
            return

        try:
            torrentPath.write_bytes(_decodeBytes(self.task.torrentData))
        except Exception as e:
            logger.opt(exception=e).warning("保存 magnet 种子文件失败 {}", self.task.title)

    async def run(self):
        if self.task.selectedFileCount <= 0:
            self.stage.setStatus(TaskStatus.FAILED)
            raise RuntimeError("至少需要选择一个文件")

        Path(self.task.path).mkdir(parents=True, exist_ok=True)
        self._saveMagnetTorrentFile()

        self.session = _createSession(
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
            params = self._buildAddTorrentParams()
            self.handle = self.session.add_torrent(params)
            self._applyRenameMapping()
            self._applyFileSelection()
            self.session.resume()
            self.handle.resume()

            while True:
                alerts = list(self.session.pop_alerts())
                self._handleAlerts(alerts)
                self._applyFileSelection()

                status = self.handle.status()
                self._syncFromStatus(status)
                self._syncFileProgress()

                pauseReason = self._seedPauseReason()
                if pauseReason:
                    logger.info("{} 自动暂停做种: {}", self.task.title, pauseReason)
                    self.task.resumeData = await self._saveResumeData()
                    self.task.isSeeding = False
                    self.stage.stateText = "已自动暂停做种"
                    self.stage.setStatus(TaskStatus.COMPLETED)
                    self.stage.progress = 100
                    self.stage.speed = 0
                    return

                await asyncio.sleep(1)
        except asyncio.CancelledError:
            self.task.resumeData = await asyncio.shield(self._saveResumeData())
            wasSeeding = self.task.isSeeding
            self.stage.stateText = "已暂停做种" if wasSeeding else "已暂停下载"
            self.stage.setStatus(TaskStatus.PAUSED)
            raise
        except Exception as e:
            self.task.resumeData = await self._saveResumeData()
            self.stage.setError(e)
            raise
        finally:
            await self._shutdownSession()
            self.handle = None
            self.session = None


async def _fetchTorrentBytes(payload: dict) -> bytes:
    url = str(payload["url"]).strip()
    headers = payload.get("headers", DEFAULT_HEADERS)
    proxies = payload.get("proxies", getProxies())

    client = niquests.AsyncSession(headers=headers, timeout=30, happy_eyeballs=True)
    client.trust_env = False

    try:
        response = await client.get(
            url,
            proxies=proxies,
            verify=cfg.SSLVerify.value,
            allow_redirects=True,
        )
        try:
            response.raise_for_status()
            return bytes(response.content)
        finally:
            response.close()
    finally:
        await client.close()


def _readLocalTorrentBytes(source: str) -> bytes:
    torrentPath = resolveLocalTorrentPath(source)
    if torrentPath is None:
        raise ValueError("不是有效的本地 .torrent 文件路径")
    return torrentPath.resolve().read_bytes()


async def _resolveMagnetMetadata(payload: dict) -> tuple[lt.torrent_info, list[str], bytes]:
    url = str(payload["url"]).strip()
    proxies = payload.get("proxies", getProxies())
    enableDHT = bittorrentConfig.enableDHT.value
    enableWebTrackers = bittorrentConfig.enableWebTrackers.value
    initialWebTrackers = getCachedWebTrackers() if enableWebTrackers else []
    session = _createSession(
        listenPort=bittorrentConfig.listenPort.value,
        connectionsLimit=bittorrentConfig.connectionsLimit.value,
        downloadRateLimit=bittorrentConfig.downloadRateLimit.value,
        uploadRateLimit=bittorrentConfig.uploadRateLimit.value,
        enableDHT=enableDHT,
        enableLSD=bittorrentConfig.enableLSD.value,
        enableUPnP=bittorrentConfig.enableUPnP.value,
        enableNATPMP=bittorrentConfig.enableNATPMP.value,
        proxies=proxies,
        extraSettings={
            "announce_to_all_trackers": True,
            "announce_to_all_tiers": True,
        },
    )

    params = lt.parse_magnet_uri(url)
    params.trackers = mergeTrackers(params.trackers.copy(), initialWebTrackers)
    _metadataTempPath().mkdir(parents=True, exist_ok=True)
    params.save_path = str(_metadataTempPath())
    params.storage_mode = _storageMode("sparse")
    params.flags = int(params.flags) | int(lt.torrent_flags.default_dont_download)
    params.flags = int(params.flags) | int(lt.torrent_flags.update_subscribe)

    webTrackerTask: asyncio.Task[list[str]] | None = None
    if enableWebTrackers and bittorrentConfig.autoRefreshWebTrackers.value:
        webTrackerTask = asyncio.create_task(_resolveAdditionalTrackers())

    handle = session.add_torrent(params)
    session.resume()
    handle.resume()
    knownTrackers = set(params.trackers)
    appliedRefreshedTrackers = False
    _forceMetadataPeerDiscovery(handle, enableDHT=enableDHT)

    try:
        deadline = asyncio.get_running_loop().time() + bittorrentConfig.metadataTimeout.value
        while asyncio.get_running_loop().time() < deadline:
            if webTrackerTask is not None and webTrackerTask.done() and not appliedRefreshedTrackers:
                appliedRefreshedTrackers = True
                refreshedTrackers = webTrackerTask.result()
                params.trackers = mergeTrackers(params.trackers.copy(), refreshedTrackers)
                if _addTrackersToHandle(handle, refreshedTrackers, knownTrackers):
                    _forceMetadataPeerDiscovery(handle, enableDHT=enableDHT)

            alerts = list(session.pop_alerts())
            for alert in alerts:
                if isinstance(alert, lt.metadata_received_alert):
                    ti = handle.torrent_file()
                    if ti is not None and ti.is_valid():
                        return ti, params.trackers.copy(), _torrentBytesFromInfo(ti)
                if isinstance(alert, lt.metadata_failed_alert):
                    raise RuntimeError(alert.message())
                if isinstance(alert, (lt.torrent_error_alert, lt.file_error_alert)):
                    raise RuntimeError(alert.message())

            status = handle.status()
            if status.has_metadata:
                ti = handle.torrent_file()
                if ti is not None and ti.is_valid():
                    return ti, params.trackers.copy(), _torrentBytesFromInfo(ti)

            await asyncio.sleep(0.2)

        raise TimeoutError("等待 magnet 元数据超时")
    finally:
        if webTrackerTask is not None and not webTrackerTask.done():
            webTrackerTask.cancel()
            with suppress(asyncio.CancelledError):
                await webTrackerTask
        try:
            session.remove_torrent(handle)
        except Exception:
            pass


def buildTaskFromTorrentInfo(
    ti: lt.torrent_info,
    *,
    payload: dict,
    sourceType: str,
    sourceUrl: str,
    torrentBytes: bytes,
    trackers: list[str],
) -> BitTorrentTask:
    files = ti.files()
    entries: list[BitTorrentFile] = []
    for index in range(ti.num_files()):
        if _isPadFile(files, index):
            continue
        entries.append(
            BitTorrentFile(
                index=index,
                path=files.file_path(index),
                size=int(files.file_size(index)),
            )
        )

    if not entries:
        raise ValueError("该种子中没有可下载的普通文件")

    rootName = sanitizeFilename(PurePosixPath(entries[0].path).parts[0], fallback="torrent")
    title = sanitizeFilename(Path(entries[0].path).name, fallback="torrent") if len(entries) == 1 else rootName
    task = BitTorrentTask(
        title=title,
        url=sourceUrl,
        fileSize=sum(entry.size for entry in entries),
        path=Path(payload.get("path", cfg.downloadFolder.value)),
        stages=[BitTorrentTaskStage(stageIndex=1, resolvePath="")],
        sourceType=sourceType,
        torrentData=_encodeBytes(torrentBytes),
        trackers=trackers or _extractTrackers(ti),
        files=entries,
        proxies=payload.get("proxies", getProxies()),
        listenPort=bittorrentConfig.listenPort.value,
        connectionsLimit=bittorrentConfig.connectionsLimit.value,
        downloadRateLimit=bittorrentConfig.downloadRateLimit.value,
        uploadRateLimit=bittorrentConfig.uploadRateLimit.value,
        enableDHT=bittorrentConfig.enableDHT.value,
        enableLSD=bittorrentConfig.enableLSD.value,
        enableUPnP=bittorrentConfig.enableUPnP.value,
        enableNATPMP=bittorrentConfig.enableNATPMP.value,
        sequentialDownload=bittorrentConfig.sequentialDownload.value,
        storageMode=bittorrentConfig.storageMode.value,
        seedRatioLimitPercent=bittorrentConfig.seedRatioLimitPercent.value,
        seedTimeLimitMinutes=bittorrentConfig.seedTimeLimitMinutes.value,
        saveMagnetTorrentFile=bittorrentConfig.saveMagnetTorrentFile.value,
    )
    return task


async def parse(payload: dict) -> BitTorrentTask:
    url = str(payload["url"]).strip()
    localTorrentPath = resolveLocalTorrentPath(url)
    if localTorrentPath is not None:
        torrentBytes, webTrackers = await asyncio.gather(
            asyncio.to_thread(_readLocalTorrentBytes, url),
            _resolveAdditionalTrackers(),
        )
        ti = lt.torrent_info(torrentBytes)
        return buildTaskFromTorrentInfo(
            ti,
            payload=payload,
            sourceType="torrent",
            sourceUrl=str(localTorrentPath.resolve()),
            torrentBytes=torrentBytes,
            trackers=mergeTrackers(_extractTrackers(ti), webTrackers),
        )

    parsedUrl = urlparse(url)

    if parsedUrl.scheme.lower() == "magnet":
        ti, trackers, torrentBytes = await _resolveMagnetMetadata(payload)
        return buildTaskFromTorrentInfo(
            ti,
            payload=payload,
            sourceType="magnet",
            sourceUrl=url,
            torrentBytes=torrentBytes,
            trackers=trackers,
        )

    torrentBytes, webTrackers = await asyncio.gather(
        _fetchTorrentBytes(payload),
        _resolveAdditionalTrackers(),
    )
    ti = lt.torrent_info(torrentBytes)
    return buildTaskFromTorrentInfo(
        ti,
        payload=payload,
        sourceType="torrent",
        sourceUrl=url,
        torrentBytes=torrentBytes,
        trackers=mergeTrackers(_extractTrackers(ti), webTrackers),
    )
