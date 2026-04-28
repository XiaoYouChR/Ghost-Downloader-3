# pyright: reportAny=false, reportExplicitAny=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportAttributeAccessIssue=false, reportImplicitOverride=false, reportInconsistentConstructor=false, reportUnannotatedClassAttribute=false, reportArgumentType=false, reportPrivateLocalImportUsage=false, reportCallIssue=false, reportMissingTypeArgument=false, reportUnusedImport=false, reportUnusedFunction=false, reportUnusedCallResult=false, reportPropertyTypeMismatch=false, reportPrivateUsage=false, reportReturnType=false

from __future__ import annotations

import asyncio
from base64 import b64decode, b64encode
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from dataclasses import replace
from datetime import timedelta
from pathlib import Path, PurePosixPath
from tempfile import gettempdir
from time import time_ns
from typing import Any
from typing import cast
from urllib.parse import unquote, urlparse, urlsplit
from urllib.request import url2pathname
from uuid import uuid4

import libtorrent as lt
import niquests
from loguru import logger

from app.feature_pack.api import TaskStatus
from app.feature_pack.api import FormField
from app.feature_pack.api import MultiFileTask
from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskFile
from app.feature_pack.api import TaskForm
from app.feature_pack.api import TaskInput
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage
from app.supports.config import DEFAULT_HEADERS, VERSION, cfg
from app.supports.utils import getProxies, sanitizeFilename, splitRequestHeadersAndCookies
from .config import bittorrentConfig, getCachedWebTrackers, refreshConfiguredWebTrackers
from .trackers import mergeTrackers

BITTORRENT_USER_AGENT = f"GhostDownloader/{VERSION} libtorrent/{lt.__version__}"

_BITTORRENT_TASK_PACK_ID = "bittorrent_pack"
_BITTORRENT_TASK_KIND = "bittorrent_download"
_BITTORRENT_STAGE_KIND = "bittorrent_download"
_BITTORRENT_TASK_VERSION = 1
_BITTORRENT_STAGE_VERSION = 1
_DEFAULT_STAGE_NAME = "BitTorrent 下载"


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


def _copyHeaders(headers: Mapping[str, str] | None) -> dict[str, str]:
    if headers:
        return {str(key): str(value) for key, value in headers.items()}
    return DEFAULT_HEADERS.copy()


def _copyProxies(
    proxies: Mapping[str, str] | None,
) -> dict[str, str] | None:
    if proxies is None:
        return None
    return {str(key): str(value) for key, value in proxies.items()}


def _normalizeState(value: str | TaskStatus | object) -> str:
    if isinstance(value, TaskStatus):
        return value.name.lower()
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"completed", "failed", "paused", "running", "waiting"}:
            return normalized
    return "waiting"


def _legacyStatus(value: str | TaskStatus | object) -> TaskStatus:
    return {
        "waiting": TaskStatus.WAITING,
        "running": TaskStatus.RUNNING,
        "paused": TaskStatus.PAUSED,
        "completed": TaskStatus.COMPLETED,
        "failed": TaskStatus.FAILED,
    }[_normalizeState(value)]


def _fileIdForIndex(index: int) -> str:
    return f"file-{index}"


def _fileIndexFromId(fileId: str) -> int:
    prefix, _, suffix = fileId.partition("-")
    if prefix == "file" and suffix.isdecimal():
        return int(suffix)
    if fileId.isdecimal():
        return int(fileId)
    return 0


def _normalizeConfig(config: TaskConfig) -> TaskConfig:
    rawName = str(config.name).strip()
    return TaskConfig(
        source=str(config.source).strip(),
        folder=Path(config.folder),
        name=sanitizeFilename(rawName, fallback="torrent") if rawName else "",
        headers=_copyHeaders(config.headers),
        proxies=_copyProxies(config.proxies),
        chunks=max(1, int(config.chunks)),
    )


def _normalizeTorrentFilePath(path: object, *, fallback: str = "torrent_file") -> str:
    text = str(path or "").strip().replace("\\", "/")
    if not text:
        return fallback
    normalizedPath = PurePosixPath(text)
    return str(normalizedPath) if str(normalizedPath) != "." else fallback


async def _resolveAdditionalTrackers() -> list[str]:
    if not bittorrentConfig.enableWebTrackers.value:
        return []

    if bittorrentConfig.autoRefreshWebTrackers.value:
        try:
            return await refreshConfiguredWebTrackers()
        except Exception as e:
            logger.opt(exception=e).warning("刷新 Web Tracker 失败，回退到缓存 {}", repr(e))

    return getCachedWebTrackers()


@dataclass(slots=True, kw_only=True)
class BitTorrentFile(TaskFile):
    id: str = ""
    path: str = ""
    size: int = 0
    index: int = 0
    priority: int = 4

    def __post_init__(self) -> None:
        self.path = _normalizeTorrentFilePath(self.path)
        if not self.id:
            self.id = _fileIdForIndex(self.index)
        self.size = max(0, int(self.size))
        self.priority = 4 if self.selected else 0

    @property
    def downloadedBytes(self) -> int:
        return self.doneBytes

    @downloadedBytes.setter
    def downloadedBytes(self, value: int) -> None:
        self.doneBytes = max(0, int(value))

    @property
    def completed(self) -> bool:
        return self.finished

    @completed.setter
    def completed(self, value: bool) -> None:
        self.finished = bool(value)


