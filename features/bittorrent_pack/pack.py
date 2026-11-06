from __future__ import annotations

import asyncio
import re
from base64 import b64encode
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import libtorrent as lt

from app.client import buildClient, toEmulation
from app.config.cfg import cfg
from app.i18n import N

from app.models.pack import FeaturePack, TaskParser, FileType, UriScheme
from app.models.task import Task, TaskOptions
from app.platform.filesystem import localFilePath, toSafeFilename

from .config import bittorrentConfig
from .session import PROXY_SCHEMES, btSession
from .task import BTFile, BTTask, BTTaskStep, BTTorrentFileStep
from .trackers import mergedTrackers, trackerList

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
    from app.view.cards.draft_cards import DraftCard
    from app.view.cards.task_cards import TaskCard
    from app.view.components.option_cards import OptionCard
    from app.view.dialogs.task_drawer import DetailCard

INFO_HASH_PATTERN = re.compile(r"[0-9a-f]{40}|[a-z2-7]{32}", re.IGNORECASE)


def toMagnetUrl(url: str) -> str:
    return f"magnet:?xt=urn:btih:{url}" if INFO_HASH_PATTERN.fullmatch(url) else url


def refreshTrackerListIfStale() -> None:
    if bittorrentConfig.autoRefreshWebTrackers.value and trackerList.isStale():
        asyncio.ensure_future(trackerList.refresh())


class TorrentParser(TaskParser):
    priority = 85

    def match(self, options: TaskOptions) -> bool:
        if options.isProbed:
            return options.file.matchType({".torrent"}, {"application/x-bittorrent"})
        url = toMagnetUrl(options.url.strip())
        if urlparse(url).scheme.lower() == "magnet":
            return True
        return localFilePath(url, {".torrent"}) is not None

    async def parse(self, options: TaskOptions) -> Task:
        url = toMagnetUrl(options.url.strip())
        outputFolder = options.outputFolder

        refreshTrackerListIfStale()
        webTrackers = mergedTrackers() if bittorrentConfig.enableWebTrackers.value else []

        localPath = localFilePath(url, {".torrent"})
        if options.isProbed:
            emulation = toEmulation(options.clientProfile or cfg.clientProfile.value, options.sourceUserAgent)
            client = buildClient(emulation=emulation, userAgent=options.userAgent or None, timeout=30)
            try:
                response = await client.get(url, headers={**options.headers, "accept-encoding": "identity"})
                try:
                    response.raise_for_status()
                    torrentBytes = bytes(await response.bytes())
                finally:
                    response.close()
            finally:
                client.close()
            sourceType, sourceUrl = "torrent", url

        elif localPath is not None:
            torrentBytes = await asyncio.to_thread(localPath.resolve().read_bytes)
            sourceType, sourceUrl = "torrent", str(localPath.resolve())

        elif urlparse(url).scheme.lower() == "magnet":
            torrentBytes = await btSession.fetchMetadata(url, webTrackers)
            sourceType, sourceUrl = "magnet", url

        else:
            raise ValueError("无法解析 BitTorrent 来源")

        if not torrentBytes:
            raise ValueError("种子文件为空")

        try:
            params = lt.load_torrent_buffer(torrentBytes)
        except Exception as e:
            raise ValueError(f"无效的 BitTorrent 种子文件：{e}") from e

        trackers = list(dict.fromkeys(
            t.strip() for g in (params.trackers, webTrackers) for t in g if t.strip()
        ))

        layout = params.ti.layout()
        entries: list[BTFile] = [
            BTFile(
                index=i,
                relativePath=layout.file_path(i),
                size=layout.file_size(i),
            )
            for i in range(layout.num_files())
            if not (layout.file_flags(i) & lt.file_storage.flag_pad_file)
        ]

        if not entries:
            raise ValueError("该种子中没有可下载的普通文件")

        rootName = toSafeFilename(PurePosixPath(entries[0].relativePath).parts[0], fallback="torrent")
        name = toSafeFilename(Path(entries[0].relativePath).name, fallback="torrent") if len(entries) == 1 else rootName

        steps = [BTTaskStep(stepIndex=1)]
        if (sourceType == "magnet" or options.isProbed) and bittorrentConfig.saveMagnetFile.value:
            steps.append(BTTorrentFileStep(stepIndex=0))
        task = BTTask(
            name=name,
            url=sourceUrl,
            fileSize=sum(e.size for e in entries),
            outputFolder=outputFolder,
            steps=steps,
            sourceType=sourceType,
            torrentData=b64encode(torrentBytes).decode(),
            trackers=trackers,
            files=entries,
        )
        return task


class BitTorrentPack(FeaturePack):
    packId = "bt"
    capturedLinks = N("BitTorrentPack", "磁力链接")
    config = bittorrentConfig
    proxySchemes = PROXY_SCHEMES
    parsers = [TorrentParser]

    def taskCardClass(self, task: Task) -> type[TaskCard] | None:
        from .cards import BTTaskCard
        return BTTaskCard

    def draftCardClass(self, task: Task) -> type[DraftCard] | None:
        from .cards import BTDraftCard
        return BTDraftCard

    def optionCards(self, task: Task, parent: QWidget | None = None) -> list[OptionCard]:
        from app.view.components.option_cards import OutputFolderCard
        return [OutputFolderCard(parent, initial=task.outputFolder)]

    def detailCards(self, task: BTTask, parent: QWidget | None = None) -> list[DetailCard]:
        from .detail_cards import PeerCard, TorrentCard, TrackerCard
        runner = self._services.coroutineRunner
        return [TorrentCard(task, runner, parent), TrackerCard(task, runner, parent), PeerCard(task, runner, parent)]

    def fileTypes(self) -> list[FileType]:
        return [
            FileType(
                extensions=(".torrent",),
                displayName=N("BitTorrentPack", "BitTorrent 种子文件"),
                mimeType="application/x-bittorrent",
                icon="torrent",
            ),
        ]

    def uriSchemes(self) -> list[UriScheme]:
        return [UriScheme("magnet", "Magnet")]

    async def activate(self) -> None:
        btSession.open()
        refreshTrackerListIfStale()

    async def deactivate(self) -> None:
        await btSession.close()
