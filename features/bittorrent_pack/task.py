import asyncio
from base64 import b64decode, b64encode
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
from app.supports.utils import getProxies, toSafeFilename, splitRequestHeadersAndCookies
from .config import bittorrentConfig, getCachedWebTrackers, refreshConfiguredWebTrackers
from .trackers import mergeTrackers

BITTORRENT_USER_AGENT = f"GhostDownloader/{VERSION} libtorrent/{lt.__version__}"

_PROXY_TYPE_MAP = {
    "http": lt.proxy_type_t.http,
    "https": lt.proxy_type_t.http_pw,
    "socks4": lt.proxy_type_t.socks4,
    "socks5": lt.proxy_type_t.socks5,
}

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
    }

    if proxies:
        proxyUrl = str(proxies.get("https") or proxies.get("http") or "").strip()
        if proxyUrl:
            parsed = urlsplit(proxyUrl)
            if parsed.hostname and parsed.port:
                settings.update({
                    "proxy_type": _PROXY_TYPE_MAP.get(parsed.scheme.lower(), lt.proxy_type_t.none),
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

    session = lt.session(settings)
    session.set_alert_mask(int(lt.alert.category_t.all_categories))
    return session


def _extractTrackers(ti: lt.torrent_info) -> list[str]:
    seen: set[str] = set()
    return [
        url for tracker in ti.trackers()
        if (url := str(tracker.url).strip()) and url not in seen and not seen.add(url)
    ]


async def _fetchTrackers() -> list[str]:
    if not bittorrentConfig.enableWebTrackers.value:
        return []

    if bittorrentConfig.autoRefreshWebTrackers.value:
        try:
            return await refreshConfiguredWebTrackers()
        except Exception as e:
            logger.opt(exception=e).warning("刷新 Web Tracker 失败，回退到缓存 {}", repr(e))

    return getCachedWebTrackers()


@dataclass
class BTFile:
    index: int
    path: str
    size: int
    selected: bool = True
    priority: int = 4
    downloadedBytes: int = 0
    completed: bool = False

    def __post_init__(self):
        self.path = str(PurePosixPath(str(self.path).replace("\\", "/")))


@dataclass(kw_only=True)
class BTTask(Task):
    packId: str = field(default="bt")
    sourceType: str
    torrentData: str
    resumeData: str = field(default="")
    trackers: list[str] = field(default_factory=list)
    files: list[BTFile] = field(default_factory=list)
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
    stateText: str = field(default="")
    peerCount: int = field(default=0)
    seedCount: int = field(default=0)
    downloadRate: int = field(default=0)
    uploadRate: int = field(default=0)

    def __post_init__(self):
        self.files = [
            item if isinstance(item, BTFile) else BTFile(**item)
            for item in self.files
        ]
        self.fileSelectionVersion = 0
        self.title = toSafeFilename(self.title, fallback="torrent")
        super().__post_init__()
        self.fileSize = sum(file.size for file in self.files if file.selected)

    @property
    def stage(self) -> TaskStage:
        return self.stages[0]

    @property
    def magnetTorrentPath(self) -> Path | None:
        if self.sourceType != "magnet" or not self.saveMagnetTorrentFile:
            return None
        return self.path / f"{self.title}.torrent"

    @property
    def countSelected(self) -> int:
        return sum(1 for file in self.files if file.selected)

    @property
    def countAll(self) -> int:
        return len(self.files)

    @property
    def isSingleFile(self) -> bool:
        return len(self.files) == 1

    @property
    def hasUnselected(self) -> bool:
        return self.countSelected < self.countAll

    def mapPath(self, file: BTFile) -> str:
        if self.isSingleFile:
            return self.title
        return str(PurePosixPath(self.title, *PurePosixPath(file.path).parts[1:]))

    def priorities(self) -> list[int]:
        return [file.priority if file.selected else 0 for file in self.files]

    def setSelection(self, selectedIndexes: set[int]):
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
        self.fileSize = sum(file.size for file in self.files if file.selected)

    def reopen(self) -> bool:
        if self.stage.status != TaskStatus.COMPLETED:
            return False

        if not any(file.selected and not file.completed for file in self.files):
            return False

        self.isSeeding = False
        self._updateSlot()
        self.stateText = "已添加新的下载文件"
        self.stage.setStatus(TaskStatus.PAUSED)
        self.stage.receivedBytes = sum(file.downloadedBytes for file in self.files if file.selected)
        if self.fileSize > 0:
            self.stage.progress = self.stage.receivedBytes / self.fileSize * 100
        else:
            self.stage.progress = 0
        return True

    def updateProgress(self, fileBytes: list[int]):
        for file in self.files:
            if not file.selected:
                file.downloadedBytes = 0
                file.completed = False
                continue
            downloaded = int(fileBytes[file.index]) if file.index < len(fileBytes) else 0
            file.downloadedBytes = downloaded
            file.completed = file.size > 0 and downloaded >= file.size

    def applySettings(self, payload: dict[str, Any]):
        super().applySettings(payload)
        if "proxies" in payload:
            self.proxies = payload.get("proxies")

    def reset(self) -> TaskStatus:
        result = super().reset()
        self.resumeData = ""
        self.shareRatioPercent = 0
        self.seedingTimeSeconds = 0
        self.isSeeding = False
        self._updateSlot()
        self.stateText = ""
        self.peerCount = 0
        self.seedCount = 0
        self.downloadRate = 0
        self.uploadRate = 0
        for file in self.files:
            file.downloadedBytes = 0
            file.completed = False
        return result

    def _updateSlot(self):
        self.usesSlot = not self.isSeeding

    async def run(self):
        try:
            for stage in self.pendingStages():
                await BTWorker(stage).run()
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
                params = lt.read_resume_data(b64decode(self.task.resumeData.encode("ascii")))
            except Exception as e:
                logger.opt(exception=e).warning("读取 BitTorrent resume 数据失败，改用种子元数据 {}", self.task.title)
                params = None
        else:
            params = None

        if params is None:
            params = lt.add_torrent_params()
            params.ti = lt.torrent_info(b64decode(self.task.torrentData.encode("ascii")))
            flags = int(params.flags)
            if self.task.sequentialDownload:
                flags |= int(lt.torrent_flags.sequential_download)
            else:
                flags &= ~int(lt.torrent_flags.sequential_download)
            params.flags = flags | int(lt.torrent_flags.update_subscribe)

        # ⚠️ 即使从 resume 恢复也要覆盖参数，确保用户修改的设置生效（路径、文件选择、限速等）
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
        totalWanted = int(status.total_wanted)
        totalWantedDone = int(status.total_wanted_done)
        isSeeding = bool(status.is_seeding)
        sessionSeedingSeconds = int((status.seeding_duration or status.seeding_time).total_seconds() if isinstance(status.seeding_duration or status.seeding_time, timedelta) else int(status.seeding_duration or status.seeding_time))

        self.task.stateText = _STATE_TEXT_MAP.get(status.state.name, status.state.name)
        self.task.peerCount = int(status.num_peers)
        self.task.seedCount = int(status.num_seeds)
        self.task.isSeeding = isSeeding
        self.task._updateSlot()
        self.task.downloadRate = int(status.download_rate)
        self.task.uploadRate = int(status.upload_rate)

        downloaded = int(status.all_time_download or status.total_wanted_done or status.total_done)
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
            from app.services.core_service import coreService
            coreService.notifyTaskSchedulingChanged()

    def _updateFiles(self):
        if self.handle is None:
            return
        try:
            fileBytes = list(self.handle.file_progress())
        except Exception:
            return
        self.task.updateProgress(fileBytes)

    def _shouldStopSeding(self) -> bool:
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
                    self.task.resumeData = b64encode(lt.write_resume_data_buf(alert.params)).decode("ascii")
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
            torrentPath.write_bytes(b64decode(self.task.torrentData.encode("ascii")))
        except Exception as e:
            logger.opt(exception=e).warning("保存 magnet 种子文件失败 {}", self.task.title)

    async def run(self):
        if self.task.countSelected <= 0:
            self.stage.setStatus(TaskStatus.FAILED)
            raise RuntimeError("至少需要选择一个文件")

        Path(self.task.path).mkdir(parents=True, exist_ok=True)
        self._saveMagnetFile()

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
            params = self._buildArgs()
            self.handle = self.session.add_torrent(params)
            self._mapFiles()
            self._updateSettings()
            self.session.resume()
            self.handle.resume()

            while True:
                alerts = list(self.session.pop_alerts())
                self._handleAlerts(alerts)
                self._updateSettings()

                status = self.handle.status()
                self._updateStatus(status)
                self._updateFiles()

                if self._shouldStopSeding():
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



async def _loadFromFile(source: str, webTrackers: list[str]) -> tuple[bytes, lt.torrent_info, list[str]]:
    torrentPath = resolveLocalTorrentPath(source)
    if torrentPath is None:
        raise ValueError("不是有效的本地 .torrent 文件路径")
    torrentBytes = await asyncio.to_thread(lambda: torrentPath.resolve().read_bytes())
    ti = lt.torrent_info(torrentBytes)
    return torrentBytes, ti, mergeTrackers(_extractTrackers(ti), webTrackers)


async def _loadFromUrl(payload: dict, webTrackers: list[str]) -> tuple[bytes, lt.torrent_info, list[str]]:
    url = str(payload["url"]).strip()
    headers = payload.get("headers", DEFAULT_HEADERS)
    proxies = payload.get("proxies", getProxies())
    requestHeaders, requestCookies = splitRequestHeadersAndCookies(
        headers if isinstance(headers, dict) else DEFAULT_HEADERS
    )

    client = niquests.AsyncSession(timeout=30, happy_eyeballs=True)
    client.trust_env = False
    try:
        response = await client.get(
            url,
            headers=requestHeaders,
            cookies=requestCookies,
            proxies=proxies,
            verify=cfg.SSLVerify.value,
            allow_redirects=True,
        )
        try:
            response.raise_for_status()
            torrentBytes = bytes(response.content)
        finally:
            await response.close()
    finally:
        await client.close()

    ti = lt.torrent_info(torrentBytes)
    return torrentBytes, ti, mergeTrackers(_extractTrackers(ti), webTrackers)


def _loadFromMagnetBlocking(
    url: str,
    proxies: dict | None,
    webTrackers: list[str],
) -> tuple[bytes, lt.torrent_info, list[str]]:
    import time

    session = _createSession(
        listenPort=bittorrentConfig.listenPort.value,
        connectionsLimit=bittorrentConfig.connectionsLimit.value,
        downloadRateLimit=bittorrentConfig.downloadRateLimit.value,
        uploadRateLimit=bittorrentConfig.uploadRateLimit.value,
        enableDHT=bittorrentConfig.enableDHT.value,
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
    params.trackers = mergeTrackers(params.trackers.copy(), webTrackers)
    tempDir = Path(gettempdir()) / "ghost_downloader_bt_metadata"
    tempDir.mkdir(parents=True, exist_ok=True)
    params.save_path = str(tempDir)
    params.storage_mode = lt.storage_mode_t.storage_mode_sparse
    params.flags = int(params.flags) | int(lt.torrent_flags.default_dont_download)
    params.flags = int(params.flags) | int(lt.torrent_flags.update_subscribe)

    handle = session.add_torrent(params)
    session.resume()
    handle.resume()

    try:
        handle.force_reannounce(0, -1, lt.reannounce_flags_t.ignore_min_interval)
    except Exception:
        handle.force_reannounce()
    if bittorrentConfig.enableDHT.value:
        try:
            handle.force_dht_announce()
        except Exception:
            pass

    metadataTimeout = bittorrentConfig.metadataTimeout.value
    try:
        deadline = time.monotonic() + metadataTimeout
        while time.monotonic() < deadline:
            alerts = list(session.pop_alerts())
            for alert in alerts:
                if isinstance(alert, lt.metadata_received_alert):
                    ti = handle.torrent_file()
                    if ti is not None and ti.is_valid():
                        ti_bytes = lt.bencode(lt.create_torrent(ti).generate())
                        return ti_bytes, ti, params.trackers.copy()
                if isinstance(alert, lt.metadata_failed_alert):
                    raise RuntimeError(alert.message())
                if isinstance(alert, (lt.torrent_error_alert, lt.file_error_alert)):
                    raise RuntimeError(alert.message())

            status = handle.status()
            if status.has_metadata:
                ti = handle.torrent_file()
                if ti is not None and ti.is_valid():
                    ti_bytes = lt.bencode(lt.create_torrent(ti).generate())
                    return ti_bytes, ti, params.trackers.copy()

            time.sleep(0.2)

        raise TimeoutError("等待 magnet 元数据超时")
    finally:
        try:
            session.remove_torrent(handle)
        except Exception:
            pass


async def _loadFromMagnet(
    payload: dict,
    webTrackers: list[str],
) -> tuple[bytes, lt.torrent_info, list[str]]:
    url = str(payload["url"]).strip()
    proxies = payload.get("proxies", getProxies())
    return await asyncio.to_thread(_loadFromMagnetBlocking, url, proxies, webTrackers)


def _buildTask(
    ti: lt.torrent_info,
    *,
    payload: dict,
    sourceType: str,
    sourceUrl: str,
    torrentBytes: bytes,
    trackers: list[str],
) -> BTTask:
    files = ti.files()
    entries: list[BTFile] = [
        BTFile(
            index=index,
            path=files.file_path(index),
            size=int(files.file_size(index)),
        )
        for index in range(ti.num_files())
        if not bool(files.file_flags(index) & lt.file_storage.flag_pad_file)
    ]

    if not entries:
        raise ValueError("该种子中没有可下载的普通文件")

    rootName = toSafeFilename(PurePosixPath(entries[0].path).parts[0], fallback="torrent")
    title = toSafeFilename(Path(entries[0].path).name, fallback="torrent") if len(entries) == 1 else rootName

    return BTTask(
        title=title,
        url=sourceUrl,
        fileSize=sum(entry.size for entry in entries),
        path=Path(payload.get("path", cfg.downloadFolder.value)),
        stages=[TaskStage(stageIndex=1)],
        sourceType=sourceType,
        torrentData=b64encode(torrentBytes).decode("ascii"),
        trackers=trackers or _extractTrackers(ti),
        files=entries,
        proxies=payload.get("proxies", getProxies()),
    )


async def resolve(payload: dict) -> BTTask:
    url = str(payload["url"]).strip()
    webTrackers = await _fetchTrackers()

    localTorrentPath = resolveLocalTorrentPath(url)
    if localTorrentPath is not None:
        torrentBytes, ti, trackers = await _loadFromFile(url, webTrackers)
        return _buildTask(
            ti,
            payload=payload,
            sourceType="torrent",
            sourceUrl=str(localTorrentPath.resolve()),
            torrentBytes=torrentBytes,
            trackers=trackers,
        )

    parsedUrl = urlparse(url)
    if parsedUrl.scheme.lower() == "magnet":
        torrentBytes, ti, trackers = await _loadFromMagnet(payload, webTrackers)
        return _buildTask(
            ti,
            payload=payload,
            sourceType="magnet",
            sourceUrl=url,
            torrentBytes=torrentBytes,
            trackers=trackers,
        )

    torrentBytes, ti, trackers = await _loadFromUrl(payload, webTrackers)
    return _buildTask(
        ti,
        payload=payload,
        sourceType="torrent",
        sourceUrl=url,
        torrentBytes=torrentBytes,
        trackers=trackers,
    )