def _coerceBitTorrentFile(rawFile: object, fallbackIndex: int) -> BitTorrentFile:
    if isinstance(rawFile, BitTorrentFile):
        return rawFile
    if isinstance(rawFile, TaskFile):
        index = _fileIndexFromId(rawFile.id)
        return BitTorrentFile(
            id=rawFile.id,
            path=rawFile.path,
            size=rawFile.size,
            selected=rawFile.selected,
            note=rawFile.note,
            doneBytes=rawFile.doneBytes,
            finished=rawFile.finished,
            index=index,
            priority=4 if rawFile.selected else 0,
        )
    if isinstance(rawFile, Mapping):
        rawIndex = rawFile.get("index")
        index = (
            rawIndex
            if isinstance(rawIndex, int) and not isinstance(rawIndex, bool)
            else fallbackIndex
        )
        rawId = rawFile.get("id")
        rawPath = rawFile.get("path")
        rawSize = rawFile.get("size")
        rawDoneBytes = rawFile.get("downloadedBytes", rawFile.get("doneBytes", 0))
        rawPriority = rawFile.get("priority")
        rawSelected = bool(rawFile.get("selected", True))
        note = rawFile.get("note")
        return BitTorrentFile(
            id=rawId if isinstance(rawId, str) and rawId else _fileIdForIndex(index),
            path=_normalizeTorrentFilePath(rawPath),
            size=rawSize if isinstance(rawSize, int) and not isinstance(rawSize, bool) else 0,
            selected=rawSelected,
            note=note if isinstance(note, str) else "",
            doneBytes=rawDoneBytes if isinstance(rawDoneBytes, int) and not isinstance(rawDoneBytes, bool) else 0,
            finished=bool(rawFile.get("completed", rawFile.get("finished", False))),
            index=index,
            priority=rawPriority if isinstance(rawPriority, int) and not isinstance(rawPriority, bool) else (4 if rawSelected else 0),
        )
    raise TypeError(f"Unsupported BitTorrent task file type: {type(rawFile).__name__}")


def _restoreBitTorrentFiles(state: Mapping[str, object]) -> list[BitTorrentFile]:
    rawFiles = state.get("files")
    rawMetadata = state.get("fileMetadata")
    metadataById: dict[str, Mapping[str, object]] = {}
    if isinstance(rawMetadata, list):
        for item in rawMetadata:
            if not isinstance(item, Mapping):
                continue
            fileId = item.get("id")
            if isinstance(fileId, str):
                metadataById[fileId] = item

    restoredFiles: list[BitTorrentFile] = []
    if not isinstance(rawFiles, list):
        return restoredFiles

    for fallbackIndex, rawFile in enumerate(rawFiles):
        if not isinstance(rawFile, Mapping):
            continue
        fileId = rawFile.get("id")
        if not isinstance(fileId, str) or not fileId:
            continue
        metadata = metadataById.get(fileId, {})
        rawIndex = metadata.get("index")
        rawPriority = metadata.get("priority")
        restoredFile = _coerceBitTorrentFile(rawFile, fallbackIndex)
        restoredFile.index = rawIndex if isinstance(rawIndex, int) and not isinstance(rawIndex, bool) else restoredFile.index
        if isinstance(rawPriority, int) and not isinstance(rawPriority, bool):
            restoredFile.priority = rawPriority
        elif restoredFile.selected:
            restoredFile.priority = 4
        else:
            restoredFile.priority = 0
        restoredFiles.append(restoredFile)
    return restoredFiles


