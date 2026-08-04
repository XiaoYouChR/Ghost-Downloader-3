from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from app.models.task import Task, TaskFile, TaskStep, TaskStatus
from app.platform.filesystem import toSafeFilename
from http_pack.task import HttpTaskStep
from ffmpeg_pack.task import FFmpegStep

AUDIO_QUALITY_LABELS = {30216: "64K", 30232: "132K", 30280: "192K", 30250: "杜比全景声", 30251: "Hi-Res"}


def streamUrl(s: dict) -> str:
    url = s.get("baseUrl") or ""
    if url:
        return url
    for item in (s.get("backupUrl") or []):
        if item:
            return item
    return ""


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
    _duration: int = field(default=0, repr=False)
    _videoStreams: list[dict] = field(default_factory=list, repr=False)
    _audioStreams: list[dict] = field(default_factory=list, repr=False)

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
    isVideoEnabled: bool = True
    isAudioEnabled: bool = True
    isCoverEnabled: bool = False
    subtitleLanguages: list[str] = field(default_factory=list)
    _baseName: str = ""
    _acceptQualities: list[int] = field(default_factory=list, repr=False)
    _qualityLabels: list[str] = field(default_factory=list, repr=False)

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

    def setSelection(self, selectedIndexes) -> None:
        super().setSelection(selectedIndexes)
        if self.isCoverEnabled:
            self.fileSize += self.coverSize

    def setName(self, name: str):
        super().setName(name)
        self._baseName = Path(self.name).stem

    def setVideoQuality(self, qn: int, codecid: int) -> None:
        for page in (self.files or []):
            stream = next((s for s in page._videoStreams if s["id"] == qn and s["codecid"] == codecid), None)
            if stream and streamUrl(stream):
                page.videoUrl = streamUrl(stream)
                page.videoSize = stream["bandwidth"] * page._duration // 8
        self._rebuildSteps()

    def setAudioQuality(self, qn: int) -> None:
        for page in (self.files or []):
            stream = next((s for s in page._audioStreams if s["id"] == qn), None)
            if stream and streamUrl(stream):
                page.audioUrl = streamUrl(stream)
                page.audioSize = stream["bandwidth"] * page._duration // 8
        self._rebuildSteps()

    def setSubtitleLanguages(self, languages: list[str]) -> None:
        self.subtitleLanguages = languages
        self._rebuildSteps()

    def _rebuildSteps(self) -> None:
        self.steps.clear()
        files: list[BiliPage] = self.files or []
        hasSubs = bool(self.subtitleLanguages)
        needsMerge = self.isVideoEnabled and self.isAudioEnabled

        if self.isVideoEnabled:
            self.name = toSafeFilename(f"{self._baseName}.mp4", fallback="video.mp4")
        elif self.isAudioEnabled:
            self.name = toSafeFilename(f"{self._baseName}.m4a", fallback="audio.m4a")
        elif self.isCoverEnabled:
            self.name = toSafeFilename(f"{self._baseName}.jpg", fallback="cover.jpg")
        else:
            for file in files:
                file.size = 0
            self.fileSize = 0
            return

        for file in files:
            file.size = (file.videoSize if self.isVideoEnabled else 0) + (file.audioSize if self.isAudioEnabled else 0)
        self.fileSize = sum(f.size for f in files if f.selected) + (self.coverSize if self.isCoverEnabled else 0)

        stepIndex = 0
        for file in files:
            pageSuffix = self._pageSuffix(file)
            if self.isVideoEnabled:
                stepIndex += 1
                self.addStep(BilibiliVideoStep(
                    stepIndex=stepIndex,
                    url=file.videoUrl,
                    fileSize=file.videoSize,
                    headers=dict(file.headers),
                    subworkerCount=file.subworkerCount,
                    canUseRangeRequests=True,
                    fileIndex=file.index,
                    pageSuffix=pageSuffix,
                ))
            if self.isAudioEnabled:
                stepIndex += 1
                self.addStep(BilibiliAudioStep(
                    stepIndex=stepIndex,
                    url=file.audioUrl,
                    fileSize=file.audioSize,
                    headers=dict(file.headers),
                    subworkerCount=file.subworkerCount,
                    canUseRangeRequests=True,
                    fileIndex=file.index,
                    pageSuffix=pageSuffix,
                ))
            if needsMerge:
                stepIndex += 1
                self.addStep(BilibiliMergeStep(
                    stepIndex=stepIndex,
                    fileIndex=file.index,
                    pageSuffix=pageSuffix,
                ))
            if hasSubs and file.subtitles and (self.isVideoEnabled or self.isAudioEnabled):
                stepIndex += 1
                self.addStep(BilibiliSubtitleStep(
                    stepIndex=stepIndex,
                    fileIndex=file.index,
                    pageSuffix=pageSuffix,
                ))

        if self.isCoverEnabled and self.coverUrl:
            stepIndex += 1
            self.addStep(HttpTaskStep(
                stepIndex=stepIndex,
                url=self.coverUrl,
                fileSize=self.coverSize,
                headers={},
                canUseRangeRequests=self.coverSize > 0,
                subworkerCount=1,
                outputFile=str(self.filesFolder / f"{self._baseName}.jpg"),
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
        stem = pageStem(self.task.name, self.pageSuffix)
        if self.task.isAudioEnabled:
            return str(self.task.filesFolder / f"{stem}.video.m4s")
        return str(self.task.filesFolder / f"{stem}.mp4")


@dataclass(kw_only=True)
class BilibiliAudioStep(HttpTaskStep):
    fileIndex: int = 0
    pageSuffix: str = ""

    @property
    def outputPath(self) -> str:
        stem = pageStem(self.task.name, self.pageSuffix)
        if self.task.isVideoEnabled:
            return str(self.task.filesFolder / f"{stem}.audio.m4s")
        return str(self.task.filesFolder / f"{stem}.m4a")


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

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
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
