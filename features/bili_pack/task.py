from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

from loguru import logger

from app.models.task import Task, TaskStep, TaskStatus
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
    subtitleLanguages: list[str] = field(default_factory=list)
    _baseName: str = ""

    def setMode(self, mode: DownloadMode) -> None:
        self.mode = mode
        self._rebuildSteps()

    def setSubtitleLanguages(self, languages: list[str]) -> None:
        self.subtitleLanguages = languages
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
            suffix = ".m4a" if len(selected) <= 1 else ".m4a"
            self.name = toSafeFilename(f"{self._baseName}{suffix}", fallback=f"audio{suffix}")
            self.fileSize = sum(p["audioSize"] for p in selected)
            stepIndex = 1
            for i, info in enumerate(selected):
                pageSuffix = self._pageSuffix(info)
                self.addStep(BilibiliAudioStep(
                    stepIndex=stepIndex,
                    url=info["audioUrl"],
                    fileSize=info["audioSize"],
                    headers=dict(info.get("headers") or {}),
                    subworkerCount=info.get("subworkerCount", 8),
                    canUseRangeRequests=True,
                    pageIndex=i,
                    pageSuffix=pageSuffix,
                ))
                stepIndex += 1
                if hasSubs and info.get("subtitles"):
                    self.addStep(BilibiliSubtitleStep(
                        stepIndex=stepIndex,
                        pageIndex=i,
                        pageSuffix=pageSuffix,
                    ))
                    stepIndex += 1
            return

        # VIDEO mode
        self.name = toSafeFilename(f"{self._baseName}.mp4", fallback="video.mp4")
        self.fileSize = sum(p["videoSize"] + p["audioSize"] for p in selected)
        stepIndex = 1
        for i, info in enumerate(selected):
            pageSuffix = self._pageSuffix(info)
            self.addStep(BilibiliVideoStep(
                stepIndex=stepIndex,
                url=info["videoUrl"],
                fileSize=info["videoSize"],
                headers=dict(info.get("headers") or {}),
                subworkerCount=info.get("subworkerCount", 8),
                canUseRangeRequests=True,
                pageIndex=i,
                pageSuffix=pageSuffix,
            ))
            self.addStep(BilibiliAudioStep(
                stepIndex=stepIndex + 1,
                url=info["audioUrl"],
                fileSize=info["audioSize"],
                headers=dict(info.get("headers") or {}),
                subworkerCount=info.get("subworkerCount", 8),
                canUseRangeRequests=True,
                pageIndex=i,
                pageSuffix=pageSuffix,
            ))
            self.addStep(BilibiliMergeStep(
                stepIndex=stepIndex + 2,
                pageIndex=i,
                pageSuffix=pageSuffix,
            ))
            stepIndex += 3
            if hasSubs and info.get("subtitles"):
                self.addStep(BilibiliSubtitleStep(
                    stepIndex=stepIndex,
                    pageIndex=i,
                    pageSuffix=pageSuffix,
                ))
                stepIndex += 1

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


@dataclass(kw_only=True)
class BilibiliSubtitleStep(TaskStep):
    canPause = False
    pageIndex: int = 0
    pageSuffix: str = ""

    @property
    def outputPath(self) -> str:
        return ""

    def deleteFiles(self) -> None:
        stem = pageStem(self.task.name, self.pageSuffix)
        for path in self.task.outputFolder.glob(f"{stem}.*.srt"):
            path.unlink(missing_ok=True)

    def moveFiles(self, oldFolder: Path, newFolder: Path) -> None:
        from shutil import move
        stem = pageStem(self.task.name, self.pageSuffix)
        for path in oldFolder.glob(f"{stem}.*.srt"):
            target = newFolder / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                move(str(path), str(target))

    async def run(self) -> None:
        from app.client import buildClient

        task: BilibiliTask = self.task
        pageInfo = task.selectedPages[self.pageIndex]
        subtitles = pageInfo.get("subtitles") or []
        selectedLangs = set(task.subtitleLanguages)

        matching = [s for s in subtitles if s["lan"] in selectedLangs]
        if not matching:
            self.setStatus(TaskStatus.COMPLETED)
            return

        stem = pageStem(task.name, self.pageSuffix)
        task.outputFolder.mkdir(parents=True, exist_ok=True)

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
                    srtFile = task.outputFolder / f"{stem}.{sub['lan']}.srt"
                    srtFile.write_text("\n".join(lines), encoding="utf-8")
                except Exception:
                    logger.opt(exception=True).debug("Subtitle download failed: {}", sub.get("lan"))
        finally:
            client.close()

        self.setStatus(TaskStatus.COMPLETED)