class BitTorrentTaskStage(TaskStage):
    recordTaskPackId = _BITTORRENT_TASK_PACK_ID
    recordTaskKind = _BITTORRENT_TASK_KIND
    recordTaskVersion = _BITTORRENT_TASK_VERSION
    recordKind = _BITTORRENT_STAGE_KIND
    recordVersion = _BITTORRENT_STAGE_VERSION

    def __init__(
        self,
        *,
        id: str | None = None,
        stageIndex: int = 1,
        resolvePath: str = "",
        kind: str = _BITTORRENT_STAGE_KIND,
        version: int = _BITTORRENT_STAGE_VERSION,
        name: str = _DEFAULT_STAGE_NAME,
        state: str | TaskStatus = "waiting",
        progress: float = 0.0,
        doneBytes: int = 0,
        speed: int = 0,
        error: str = "",
        stateText: str = "",
        peerCount: int = 0,
        seedCount: int = 0,
        downloadRate: int = 0,
        uploadRate: int = 0,
    ) -> None:
        super().__init__(
            id=id or f"bittorrent-stage-{uuid4().hex}",
            kind=kind,
            version=version,
            name=name,
        )
        self.stageIndex = max(1, int(stageIndex))
        self.resolvePath = str(resolvePath)
        self.state = _normalizeState(state)
        self.progress = max(0.0, min(float(progress), 100.0))
        self.doneBytes = max(0, int(doneBytes))
        self.speed = max(0, int(speed))
        self.error = str(error)
        self.stateText = str(stateText)
        self.peerCount = max(0, int(peerCount))
        self.seedCount = max(0, int(seedCount))
        self.downloadRate = max(0, int(downloadRate))
        self.uploadRate = max(0, int(uploadRate))

    @property
    def receivedBytes(self) -> int:
        return self.doneBytes

    @receivedBytes.setter
    def receivedBytes(self, value: int) -> None:
        self.doneBytes = max(0, int(value))

    @property
    def status(self) -> TaskStatus:
        return _legacyStatus(self.state)

    @status.setter
    def status(self, value: TaskStatus | str) -> None:
        self.setStatus(value, emitSignals=False)

    async def pause(self) -> None:
        self.setStatus("paused")

    async def run(self) -> None:
        await BitTorrentWorker(self).run()

    def reset(self, notifyTask: bool = True) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.speed = 0
        self.error = ""
        self.stateText = ""
        self.peerCount = 0
        self.seedCount = 0
        self.downloadRate = 0
        self.uploadRate = 0
        task = self._task if isinstance(self._task, BitTorrentTask) else None
        if notifyTask and task is not None:
            task.syncStatusFromStages()
        self.stateChanged.emit(self.state)
        self.progressChanged.emit(self.progress)
        self.snapshotChanged.emit(self.snapshot())

    def setStatus(
        self,
        status: TaskStatus | str,
        *,
        emitSignals: bool = True,
        notifyTask: bool | None = None,
    ) -> None:
        normalizedStatus = _normalizeState(status)
        stateChanged = self.state != normalizedStatus
        progressChanged = False
        self.state = normalizedStatus
        if normalizedStatus == "completed":
            self.progress = 100.0
            progressChanged = True
            self.speed = 0
            self.error = ""
        elif normalizedStatus in {"paused", "waiting"}:
            self.speed = 0
            self.downloadRate = 0
            self.uploadRate = 0
            self.error = ""
        elif normalizedStatus == "failed":
            self.speed = 0

        task = self._task if isinstance(self._task, BitTorrentTask) else None
        if notifyTask is not False and task is not None:
            task.syncStatusFromStages()

        if not emitSignals:
            return
        if stateChanged:
            self.stateChanged.emit(self.state)
        if progressChanged:
            self.progressChanged.emit(self.progress)
        self.snapshotChanged.emit(self.snapshot())

    def setError(self, error: object, notifyTask: bool = True) -> None:
        message = repr(error).strip() if error is not None else ""
        self.error = message
        self.state = "failed"
        self.speed = 0
        task = self._task if isinstance(self._task, BitTorrentTask) else None
        if notifyTask and task is not None:
            task.syncStatusFromStages()
        self.stateChanged.emit(self.state)
        self.failed.emit(message)
        self.snapshotChanged.emit(self.snapshot())

    def updateTransfer(
        self,
        *,
        doneBytes: int,
        speed: int,
        progress: float,
        notifyTask: bool = True,
    ) -> None:
        self.doneBytes = max(0, int(doneBytes))
        self.speed = max(0, int(speed))
        self.progress = max(0.0, min(float(progress), 100.0))
        task = self._task if isinstance(self._task, BitTorrentTask) else None
        if notifyTask and task is not None:
            task.syncStatusFromStages()
        self.progressChanged.emit(self.progress)
        self.snapshotChanged.emit(self.snapshot())

    def snapshot(self) -> StageSnapshot:
        return StageSnapshot(
            id=self.id,
            kind=self.kind,
            name=self.name,
            state=self.state,
            progress=self.progress,
            doneBytes=self.doneBytes,
            speed=self.speed,
            error=self.error,
        )

    def persistenceState(self) -> dict[str, object]:
        return {
            "stageIndex": self.stageIndex,
            "resolvePath": self.resolvePath,
            "state": self.state,
            "progress": self.progress,
            "doneBytes": self.doneBytes,
            "speed": self.speed,
            "error": self.error,
            "stateText": self.stateText,
            "peerCount": self.peerCount,
            "seedCount": self.seedCount,
            "downloadRate": self.downloadRate,
            "uploadRate": self.uploadRate,
        }

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        rawStageIndex = state.get("stageIndex")
        rawResolvePath = state.get("resolvePath")
        rawState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawSpeed = state.get("speed")
        rawError = state.get("error")
        rawStateText = state.get("stateText")
        rawPeerCount = state.get("peerCount")
        rawSeedCount = state.get("seedCount")
        rawDownloadRate = state.get("downloadRate")
        rawUploadRate = state.get("uploadRate")

        if isinstance(rawStageIndex, int) and not isinstance(rawStageIndex, bool):
            self.stageIndex = max(1, rawStageIndex)
        if isinstance(rawResolvePath, str):
            self.resolvePath = rawResolvePath
        if isinstance(rawState, str):
            self.state = _normalizeState(rawState)
        if isinstance(rawProgress, int | float):
            self.progress = max(0.0, min(float(rawProgress), 100.0))
        if isinstance(rawDoneBytes, int) and not isinstance(rawDoneBytes, bool):
            self.doneBytes = max(0, rawDoneBytes)
        if isinstance(rawSpeed, int) and not isinstance(rawSpeed, bool):
            self.speed = max(0, rawSpeed)
        if isinstance(rawError, str):
            self.error = rawError
        if isinstance(rawStateText, str):
            self.stateText = rawStateText
        if isinstance(rawPeerCount, int) and not isinstance(rawPeerCount, bool):
            self.peerCount = max(0, rawPeerCount)
        if isinstance(rawSeedCount, int) and not isinstance(rawSeedCount, bool):
            self.seedCount = max(0, rawSeedCount)
        if isinstance(rawDownloadRate, int) and not isinstance(rawDownloadRate, bool):
            self.downloadRate = max(0, rawDownloadRate)
        if isinstance(rawUploadRate, int) and not isinstance(rawUploadRate, bool):
            self.uploadRate = max(0, rawUploadRate)

    @classmethod
    def createPersistentStage(
        cls,
        *,
        id: str,
        kind: str,
        version: int,
        name: str,
        state: Mapping[str, object],
    ) -> "BitTorrentTaskStage":
        rawStageIndex = state.get("stageIndex")
        rawResolvePath = state.get("resolvePath")
        rawTaskState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawSpeed = state.get("speed")
        rawError = state.get("error")
        rawStateText = state.get("stateText")
        rawPeerCount = state.get("peerCount")
        rawSeedCount = state.get("seedCount")
        rawDownloadRate = state.get("downloadRate")
        rawUploadRate = state.get("uploadRate")
        return cls(
            id=id,
            kind=kind,
            version=version,
            name=name,
            stageIndex=rawStageIndex if isinstance(rawStageIndex, int) else 1,
            resolvePath=rawResolvePath if isinstance(rawResolvePath, str) else "",
            state=rawTaskState if isinstance(rawTaskState, str) else "waiting",
            progress=float(rawProgress) if isinstance(rawProgress, int | float) else 0.0,
            doneBytes=rawDoneBytes if isinstance(rawDoneBytes, int) else 0,
            speed=rawSpeed if isinstance(rawSpeed, int) else 0,
            error=rawError if isinstance(rawError, str) else "",
            stateText=rawStateText if isinstance(rawStateText, str) else "",
            peerCount=rawPeerCount if isinstance(rawPeerCount, int) else 0,
            seedCount=rawSeedCount if isinstance(rawSeedCount, int) else 0,
            downloadRate=rawDownloadRate if isinstance(rawDownloadRate, int) else 0,
            uploadRate=rawUploadRate if isinstance(rawUploadRate, int) else 0,
        )


