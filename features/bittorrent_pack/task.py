from __future__ import annotations

import asyncio
from base64 import b64decode, b64encode
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import libtorrent as lt
from loguru import logger

from app.models.task import Task, TaskStep, TaskFile, TaskStatus
from app.platform.filesystem import deletePath, toPosixPath
from app.services.speed_meter import speedMeter
from .config import bittorrentConfig

STATE_TEXT = {
    "checking_files": "校验已有文件",
    "checking_resume_data": "检查续传状态",
    "downloading_metadata": "获取元数据",
    "downloading": "下载中",
    "finished": "下载完成",
    "seeding": "做种中",
    "allocating": "分配文件中",
    "queued_for_checking": "等待校验",
}

ERROR_ALERTS = (
    lt.file_error_alert,
    lt.metadata_failed_alert,
    lt.torrent_error_alert,
    lt.hash_failed_alert,
)


@dataclass(kw_only=True)
class BTFile(TaskFile):
    priority: int = 4

    def __post_init__(self):
        self.relativePath = toPosixPath(self.relativePath)


@dataclass(kw_only=True, eq=False)
class BTTask(Task):
    packId: str = "bt"
    canEdit = True
    fileType = BTFile
    sourceType: str = "torrent"
    torrentData: str = ""
    resumeData: str = ""
    trackers: list[str] = field(default_factory=list)
    shouldSeed: bool = True
    shareRatioPercent: float = 0
    seedingTimeSeconds: int = 0
    isSeeding: bool = False
    stateText: str = ""
    peerCount: int = 0
    seedCount: int = 0
    downloadRate: int = 0
    uploadRate: int = 0

    def __post_init__(self):
        if self.files:
            self.files = [
                item if isinstance(item, BTFile) else BTFile(**item)
                for item in self.files
            ]
        self._fileSelectionVersion = 0
        super().__post_init__()
        self.fileSize = sum(f.size for f in self.files if f.selected)

    @property
    def step(self) -> TaskStep:
        return self.steps[0]

    @property
    def magnetTorrentPath(self) -> Path | None:
        if self.sourceType != "magnet":
            return None
        return self.outputFolder / f"{self.name}.torrent"

    @property
    def countSelected(self) -> int:
        return sum(1 for f in self.files if f.selected)

    @property
    def isSingleFile(self) -> bool:
        return len(self.files) == 1

    def toRelativePath(self, file: BTFile) -> str:
        if self.isSingleFile:
            return self.name
        return toPosixPath(Path(self.name, *PurePosixPath(file.relativePath).parts[1:]))

    def priorities(self) -> list[int]:
        return [f.priority if f.selected else 0 for f in self.files]

    def setSelection(self, selectedIndexes: set[int]):
        if not selectedIndexes:
            raise ValueError("至少需要选择一个文件")
        changed = False
        for f in self.files:
            selected = f.index in selectedIndexes
            priority = 4 if selected else 0
            if f.selected != selected or f.priority != priority:
                changed = True
            f.selected = selected
            f.priority = priority
            if not selected:
                f.downloadedBytes = 0
                f.completed = False
        if not changed:
            return
        self._fileSelectionVersion += 1
        self.fileSize = sum(f.size for f in self.files if f.selected)

    def deleteFiles(self):
        super().deleteFiles()
        if self.magnetTorrentPath is not None:
            deletePath(self.magnetTorrentPath)

    def reset(self) -> TaskStatus:
        result = super().reset()
        self.resumeData = ""
        self.shouldSeed = True
        self.shareRatioPercent = 0
        self.seedingTimeSeconds = 0
        self.isSeeding = False
        self.stateText = ""
        self.peerCount = 0
        self.seedCount = 0
        self.downloadRate = 0
        self.uploadRate = 0
        for f in self.files:
            f.downloadedBytes = 0
            f.completed = False
        return result

    def _addTorrent(self, session: lt.session) -> lt.torrent_handle:
        params = None
        if self.resumeData:
            try:
                params = lt.read_resume_data(b64decode(self.resumeData))
            except Exception as e:
                logger.opt(exception=e).warning("读取 BitTorrent resume 数据失败 {}", self.name)

        if params is None:
            params = lt.add_torrent_params()
            params.ti = lt.torrent_info(b64decode(self.torrentData))
            params.flags |= lt.torrent_flags.update_subscribe

        params.save_path = str(self.outputFolder)
        params.storage_mode = (
            lt.storage_mode_t.storage_mode_allocate
            if bittorrentConfig.storageMode.value == "allocate"
            else lt.storage_mode_t.storage_mode_sparse
        )
        params.file_priorities = self.priorities()
        if bittorrentConfig.enableSequentialDownload.value:
            params.flags |= lt.torrent_flags.sequential_download
        else:
            params.flags &= ~lt.torrent_flags.sequential_download
        if self.trackers:
            params.trackers = self.trackers.copy()

        hashes = params.ti.info_hashes() if params.ti is not None else params.info_hashes
        for existing in session.get_torrents():
            eh = existing.info_hashes()
            if (hashes.has_v1() and eh.has_v1() and hashes.v1 == eh.v1) or \
               (hashes.has_v2() and eh.has_v2() and hashes.v2 == eh.v2):
                raise RuntimeError("该种子已在下载中")

        handle = session.add_torrent(params)

        for f in self.files:
            mapped = self.toRelativePath(f)
            if mapped != f.relativePath:
                handle.rename_file(f.index, mapped)

        return handle

    async def run(self):
        from .session import btSession

        try:
            if self.countSelected <= 0:
                raise RuntimeError("至少需要选择一个文件")

            target = Path(self.outputPath)
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch() if self.isSingleFile else target.mkdir()

            if self.sourceType == "magnet" and bittorrentConfig.saveMagnetFile.value:
                try:
                    self.magnetTorrentPath.write_bytes(b64decode(self.torrentData))
                except Exception as e:
                    logger.opt(exception=e).warning("保存 magnet 种子文件失败 {}", self.name)

            btSession.open()

            session = btSession.session()
            handle = self._addTorrent(session)
        except Exception as e:
            self.step.setError(e)
            raise

        handle.resume()
        handle.force_reannounce(0, -1, lt.reannounce_flags_t.ignore_min_interval)
        if bittorrentConfig.enableDht.value:
            handle.force_dht_announce()

        self._handle = handle
        self._downloadDone = asyncio.get_running_loop().create_future()
        self._resumeWaiter: asyncio.Future | None = None
        self._appliedSelectionVersion = -1
        completed = False

        btSession.alertReceived.connect(self._onAlert)
        supervisor = asyncio.create_task(self._supervise())

        try:
            await self._downloadDone
            completed = True
            self.step.setStatus(TaskStatus.COMPLETED)
            self.step.progress = 100
            self.step.speed = 0
            self.downloadRate = 0
            btSession.registerSeeding(self, handle)
        except asyncio.CancelledError:
            self.stateText = "已暂停下载"
            self.isSeeding = False
            self.step.setStatus(TaskStatus.PAUSED)
            raise
        except Exception as e:
            self.step.setError(e)
            raise
        finally:
            btSession.alertReceived.disconnect(self._onAlert)
            supervisor.cancel()
            with suppress(asyncio.CancelledError):
                await supervisor
            if not completed:
                await asyncio.shield(self._removeTorrent(session, handle))

    async def _removeTorrent(self, session, handle):
        await self._saveResume()
        try:
            session.remove_torrent(handle)
        except Exception:
            pass

    async def _supervise(self):
        while True:
            try:
                status = self._handle.status()

                self.stateText = STATE_TEXT.get(status.state.name, status.state.name)
                self.peerCount = status.num_peers
                self.seedCount = status.num_seeds
                self.isSeeding = status.is_seeding
                self.downloadRate = status.download_rate
                self.uploadRate = status.upload_rate
                speedMeter.addSpeed(status.download_rate)

                downloaded = status.all_time_download or status.total_wanted_done or status.total_done
                self.shareRatioPercent = (status.all_time_upload / downloaded * 100) if downloaded > 0 else 0.0

                self.step.speed = status.download_rate
                self.step.receivedBytes = status.total_wanted_done
                if status.total_wanted > 0:
                    self.fileSize = status.total_wanted
                    self.step.progress = status.total_wanted_done / status.total_wanted * 100
                elif self.fileSize > 0:
                    self.step.progress = self.step.receivedBytes / self.fileSize * 100
                else:
                    self.step.progress = 0

                fileBytes = self._handle.file_progress()
                for f in self.files:
                    if not f.selected:
                        f.downloadedBytes = 0
                        f.completed = False
                        continue
                    dl = fileBytes[f.index] if f.index < len(fileBytes) else 0
                    f.downloadedBytes = dl
                    f.completed = f.size > 0 and dl >= f.size

                if self._appliedSelectionVersion != self._fileSelectionVersion:
                    self._handle.prioritize_files(self.priorities())
                    self._appliedSelectionVersion = self._fileSelectionVersion

                if status.is_seeding and not self._downloadDone.done():
                    self._downloadDone.set_result(None)

            except Exception as e:
                logger.opt(exception=e).error("BitTorrent 监控异常")
            await asyncio.sleep(1)

    def _onAlert(self, alert):
        if not hasattr(alert, "handle") or alert.handle != self._handle:
            return

        if isinstance(alert, lt.save_resume_data_alert):
            data = b64encode(lt.write_resume_data_buf(alert.params)).decode()
            self.resumeData = data
            if self._resumeWaiter is not None and not self._resumeWaiter.done():
                self._resumeWaiter.set_result(True)
            return

        if isinstance(alert, lt.save_resume_data_failed_alert):
            self.resumeData = ""
            if self._resumeWaiter is not None and not self._resumeWaiter.done():
                self._resumeWaiter.set_result(False)
            return

        if isinstance(alert, lt.file_completed_alert):
            for f in self.files:
                if f.index == alert.index:
                    f.completed = True
                    f.downloadedBytes = f.size
                    break
            return

        if isinstance(alert, lt.fastresume_rejected_alert):
            self.resumeData = ""
            return

        if isinstance(alert, ERROR_ALERTS):
            if not self._downloadDone.done():
                self._downloadDone.set_exception(RuntimeError(alert.message()))

    async def _saveResume(self):
        try:
            self._handle.save_resume_data(
                lt.save_resume_flags_t.flush_disk_cache | lt.save_resume_flags_t.save_info_dict
            )
        except Exception as e:
            logger.opt(exception=e).warning("保存 BitTorrent resume 数据失败 {}", self.name)
            self.resumeData = ""
            return

        self._resumeWaiter = asyncio.get_running_loop().create_future()
        try:
            await asyncio.wait_for(self._resumeWaiter, timeout=10)
        except asyncio.TimeoutError:
            logger.warning("等待 BitTorrent resume 数据超时 {}", self.name)
            self.resumeData = ""
        finally:
            self._resumeWaiter = None
