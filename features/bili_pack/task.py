from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

from app.models.task import Task
from app.platform.filesystem import toSafeFilename
from http_pack.task import HttpTaskStep
from ffmpeg_pack.task import FFmpegStep


class DownloadMode(IntEnum):
    VIDEO = 0
    AUDIO = 1
    COVER = 2


@dataclass(kw_only=True, eq=False)
class BilibiliTask(Task):
    packId: str = "bili"
    canEdit = True
    coverUrl: str = ""
    coverSize: int = 0
    mode: DownloadMode = DownloadMode.VIDEO
    pages: list[dict] = field(default_factory=list)
    _baseName: str = ""

    def setMode(self, mode: DownloadMode) -> None:
        self.mode = mode
        self._rebuildSteps()

    def setPageSelection(self, selectedPageNumbers: set[int]) -> None:
        for page in self.pages:
            page["selected"] = page["pageNumber"] in selectedPageNumbers
        self._rebuildSteps()

    @property
    def selectedPages(self) -> list[dict]:
        return [p for p in self.pages if p.get("selected", True)]

    def deduplicateFilename(self) -> None:
        if len(self.selectedPages) <= 1:
            super().deduplicateFilename()
            return

        folder = self.outputFolder

        def anyOutputExists() -> bool:
            for step in self.steps:
                outputFile = getattr(step, "outputFile", "")
                if not outputFile:
                    continue
                path = Path(outputFile)
                if path.exists() or Path(f"{outputFile}.ghd").exists():
                    return True
            return False

        if not anyOutputExists():
            return

        stem = self._baseName
        suffixes = "".join(Path(self.name).suffixes)
        index = 1
        while True:
            self._baseName = f"{stem}({index})"
            self.name = toSafeFilename(f"{self._baseName}{suffixes}", fallback=self.name)
            self._rebuildSteps()
            if not anyOutputExists():
                break
            index += 1

    def _rebuildSteps(self) -> None:
        self.steps.clear()
        selected = self.selectedPages

        if self.mode == DownloadMode.COVER:
            self.name = toSafeFilename(f"{self._baseName}.jpg", fallback="cover.jpg")
            self.fileSize = self.coverSize
            self.addStep(HttpTaskStep(
                stepIndex=1,
                url=self.coverUrl,
                fileSize=self.coverSize,
                headers={},
                canUseRangeRequests=self.coverSize > 0,
                subworkerCount=1,
            ))
            return

        if self.mode == DownloadMode.AUDIO:
            suffix = ".m4a" if len(selected) <= 1 else ".m4a"
            self.name = toSafeFilename(f"{self._baseName}{suffix}", fallback=f"audio{suffix}")
            self.fileSize = sum(p["audioSize"] for p in selected)
            for i, info in enumerate(selected):
                pageSuffix = self._pageSuffix(info)
                self.addStep(BilibiliAudioStep(
                    stepIndex=i + 1,
                    url=info["audioUrl"],
                    fileSize=info["audioSize"],
                    headers=dict(info.get("headers") or {}),
                    subworkerCount=info.get("subworkerCount", 8),
                    canUseRangeRequests=True,
                    pageIndex=i,
                    pageSuffix=pageSuffix,
                ))
            return

        # VIDEO mode
        self.name = toSafeFilename(f"{self._baseName}.mp4", fallback="video.mp4")
        self.fileSize = sum(p["videoSize"] + p["audioSize"] for p in selected)
        for i, info in enumerate(selected):
            pageSuffix = self._pageSuffix(info)
            stepBase = i * 3
            self.addStep(BilibiliVideoStep(
                stepIndex=stepBase + 1,
                url=info["videoUrl"],
                fileSize=info["videoSize"],
                headers=dict(info.get("headers") or {}),
                subworkerCount=info.get("subworkerCount", 8),
                canUseRangeRequests=True,
                pageIndex=i,
                pageSuffix=pageSuffix,
            ))
            self.addStep(BilibiliAudioStep(
                stepIndex=stepBase + 2,
                url=info["audioUrl"],
                fileSize=info["audioSize"],
                headers=dict(info.get("headers") or {}),
                subworkerCount=info.get("subworkerCount", 8),
                canUseRangeRequests=True,
                pageIndex=i,
                pageSuffix=pageSuffix,
            ))
            self.addStep(BilibiliMergeStep(
                stepIndex=stepBase + 3,
                pageIndex=i,
                pageSuffix=pageSuffix,
            ))

    def _pageSuffix(self, pageInfo: dict) -> str:
        selected = self.selectedPages
        if len(selected) <= 1:
            return ""
        suffix = f" - P{pageInfo['pageNumber']}"
        part = pageInfo.get("pagePart", "").strip()
        if part and part != self._baseName:
            suffix += f" {part}"
        return suffix


def pageStem(taskName: str, pageSuffix: str) -> str:
    for ext in (".mp4", ".m4a", ".jpg"):
        if taskName.lower().endswith(ext):
            taskName = taskName[:-len(ext)]
            break
    return f"{taskName}{pageSuffix}" if pageSuffix else taskName


@dataclass(kw_only=True)
class BilibiliVideoStep(HttpTaskStep):
    pageIndex: int = 0
    pageSuffix: str = ""

    @property
    def outputPath(self) -> str:
        return str(self.task.outputFolder / f"{pageStem(self.task.name, self.pageSuffix)}.video.m4s")


@dataclass(kw_only=True)
class BilibiliAudioStep(HttpTaskStep):
    pageIndex: int = 0
    pageSuffix: str = ""

    @property
    def outputPath(self) -> str:
        stem = pageStem(self.task.name, self.pageSuffix)
        ext = ".m4a" if self.task.mode == DownloadMode.AUDIO else ".audio.m4s"
        return str(self.task.outputFolder / f"{stem}{ext}")


@dataclass(kw_only=True)
class BilibiliMergeStep(FFmpegStep):
    pageIndex: int = 0
    pageSuffix: str = ""

    @property
    def outputFile(self) -> str:
        return str(self.task.outputFolder / f"{pageStem(self.task.name, self.pageSuffix)}.mp4")

    @property
    def _videoPath(self) -> Path:
        return self.task.outputFolder / f"{pageStem(self.task.name, self.pageSuffix)}.video.m4s"

    @property
    def _audioPath(self) -> Path:
        return self.task.outputFolder / f"{pageStem(self.task.name, self.pageSuffix)}.audio.m4s"