class BitTorrentTask(MultiFileTask):
    recordPackId = _BITTORRENT_TASK_PACK_ID
    recordKind = _BITTORRENT_TASK_KIND
    recordVersion = _BITTORRENT_TASK_VERSION

    def __init__(
        self,
        *,
        id: str | None = None,
        config: TaskConfig | None = None,
        stages: list[TaskStage] | None = None,
        files: list[TaskFile | Mapping[str, object]] | None = None,
        sourceType: str = "torrent",
        torrentData: str,
        resumeData: str = "",
        trackers: list[str] | None = None,
        listenPort: int | None = None,
        connectionsLimit: int | None = None,
        downloadRateLimit: int | None = None,
        uploadRateLimit: int | None = None,
        enableDHT: bool | None = None,
        enableLSD: bool | None = None,
        enableUPnP: bool | None = None,
        enableNATPMP: bool | None = None,
        sequentialDownload: bool | None = None,
        storageMode: str | None = None,
        seedRatioLimitPercent: int | None = None,
        seedTimeLimitMinutes: int | None = None,
        saveMagnetTorrentFile: bool | None = None,
        shareRatioPercent: float = 0.0,
        seedingTimeSeconds: int = 0,
        isSeeding: bool = False,
        fileSelectionVersion: int = 0,
        createdAt: int | None = None,
        title: str | None = None,
        url: str | None = None,
        fileSize: int | None = None,
        path: Path | str | None = None,
        proxies: Mapping[str, str] | None = None,
    ) -> None:
        if config is None:
            resolvedSource = str(url or "").strip()
            if not resolvedSource:
                raise ValueError("BitTorrentTask requires TaskConfig or url")
            config = TaskConfig(
                source=resolvedSource,
                folder=Path(path) if path is not None else Path(cfg.downloadFolder.value),
                name=sanitizeFilename(str(title or "").strip(), fallback="torrent"),
                headers=DEFAULT_HEADERS.copy(),
                proxies=_copyProxies(proxies) if proxies is not None else getProxies(),
                chunks=1,
            )

        normalizedConfig = _normalizeConfig(config)
        if not normalizedConfig.name:
            normalizedConfig = replace(normalizedConfig, name="torrent")
        normalizedFiles = [
            _coerceBitTorrentFile(rawFile, index)
            for index, rawFile in enumerate(files or [])
        ]
        self.sourceType = "magnet" if sourceType == "magnet" else "torrent"
        self.torrentData = str(torrentData)
        self.resumeData = str(resumeData)
        self.trackers = [str(tracker) for tracker in trackers or [] if str(tracker).strip()]
        self.listenPort = bittorrentConfig.listenPort.value if listenPort is None else int(listenPort)
        self.connectionsLimit = bittorrentConfig.connectionsLimit.value if connectionsLimit is None else int(connectionsLimit)
        self.downloadRateLimit = bittorrentConfig.downloadRateLimit.value if downloadRateLimit is None else int(downloadRateLimit)
        self.uploadRateLimit = bittorrentConfig.uploadRateLimit.value if uploadRateLimit is None else int(uploadRateLimit)
        self.enableDHT = bittorrentConfig.enableDHT.value if enableDHT is None else bool(enableDHT)
        self.enableLSD = bittorrentConfig.enableLSD.value if enableLSD is None else bool(enableLSD)
        self.enableUPnP = bittorrentConfig.enableUPnP.value if enableUPnP is None else bool(enableUPnP)
        self.enableNATPMP = bittorrentConfig.enableNATPMP.value if enableNATPMP is None else bool(enableNATPMP)
        self.sequentialDownload = bittorrentConfig.sequentialDownload.value if sequentialDownload is None else bool(sequentialDownload)
        self.storageMode = storageMode if isinstance(storageMode, str) and storageMode else bittorrentConfig.storageMode.value
        self.seedRatioLimitPercent = bittorrentConfig.seedRatioLimitPercent.value if seedRatioLimitPercent is None else int(seedRatioLimitPercent)
        self.seedTimeLimitMinutes = bittorrentConfig.seedTimeLimitMinutes.value if seedTimeLimitMinutes is None else int(seedTimeLimitMinutes)
        self.saveMagnetTorrentFile = bittorrentConfig.saveMagnetTorrentFile.value if saveMagnetTorrentFile is None else bool(saveMagnetTorrentFile)
        self.shareRatioPercent = max(0.0, float(shareRatioPercent))
        self.seedingTimeSeconds = max(0, int(seedingTimeSeconds))
        self.isSeeding = bool(isSeeding)
        self.fileSelectionVersion = max(0, int(fileSelectionVersion))
        self.createdAt = int(time_ns()) if createdAt is None else int(createdAt)
        self.url = normalizedConfig.source
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.totalBytes = max(0, int(fileSize)) if fileSize is not None else 0
        self.target = ""
        self._filesByIndex: dict[int, BitTorrentFile] = {}
        self._filesById: dict[str, BitTorrentFile] = {}

        resolvedStages = stages or [BitTorrentTaskStage(stageIndex=1, resolvePath="")]
        super().__init__(
            id=id or f"bittorrent-task-{uuid4().hex}",
            packId=_BITTORRENT_TASK_PACK_ID,
            kind=_BITTORRENT_TASK_KIND,
            version=_BITTORRENT_TASK_VERSION,
            config=normalizedConfig,
            stages=resolvedStages,
            files=normalizedFiles,
        )
        self._rebuildFileIndexes()
        self.syncOutput()
        self._recalculateSelection()
        self.syncStatusFromStages()

    @property
    def taskId(self) -> str:
        return self.id

    @property
    def title(self) -> str:
        return self.config.name

    @title.setter
    def title(self, value: str) -> None:
        self.setTitle(value)

    @property
    def path(self) -> Path:
        return self.config.folder

    @property
    def proxies(self) -> dict[str, str] | None:
        return None if self.config.proxies is None else dict(self.config.proxies)

    @property
    def status(self) -> TaskStatus:
        return _legacyStatus(self.state)

    @status.setter
    def status(self, value: TaskStatus | str) -> None:
        self.state = _normalizeState(value)

    @property
    def fileSize(self) -> int:
        return self.totalBytes

    @fileSize.setter
    def fileSize(self, value: int) -> None:
        self.totalBytes = max(0, int(value))

    @property
    def resolvePath(self) -> str:
        return self.target

    @property
    def stage(self) -> BitTorrentTaskStage:
        return cast(BitTorrentTaskStage, self.stages[0])

    @property
    def magnetTorrentPath(self) -> Path | None:
        if self.sourceType != "magnet" or not self.saveMagnetTorrentFile:
            return None
        return self.path / f"{self.title}.torrent"

    @property
    def selectedFileCount(self) -> int:
        return self.selectedCount

    @property
    def totalFileCount(self) -> int:
        return self.fileCount

    @property
    def isSingleFileTorrent(self) -> bool:
        return len(self.files) == 1

    @property
    def hasUnselectedFiles(self) -> bool:
        return self.selectedFileCount < self.totalFileCount

    @property
    def lastError(self) -> str:
        for stage in reversed(self.stages):
            if isinstance(stage, BitTorrentTaskStage) and stage.error:
                return stage.error
        return ""

    def _rebuildFileIndexes(self) -> None:
        torrentFiles: list[BitTorrentFile] = []
        for index, rawFile in enumerate(self.files):
            torrentFile = _coerceBitTorrentFile(rawFile, index)
            torrentFiles.append(torrentFile)
        self.files = torrentFiles
        self._filesByIndex = {file.index: file for file in torrentFiles}
        self._filesById = {file.id: file for file in torrentFiles}

    def syncOutput(self) -> None:
        self.target = str(self.root)
        for stage in self.stages:
            if isinstance(stage, BitTorrentTaskStage):
                stage.resolvePath = self.target

    def setTitle(self, title: str) -> None:
        self.configure(replace(self.config, name=sanitizeFilename(title, fallback=self.config.name or "torrent")))

    def mappedRelativePath(self, file: BitTorrentFile) -> str:
        if self.isSingleFileTorrent:
            return self.title.replace("\\", "/")

        parts = list(PurePosixPath(file.path).parts)
        if not parts:
            return self.title
        parts[0] = self.title
        return str(PurePosixPath(*parts))

    def filePriorities(self) -> list[int]:
        prioritiesByIndex = {
            file.index: file.priority if file.selected else 0
            for file in self.files
        }
        maxIndex = max(prioritiesByIndex, default=-1)
        return [prioritiesByIndex.get(index, 0) for index in range(maxIndex + 1)]

    def _recalculateSelection(self) -> None:
        self.totalBytes = sum(file.size for file in self.files if file.selected)

    def select(self, ids: set[str]) -> None:
        if not ids:
            raise ValueError("至少需要选择一个文件")
        knownIds = {file.id for file in self.files}
        unknownIds = ids - knownIds
        if unknownIds:
            unknownList = ", ".join(sorted(unknownIds))
            raise ValueError(f"Unknown task file ids: {unknownList}")

        changed = False
        for file in self.files:
            selected = file.id in ids
            priority = 4 if selected else 0
            if file.selected != selected or file.priority != priority:
                changed = True
            file.selected = selected
            file.priority = priority
            if not selected:
                file.doneBytes = 0
                file.finished = False

        if not changed:
            return

        self.fileSelectionVersion += 1
        self._recalculateSelection()
        self.syncStatusFromStages()
        self.snapshotChanged.emit(self.snapshot())

    def updateSelectedFiles(self, selectedIndexes: set[int]) -> None:
        self.select({_fileIdForIndex(index) for index in selectedIndexes})

    def reopenForAdditionalFiles(self) -> bool:
        if self.stage.status != TaskStatus.COMPLETED:
            return False
        if not any(file.selected and not file.finished for file in self.files):
            return False

        self.isSeeding = False
        self.stage.stateText = "已添加新的下载文件"
        self.stage.setStatus(TaskStatus.PAUSED)
        self.stage.receivedBytes = sum(file.doneBytes for file in self.files if file.selected)
        if self.fileSize > 0:
            self.stage.progress = self.stage.receivedBytes / self.fileSize * 100
        else:
            self.stage.progress = 0
        self.syncStatusFromStages()
        return True

    def updateFileProgress(self, progresses: list[int]) -> None:
        for file in self.files:
            if not file.selected:
                file.doneBytes = 0
                file.finished = False
                continue
            downloaded = int(progresses[file.index]) if file.index < len(progresses) else 0
            file.doneBytes = max(0, downloaded)
            file.finished = file.size > 0 and downloaded >= file.size
        self.syncStatusFromStages()

    def configure(self, config: TaskConfig) -> None:
        normalizedConfig = _normalizeConfig(config)
        if not normalizedConfig.name:
            normalizedConfig = replace(normalizedConfig, name=self.config.name)
        self.url = normalizedConfig.source
        super().configure(normalizedConfig)
        self.syncStatusFromStages()

    def editForm(self, _mode: str) -> TaskForm | None:
        return TaskForm(
            title="编辑 BitTorrent 下载任务",
            fields=(
                FormField(
                    key="name",
                    label="名称",
                    kind="text",
                    placeholder="输入输出名称",
                ),
                FormField(
                    key="folder",
                    label="下载目录",
                    kind="folder",
                    placeholder="选择输出目录",
                ),
                FormField(
                    key="files",
                    label="选择文件",
                    kind="files",
                ),
                FormField(
                    key="proxies",
                    label="代理",
                    kind="proxy",
                    note="使用 key: value 的格式，每行一项；留空表示不使用代理",
                ),
            ),
        )

    def syncStatusFromStages(self) -> TaskStatus:
        self._recalculateSelection()
        if not self.stages:
            self.state = "waiting"
            self.progress = 0.0
            self.doneBytes = 0
            return self.status

        stage = self.stage
        self.state = stage.state
        self.doneBytes = sum(file.doneBytes for file in self.files if file.selected)
        if self.doneBytes <= 0:
            self.doneBytes = stage.doneBytes
        if self.totalBytes > 0:
            self.progress = max(0.0, min((self.doneBytes / self.totalBytes) * 100.0, 100.0))
        else:
            self.progress = stage.progress
        if stage.state == "completed":
            self.progress = 100.0
            if self.totalBytes > 0:
                self.doneBytes = max(self.doneBytes, self.totalBytes)
        return self.status

    def setState(self, state: str) -> None:
        normalizedState = _normalizeState(state)
        self.state = normalizedState
        self.stateChanged.emit(normalizedState)
        self.snapshotChanged.emit(self.snapshot())

    def setStatus(self, status: TaskStatus | str) -> TaskStatus:
        normalizedStatus = _normalizeState(status)
        if self.stages:
            self.stage.setStatus(normalizedStatus, emitSignals=False, notifyTask=False)
        self.state = normalizedStatus
        return self.syncStatusFromStages()

    async def pause(self) -> None:
        self.setStatus("paused")

    def reset(self) -> None:
        self.resumeData = ""
        self.shareRatioPercent = 0
        self.seedingTimeSeconds = 0
        self.isSeeding = False
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.currentStageIndex = 0
        for file in self.files:
            file.doneBytes = 0
            file.finished = False
        for stage in self.stages:
            if isinstance(stage, BitTorrentTaskStage):
                stage.reset(notifyTask=False)
            else:
                stage.reset()
        self.syncStatusFromStages()

    def canPause(self) -> bool:
        return self.state == "running"

    def stagesForExecution(self) -> list[BitTorrentTaskStage]:
        return [self.stage]

    async def run(self) -> None:
        try:
            self.setState("running")
            self.stage.setStatus("running", emitSignals=False, notifyTask=False)
            await BitTorrentWorker(self.stage).run()
            self.syncStatusFromStages()
        except asyncio.CancelledError:
            logger.info("{} 停止下载", self.title)
            raise
        except Exception as error:
            if not self.stage.error:
                self.stage.setError(error)
            logger.opt(exception=error).error("{} 下载失败", self.title)
            raise

    def snapshot(self) -> TaskSnapshot:
        return TaskSnapshot(
            id=self.id,
            packId=self.packId,
            kind=self.kind,
            name=self.config.name,
            state=self.state,
            progress=self.progress,
            doneBytes=self.doneBytes,
            totalBytes=max(0, self.totalBytes),
            canPause=self.canPause(),
            target=self.target,
            stages=tuple(stage.snapshot() for stage in self.stages),
        )

    def persistenceState(self) -> dict[str, object]:
        state = super().persistenceState()
        state.update(
            {
                "sourceType": self.sourceType,
                "torrentData": self.torrentData,
                "resumeData": self.resumeData,
                "trackers": self.trackers.copy(),
                "listenPort": self.listenPort,
                "connectionsLimit": self.connectionsLimit,
                "downloadRateLimit": self.downloadRateLimit,
                "uploadRateLimit": self.uploadRateLimit,
                "enableDHT": self.enableDHT,
                "enableLSD": self.enableLSD,
                "enableUPnP": self.enableUPnP,
                "enableNATPMP": self.enableNATPMP,
                "sequentialDownload": self.sequentialDownload,
                "storageMode": self.storageMode,
                "seedRatioLimitPercent": self.seedRatioLimitPercent,
                "seedTimeLimitMinutes": self.seedTimeLimitMinutes,
                "saveMagnetTorrentFile": self.saveMagnetTorrentFile,
                "shareRatioPercent": self.shareRatioPercent,
                "seedingTimeSeconds": self.seedingTimeSeconds,
                "isSeeding": self.isSeeding,
                "fileSelectionVersion": self.fileSelectionVersion,
                "createdAt": self.createdAt,
                "url": self.url,
                "state": self.state,
                "progress": self.progress,
                "doneBytes": self.doneBytes,
                "totalBytes": self.totalBytes,
                "fileMetadata": [
                    {
                        "id": file.id,
                        "index": file.index,
                        "priority": file.priority,
                    }
                    for file in self.files
                    if isinstance(file, BitTorrentFile)
                ],
            }
        )
        return state

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        super().restorePersistentState(state)

        rawSourceType = state.get("sourceType")
        rawTorrentData = state.get("torrentData")
        rawResumeData = state.get("resumeData")
        rawTrackers = state.get("trackers")
        rawCreatedAt = state.get("createdAt")
        rawUrl = state.get("url")
        rawTaskState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawTotalBytes = state.get("totalBytes")

        if isinstance(rawSourceType, str) and rawSourceType in {"magnet", "torrent"}:
            self.sourceType = rawSourceType
        if isinstance(rawTorrentData, str):
            self.torrentData = rawTorrentData
        if isinstance(rawResumeData, str):
            self.resumeData = rawResumeData
        if isinstance(rawTrackers, list):
            self.trackers = [str(tracker) for tracker in rawTrackers if isinstance(tracker, str)]
        for attrName in (
            "listenPort",
            "connectionsLimit",
            "downloadRateLimit",
            "uploadRateLimit",
            "seedRatioLimitPercent",
            "seedTimeLimitMinutes",
            "seedingTimeSeconds",
            "fileSelectionVersion",
        ):
            value = state.get(attrName)
            if isinstance(value, int) and not isinstance(value, bool):
                setattr(self, attrName, value)
        for attrName in (
            "enableDHT",
            "enableLSD",
            "enableUPnP",
            "enableNATPMP",
            "sequentialDownload",
            "saveMagnetTorrentFile",
            "isSeeding",
        ):
            value = state.get(attrName)
            if isinstance(value, bool):
                setattr(self, attrName, value)
        rawStorageMode = state.get("storageMode")
        if isinstance(rawStorageMode, str) and rawStorageMode:
            self.storageMode = rawStorageMode
        rawShareRatio = state.get("shareRatioPercent")
        if isinstance(rawShareRatio, int | float):
            self.shareRatioPercent = max(0.0, float(rawShareRatio))
        if isinstance(rawCreatedAt, int) and not isinstance(rawCreatedAt, bool):
            self.createdAt = rawCreatedAt
        if isinstance(rawUrl, str) and rawUrl:
            self.url = rawUrl
        if isinstance(rawTaskState, str):
            self.state = _normalizeState(rawTaskState)
        if isinstance(rawProgress, int | float):
            self.progress = max(0.0, min(float(rawProgress), 100.0))
        if isinstance(rawDoneBytes, int) and not isinstance(rawDoneBytes, bool):
            self.doneBytes = max(0, rawDoneBytes)
        if isinstance(rawTotalBytes, int) and not isinstance(rawTotalBytes, bool):
            self.totalBytes = max(0, rawTotalBytes)

        restoredFiles = _restoreBitTorrentFiles(state)
        if restoredFiles:
            self.files = restoredFiles
        self._rebuildFileIndexes()
        self.syncOutput()
        self.syncStatusFromStages()

    @classmethod
    def createPersistentTask(
        cls,
        *,
        id: str,
        packId: str,
        kind: str,
        version: int,
        config: TaskConfig,
        stages: list[TaskStage],
        state: Mapping[str, object],
    ) -> "BitTorrentTask":
        _ = packId
        _ = kind
        _ = version
        rawSourceType = state.get("sourceType")
        rawTorrentData = state.get("torrentData")
        rawResumeData = state.get("resumeData")
        rawTrackers = state.get("trackers")
        rawCreatedAt = state.get("createdAt")
        rawTotalBytes = state.get("totalBytes")
        files = _restoreBitTorrentFiles(state)

        return cls(
            id=id,
            config=config,
            stages=stages,
            files=files,
            sourceType=rawSourceType if isinstance(rawSourceType, str) else "torrent",
            torrentData=rawTorrentData if isinstance(rawTorrentData, str) else "",
            resumeData=rawResumeData if isinstance(rawResumeData, str) else "",
            trackers=[str(tracker) for tracker in rawTrackers if isinstance(tracker, str)] if isinstance(rawTrackers, list) else [],
            createdAt=rawCreatedAt if isinstance(rawCreatedAt, int) else None,
            fileSize=rawTotalBytes if isinstance(rawTotalBytes, int) else None,
        )

    def __hash__(self) -> int:
        return hash(self.id)

    def occupiesDownloadSlot(self) -> bool:
        return self.state == "running" and not self.isSeeding

    def willOccupyDownloadSlotWhenStarted(self) -> bool:
        return not self.isSeeding


