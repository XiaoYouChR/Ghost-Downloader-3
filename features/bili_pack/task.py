from __future__ import annotations

from typing import TYPE_CHECKING

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

from loguru import logger

from app.models.task import Task, TaskFile, TaskStep, TaskStatus
from app.platform.filesystem import toSafeFilename
from http_pack.task import HttpTaskStep
from ffmpeg_pack.task import FFmpegStep

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

STEPS_PER_PAGE = 4


class DownloadMode(IntEnum):
    VIDEO = 0
    AUDIO = 1
    COVER = 2


@dataclass(kw_only=True)
class BiliPage(TaskFile):
    pagePart: str = ""
    videoUrl: str = ""
    audioUrl: str = ""
    videoSize: int = 0
    audioSize: int = 0
    headers: dict = field(default_factory=dict)
    subworkerCount: int = 8
    subtitles: list[dict] = field(default_factory=list)

    @property
    def pageNumber(self) -> int:
        return self.index + 1


@dataclass(kw_only=True, eq=False)
class BilibiliTask(Task):
    packId: str = "bili"
    canEdit = True
    fileType = BiliPage
    coverUrl: str = ""
    coverSize: int = 0
    mode: DownloadMode = DownloadMode.VIDEO
    subtitleLanguages: list[str] = field(default_factory=list)
    _baseName: str = ""

    @property
    def outputPath(self) -> str:
        if self.files and len(self.files) > 1:
            return str(self.outputFolder / Path(self.name).stem)
        return super().outputPath

    @property
    def filesFolder(self) -> Path:
        if self.files and len(self.files) > 1:
            return Path(self.outputPath)
        return self.outputFolder

    def setMode(self, mode: DownloadMode) -> None:
        self.mode = mode
        self._rebuildSteps()

    def setSubtitleLanguages(self, languages: list[str]) -> None:
        self.subtitleLanguages = languages
        self._rebuildSteps()

    def deduplicateFilename(self) -> None:
        if len(self.files or []) <= 1:
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
        files: list[BiliPage] = self.files or []
        hasSubs = bool(self.subtitleLanguages)

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
            self.name = toSafeFilename(f"{self._baseName}.m4a", fallback="audio.m4a")
            for file in files:
                file.size = file.audioSize
            self.fileSize = sum(f.size for f in files if f.selected)
            for file in files:
                base = file.index * STEPS_PER_PAGE
                pageSuffix = self._pageSuffix(file)
                self.addStep(BilibiliAudioStep(
                    stepIndex=base + 1,
                    url=file.audioUrl,
                    fileSize=file.audioSize,
                    headers=dict(file.headers),
                    subworkerCount=file.subworkerCount,
                    canUseRangeRequests=True,
                    fileIndex=file.index,
                    pageSuffix=pageSuffix,
                ))
                if hasSubs and file.subtitles:
                    self.addStep(BilibiliSubtitleStep(
                        stepIndex=base + 2,
                        fileIndex=file.index,
                        pageSuffix=pageSuffix,
                    ))
            return

        # VIDEO mode
        self.name = toSafeFilename(f"{self._baseName}.mp4", fallback="video.mp4")
        for file in files:
            file.size = file.videoSize + file.audioSize
        self.fileSize = sum(f.size for f in files if f.selected)
        for file in files:
            base = file.index * STEPS_PER_PAGE
            pageSuffix = self._pageSuffix(file)
            self.addStep(BilibiliVideoStep(
                stepIndex=base + 1,
                url=file.videoUrl,
                fileSize=file.videoSize,
                headers=dict(file.headers),
                subworkerCount=file.subworkerCount,
                canUseRangeRequests=True,
                fileIndex=file.index,
                pageSuffix=pageSuffix,
            ))
            self.addStep(BilibiliAudioStep(
                stepIndex=base + 2,
                url=file.audioUrl,
                fileSize=file.audioSize,
                headers=dict(file.headers),
                subworkerCount=file.subworkerCount,
                canUseRangeRequests=True,
                fileIndex=file.index,
                pageSuffix=pageSuffix,
            ))
            self.addStep(BilibiliMergeStep(
                stepIndex=base + 3,
                fileIndex=file.index,
                pageSuffix=pageSuffix,
            ))
            if hasSubs and file.subtitles:
                self.addStep(BilibiliSubtitleStep(
                    stepIndex=base + 4,
                    fileIndex=file.index,
                    pageSuffix=pageSuffix,
                ))

    def _pageSuffix(self, page: BiliPage) -> str:
        # 后缀跟总分P数走，与选择解耦，保证文件名稳定
        if len(self.files or []) <= 1:
            return ""
        suffix = f" - P{page.pageNumber}"
        part = page.pagePart.strip()
        if part and part != self._baseName:
            suffix += f" {part}"
        return suffix


