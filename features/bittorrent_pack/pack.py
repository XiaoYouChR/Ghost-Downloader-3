from __future__ import annotations

import asyncio
from base64 import b64encode
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import libtorrent as lt
from loguru import logger

from app.models.pack import FeaturePack, TaskParser, FileType
from app.models.task import Task, TaskOptions
from app.platform.filesystem import localFilePath, toSafeFilename

from .config import bittorrentConfig
from .session import btSession
from .task import BTFile, BTTask, BTTaskStep
from .web_tracker.service import trackerService


class TorrentParser(TaskParser):
    priority = 85

    def match(self, options: TaskOptions) -> bool:
        url = options.url.strip()
        if urlparse(url).scheme.lower() == "magnet":
            return True
        return localFilePath(url, {".torrent"}) is not None

    async def parse(self, options: TaskOptions) -> Task:
        url = options.url.strip()
        outputFolder = options.outputFolder

        if bittorrentConfig.enableWebTrackers.value:
            if bittorrentConfig.autoRefreshWebTrackers.value:
                try:
                    await trackerService.refresh()
                except Exception as e:
                    logger.opt(exception=e).warning("刷新 Web Tracker 失败,使用缓存")
            webTrackers = trackerService.mergedTrackers()
        else:
            webTrackers = []

        localPath = localFilePath(url, {".torrent"})
        if localPath is not None:
            torrentBytes = await asyncio.to_thread(localPath.resolve().read_bytes)
            sourceType, sourceUrl = "torrent", str(localPath.resolve())

        elif urlparse(url).scheme.lower() == "magnet":
            from .metadata import fetchTorrentBytes
            magnetTrackers = list(lt.parse_magnet_uri(url).trackers)
            torrentBytes = await fetchTorrentBytes(url, webTrackers)
            sourceType, sourceUrl = "magnet", url

        else:
            raise ValueError("无法解析 BitTorrent 来源")

        if not torrentBytes:
            raise ValueError("种子文件为空")

        try:
            ti = lt.torrent_info(torrentBytes)
        except Exception as e:
            raise ValueError(f"无效的 BitTorrent 种子文件：{e}") from e

        torrentTrackers = [str(t.url).strip() for t in ti.trackers()]
        allSources = (magnetTrackers, torrentTrackers, webTrackers) if sourceType == "magnet" else (torrentTrackers, webTrackers)
        trackers = list(dict.fromkeys(t for g in allSources for t in g if t))

        fileStorage = ti.files()
        entries: list[BTFile] = [
            BTFile(
                index=i,
                relativePath=fileStorage.file_path(i),
                size=fileStorage.file_size(i),
            )
            for i in range(ti.num_files())
            if not (fileStorage.file_flags(i) & lt.file_storage.flag_pad_file)
        ]

        if not entries:
            raise ValueError("该种子中没有可下载的普通文件")

        rootName = toSafeFilename(PurePosixPath(entries[0].relativePath).parts[0], fallback="torrent")
        name = toSafeFilename(Path(entries[0].relativePath).name, fallback="torrent") if len(entries) == 1 else rootName

        task = BTTask(
            name=name,
            url=sourceUrl,
            fileSize=sum(e.size for e in entries),
            outputFolder=outputFolder,
            steps=[BTTaskStep(stepIndex=1)],
            sourceType=sourceType,
            torrentData=b64encode(torrentBytes).decode(),
            trackers=trackers,
            files=entries,
        )
        return task


class BitTorrentPack(FeaturePack):
    packId = "bt"
    config = bittorrentConfig
    proxySchemes = {"socks5"}

    def parsers(self):
        return [TorrentParser()]

    def taskCard(self, task, parent=None):
        from .cards import BTTaskCard
        return BTTaskCard(task, self._services.taskService, self._services.featureService, self._services.categoryService, parent)

    def draftCard(self, task, parent=None):
        from .cards import BTDraftCard
        return BTDraftCard(task, self._services.categoryService, parent)

    def optionCards(self, task, parent=None):
        from app.view.components.option_cards import OutputFolderCard
        return [OutputFolderCard(parent, initial=task.outputFolder)]

    def fileTypes(self):
        return [
            FileType(
                extensions=(".torrent",),
                displayName=self.tr("BitTorrent 种子文件"),
                mimeType="application/x-bittorrent",
                icon="torrent",
            ),
        ]

    async def deactivate(self):
        await btSession.close()