class BitTorrentWorker:
    def __init__(self, stage: BitTorrentTaskStage):
        self.stage = stage
        if not isinstance(stage._task, BitTorrentTask):
            raise TypeError("BitTorrentTaskStage must be attached to BitTorrentTask")
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

        self.stage.updateTransfer(
            doneBytes=totalWantedDone,
            speed=self.stage.downloadRate,
            progress=self.stage.progress,
        )

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
        self.stage.setStatus(TaskStatus.RUNNING)
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
    requestHeaders, requestCookies = splitRequestHeadersAndCookies(headers if isinstance(headers, dict) else DEFAULT_HEADERS)

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


def _resolveMagnetMetadataBlocking(
    url: str,
    *,
    proxies: dict | None,
    enableDHT: bool,
    enableLSD: bool,
    enableUPnP: bool,
    enableNATPMP: bool,
    listenPort: int,
    connectionsLimit: int,
    downloadRateLimit: int,
    uploadRateLimit: int,
    metadataTimeout: int,
    webTrackers: list[str],
) -> tuple[lt.torrent_info, list[str], bytes]:
    import time

    session = _createSession(
        listenPort=listenPort,
        connectionsLimit=connectionsLimit,
        downloadRateLimit=downloadRateLimit,
        uploadRateLimit=uploadRateLimit,
        enableDHT=enableDHT,
        enableLSD=enableLSD,
        enableUPnP=enableUPnP,
        enableNATPMP=enableNATPMP,
        proxies=proxies,
        extraSettings={
            "announce_to_all_trackers": True,
            "announce_to_all_tiers": True,
        },
    )

    params = lt.parse_magnet_uri(url)
    params.trackers = mergeTrackers(params.trackers.copy(), webTrackers)
    _metadataTempPath().mkdir(parents=True, exist_ok=True)
    params.save_path = str(_metadataTempPath())
    params.storage_mode = _storageMode("sparse")
    params.flags = int(params.flags) | int(lt.torrent_flags.default_dont_download)
    params.flags = int(params.flags) | int(lt.torrent_flags.update_subscribe)

    handle = session.add_torrent(params)
    session.resume()
    handle.resume()
    _forceMetadataPeerDiscovery(handle, enableDHT=enableDHT)

    try:
        deadline = time.monotonic() + metadataTimeout
        while time.monotonic() < deadline:
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

            time.sleep(0.2)

        raise TimeoutError("等待 magnet 元数据超时")
    finally:
        try:
            session.remove_torrent(handle)
        except Exception:
            pass