def pageStem(taskName: str, pageSuffix: str) -> str:
    stem = Path(taskName).stem
    return f"{stem}{pageSuffix}" if pageSuffix else stem


@dataclass(kw_only=True)
class BilibiliVideoStep(HttpTaskStep):
    fileIndex: int = 0
    pageSuffix: str = ""

    @property
    def outputPath(self) -> str:
        return str(self.task.filesFolder / f"{pageStem(self.task.name, self.pageSuffix)}.video.m4s")


@dataclass(kw_only=True)
class BilibiliAudioStep(HttpTaskStep):
    fileIndex: int = 0
    pageSuffix: str = ""

    @property
    def outputPath(self) -> str:
        stem = pageStem(self.task.name, self.pageSuffix)
        ext = ".m4a" if self.task.mode == DownloadMode.AUDIO else ".audio.m4s"
        return str(self.task.filesFolder / f"{stem}{ext}")


@dataclass(kw_only=True)
class BilibiliMergeStep(FFmpegStep):
    fileIndex: int = 0
    pageSuffix: str = ""

    @property
    def outputFile(self) -> str:
        return str(self.task.filesFolder / f"{pageStem(self.task.name, self.pageSuffix)}.mp4")

    @property
    def _videoPath(self) -> Path:
        return self.task.filesFolder / f"{pageStem(self.task.name, self.pageSuffix)}.video.m4s"

    @property
    def _audioPath(self) -> Path:
        return self.task.filesFolder / f"{pageStem(self.task.name, self.pageSuffix)}.audio.m4s"


@dataclass(kw_only=True)
class BilibiliSubtitleStep(TaskStep):
    canPause = False
    fileIndex: int = 0
    pageSuffix: str = ""

    @property
    def outputPath(self) -> str:
        return ""

    def deleteFiles(self) -> None:
        stem = pageStem(self.task.name, self.pageSuffix)
        folder = self.task.filesFolder
        for path in folder.glob(f"{stem}.*.srt"):
            path.unlink(missing_ok=True)

    def moveFiles(self, oldFolder: Path, newFolder: Path) -> None:
        from shutil import move
        stem = pageStem(self.task.name, self.pageSuffix)
        folder = self.task.filesFolder
        for path in folder.glob(f"{stem}.*.srt"):
            target = newFolder / path.relative_to(oldFolder)
            target.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                move(str(path), str(target))

    async def run(self, reportSpeed: Callable[[int], None], waitForSpeedLimit: Callable[[], Awaitable[None]]) -> None:
        from app.client import buildClient

        task: BilibiliTask = self.task
        page = next((f for f in task.files or [] if f.index == self.fileIndex), None)
        subtitles = page.subtitles if page else []
        selectedLangs = set(task.subtitleLanguages)

        matching = [s for s in subtitles if s["lan"] in selectedLangs]
        if not matching:
            self.setStatus(TaskStatus.COMPLETED)
            return

        stem = pageStem(task.name, self.pageSuffix)
        folder = task.filesFolder
        folder.mkdir(parents=True, exist_ok=True)

        def toSrtTime(seconds: float) -> str:
            total_ms = int(round(seconds * 1000))
            h, rem = divmod(total_ms // 1000, 3600)
            m, s = divmod(rem, 60)
            return f"{h:02d}:{m:02d}:{s:02d},{total_ms % 1000:03d}"

        client = buildClient()
        try:
            for sub in matching:
                url = sub.get("subtitle_url", "")
                if not url:
                    continue
                if url.startswith("//"):
                    url = "https:" + url
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    payload = await response.json()
                    body = payload.get("body") or []
                    if not body:
                        continue
                    lines: list[str] = []
                    seq = 0
                    for entry in body:
                        start = float(entry.get("from", 0))
                        end = float(entry.get("to", 0))
                        content = str(entry.get("content", "")).strip()
                        if not content:
                            continue
                        seq += 1
                        lines.append(str(seq))
                        lines.append(f"{toSrtTime(start)} --> {toSrtTime(end)}")
                        lines.append(content)
                        lines.append("")
                    srtFile = folder / f"{stem}.{sub['lan']}.srt"
                    srtFile.write_text("\n".join(lines), encoding="utf-8")
                except Exception:
                    logger.opt(exception=True).debug("Subtitle download failed: {}", sub.get("lan"))
        finally:
            client.close()

        self.setStatus(TaskStatus.COMPLETED)