async def _resolveMagnetMetadata(payload: dict) -> tuple[lt.torrent_info, list[str], bytes]:
    url = str(payload["url"]).strip()
    proxies = payload.get("proxies", getProxies())
    enableDHT = bittorrentConfig.enableDHT.value
    webTrackers = await _resolveAdditionalTrackers()
    return await asyncio.to_thread(
        _resolveMagnetMetadataBlocking,
        url,
        proxies=proxies,
        enableDHT=enableDHT,
        enableLSD=bittorrentConfig.enableLSD.value,
        enableUPnP=bittorrentConfig.enableUPnP.value,
        enableNATPMP=bittorrentConfig.enableNATPMP.value,
        listenPort=bittorrentConfig.listenPort.value,
        connectionsLimit=bittorrentConfig.connectionsLimit.value,
        downloadRateLimit=bittorrentConfig.downloadRateLimit.value,
        uploadRateLimit=bittorrentConfig.uploadRateLimit.value,
        metadataTimeout=bittorrentConfig.metadataTimeout.value,
        webTrackers=webTrackers,
    )


def buildTaskFromTorrentInfo(
    ti: lt.torrent_info,
    *,
    config: TaskConfig,
    sourceType: str,
    sourceUrl: str,
    torrentBytes: bytes,
    trackers: list[str],
) -> BitTorrentTask:
    normalizedConfig = _normalizeConfig(config)
    files = ti.files()
    entries: list[BitTorrentFile] = []
    for index in range(ti.num_files()):
        if _isPadFile(files, index):
            continue
        entries.append(
            BitTorrentFile(
                id=_fileIdForIndex(index),
                index=index,
                path=files.file_path(index),
                size=int(files.file_size(index)),
            )
        )

    if not entries:
        raise ValueError("该种子中没有可下载的普通文件")

    rootName = sanitizeFilename(PurePosixPath(entries[0].path).parts[0], fallback="torrent")
    defaultTitle = sanitizeFilename(PurePosixPath(entries[0].path).name, fallback="torrent") if len(entries) == 1 else rootName
    resolvedConfig = replace(
        normalizedConfig,
        source=sourceUrl,
        name=normalizedConfig.name or defaultTitle,
    )
    return BitTorrentTask(
        config=resolvedConfig,
        fileSize=sum(entry.size for entry in entries),
        stages=[BitTorrentTaskStage(stageIndex=1, resolvePath="")],
        sourceType=sourceType,
        torrentData=_encodeBytes(torrentBytes),
        trackers=trackers or _extractTrackers(ti),
        files=entries,
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


async def buildBitTorrentTask(data: TaskInput) -> BitTorrentTask:
    config = _normalizeConfig(data.config)
    url = config.source
    localTorrentPath = resolveLocalTorrentPath(url)
    if localTorrentPath is not None:
        torrentBytes, webTrackers = await asyncio.gather(
            asyncio.to_thread(_readLocalTorrentBytes, url),
            _resolveAdditionalTrackers(),
        )
        ti = lt.torrent_info(torrentBytes)
        return buildTaskFromTorrentInfo(
            ti,
            config=config,
            sourceType="torrent",
            sourceUrl=str(localTorrentPath.resolve()),
            torrentBytes=torrentBytes,
            trackers=mergeTrackers(_extractTrackers(ti), webTrackers),
        )

    parsedUrl = urlparse(url)

    if parsedUrl.scheme.lower() == "magnet":
        ti, trackers, torrentBytes = await _resolveMagnetMetadata(
            {
                "url": config.source,
                "proxies": config.proxies,
            }
        )
        return buildTaskFromTorrentInfo(
            ti,
            config=config,
            sourceType="magnet",
            sourceUrl=url,
            torrentBytes=torrentBytes,
            trackers=trackers,
        )

    torrentBytes, webTrackers = await asyncio.gather(
        _fetchTorrentBytes(
            {
                "url": config.source,
                "headers": config.headers,
                "proxies": config.proxies,
            }
        ),
        _resolveAdditionalTrackers(),
    )
    ti = lt.torrent_info(torrentBytes)
    return buildTaskFromTorrentInfo(
        ti,
        config=config,
        sourceType="torrent",
        sourceUrl=url,
        torrentBytes=torrentBytes,
        trackers=mergeTrackers(_extractTrackers(ti), webTrackers),
    )


__all__ = [
    "BITTORRENT_USER_AGENT",
    "BitTorrentFile",
    "BitTorrentTask",
    "BitTorrentTaskStage",
    "BitTorrentWorker",
    "buildBitTorrentTask",
    "buildTaskFromTorrentInfo",
    "resolveLocalTorrentPath",
]
