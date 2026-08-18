from __future__ import annotations

import asyncio
import shutil
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QCoreApplication

from app.models.task import Task, TaskError, TaskFile, TaskStep, TaskStatus, SpecialFileSize
from app.platform.filesystem import toSafeFilename
from http_pack.task import HttpTaskStep
from ffmpeg_pack.task import FFmpegStep
from .stream import buildSize, fetchPlayurl, probeSize, toStreamUrl

AUDIO_QUALITY_LABELS = {30216: "64K", 30232: "132K", 30280: "192K", 30250: "杜比全景声", 30251: "Hi-Res"}


def buildTimeSuffix(startTime: int, endTime: int) -> str:
    def fmt(sec: int) -> str:
        m, s = divmod(sec, 60)
        return f"{m:02d}m{s:02d}s"
    return f"[{fmt(startTime)}-{fmt(endTime)}]"


def parseSegmentBaseEndByte(streams: list[dict], url: str) -> int:
    for s in streams:
        if toStreamUrl(s) == url:
            segBase = s.get("SegmentBase") or s.get("segment_base") or {}
            indexRange = segBase.get("indexRange") or segBase.get("index_range") or ""
            if indexRange and "-" in indexRange:
                return int(indexRange.split("-")[1])
    return 4095


def pageByIndex(task, fileIndex: int):
    return next((f for f in task.files or [] if f.index == fileIndex), None)


def setEpisodeTitle(pages: list[BiliPage], name: str) -> None:
    name = name.strip()
    if not pages or not name:
        return
    multi = len(pages) > 1
    for page in pages:
        page.episodeTitle = name
        page.relativePath = f"{name} - P{page.pageNumber}" if multi else name


def setTimeRanges(pages: list[BiliPage], ranges: dict[int, tuple[int, int]]) -> None:
    for page in pages:
        if page.index in ranges:
            page.startTime, page.endTime = ranges[page.index]


def setPagePart(page: BiliPage, name: str) -> None:
    name = name.strip()
    page.pagePart = name
    if page.episodeTitle:
        page.relativePath = f"{page.episodeTitle} - P{page.pageNumber}"
    else:
        page.relativePath = name or f"P{page.pageNumber}"


@dataclass(kw_only=True)
class BiliPage(TaskFile):
    cid: int = 0
    pagePart: str = ""
    pageNumber: int = 1
    bvid: str = ""
    episodeTitle: str = ""
    sectionTitle: str = ""
    coverUrl: str = ""
    videoUrl: str = ""
    audioUrl: str = ""
    videoSize: int = 0
    audioSize: int = 0
    startTime: int = 0
    endTime: int = 0
    headers: dict = field(default_factory=dict)
    subworkerCount: int = 8
    subtitles: list[dict] = field(default_factory=list)
    _duration: int = field(default=0, repr=False)
    _videoStreams: list[dict] = field(default_factory=list, repr=False)
    _audioStreams: list[dict] = field(default_factory=list, repr=False)


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
    requestedQn: int = 0
    requestedCodecid: int = 0
    requestedAudioQn: int = 0
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

    @property
    def isSeason(self) -> bool:
        files = self.files or []
        return any(f.episodeTitle for f in files) or len({f.bvid for f in files if f.bvid}) > 1

    def episodeGroups(self) -> list[list[BiliPage]]:
        groups: dict[str, list[BiliPage]] = {}
        order: list[str] = []
        for page in self.files or []:
            key = page.bvid or f"#{page.index}"
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(page)
        return [groups[k] for k in order]

    @property
    def hasAudio(self) -> bool:
        return any(f.audioUrl or f._audioStreams for f in self.files or [])

    def seasonSummary(self) -> str:
        groups = self.episodeGroups()
        selected = sum(1 for g in groups if any(p.selected for p in g))
        return QCoreApplication.translate(
            "BilibiliTask", "{0}/{1} 集"
        ).format(selected, len(groups))

    def setSelection(self, selectedIndexes) -> None:
        super().setSelection(selectedIndexes)
        if self.isCoverEnabled:
            self.fileSize += self.coverSize
        have = {s.fileIndex for s in self.steps if s.fileIndex is not None}
        stepIndex = max((s.stepIndex for s in self.steps), default=0)
        for file in (self.files or []):
            if file.selected and file.index not in have:
                stepIndex = self._addFileSteps(file, stepIndex)
        self._addCoverSteps(stepIndex)
        self.updateSuffixes()
        self.updateStatus()

    def updateSuffixes(self) -> None:
        for step in self.steps:
            fileIndex = getattr(step, "fileIndex", None)
            if fileIndex is None or not hasattr(step, "pageSuffix"):
                continue
            page = pageByIndex(self, fileIndex)
            if page is not None:
                step.pageSuffix = self._pageSuffix(page)

    def setName(self, name: str):
        super().setName(name)
        self._baseName = Path(self.name).stem

    def setVideoQuality(self, qn: int, codecid: int) -> None:
        self.requestedQn = qn
        self.requestedCodecid = codecid
        template = None
        for page in (self.files or []):
            stream = next((s for s in page._videoStreams if s["id"] == qn and s["codecid"] == codecid), None)
            if stream and toStreamUrl(stream):
                template = stream
                page.videoUrl = toStreamUrl(stream)
                page.videoSize = buildSize(stream, page._duration)
        if template:
            for page in (self.files or []):
                if not page._videoStreams:
                    page.videoUrl = ""
                    page.videoSize = buildSize(template, page._duration)
        self.update()

    def setAudioQuality(self, qn: int) -> None:
        self.requestedAudioQn = qn
        template = None
        for page in (self.files or []):
            stream = next((s for s in page._audioStreams if s["id"] == qn), None)
            if stream and toStreamUrl(stream):
                template = stream
                page.audioUrl = toStreamUrl(stream)
                page.audioSize = buildSize(stream, page._duration)
        if template:
            for page in (self.files or []):
                if not page._audioStreams:
                    page.audioUrl = ""
                    page.audioSize = buildSize(template, page._duration)
        self.update()

    def setSubtitleLanguages(self, languages: list[str]) -> None:
        self.subtitleLanguages = languages
        self.update()

    def update(self) -> None:
        self.steps.clear()
        files: list[BiliPage] = self.files or []

        timeSuffix = ""
        if len(files) == 1 and (files[0].startTime or files[0].endTime):
            timeSuffix = f" {buildTimeSuffix(files[0].startTime, files[0].endTime)}"

        if self.isVideoEnabled:
            self.name = toSafeFilename(f"{self._baseName}{timeSuffix}.mp4", fallback="video.mp4")
        elif self.isAudioEnabled:
            self.name = toSafeFilename(f"{self._baseName}{timeSuffix}.m4a", fallback="audio.m4a")
        elif self.isCoverEnabled:
            self.name = toSafeFilename(f"{self._baseName}.jpg", fallback="cover.jpg")
        else:
            for file in files:
                file.size = 0
            self.fileSize = 0
            return

        for file in files:
            fullSize = (file.videoSize if self.isVideoEnabled else 0) + (file.audioSize if self.isAudioEnabled else 0)
            if (file.startTime or file.endTime) and file._duration > 0:
                fullSize = int(fullSize * (file.endTime - file.startTime) / file._duration)
            file.size = fullSize
        self.fileSize = sum(f.size for f in files if f.selected) + (self.coverSize if self.isCoverEnabled else 0)

        stepIndex = 0
        for file in files:
            if file.selected:
                stepIndex = self._addFileSteps(file, stepIndex)
        self._addCoverSteps(stepIndex)
        self.updateStatus()

    def _addCoverSteps(self, stepIndex: int) -> int:
        if not self.isCoverEnabled:
            return stepIndex
        have = {s.fileIndex for s in self.steps if isinstance(s, BilibiliCoverStep)}
        covers: list[tuple[str, int, int | None]] = []
        if self.coverUrl:
            covers.append((self.coverUrl, self.coverSize, None))
        if self.isSeason:
            seen: set[str] = set()
            for page in self.files or []:
                if not page.selected or not page.coverUrl:
                    continue
                key = page.bvid or f"#{page.index}"
                if key in seen:
                    continue
                seen.add(key)
                covers.append((page.coverUrl, 0, page.index))
        referer = next((p.headers.get("referer") for p in (self.files or []) if p.headers.get("referer")), "")
        headers = {"referer": referer} if referer else {}
        for url, size, fileIndex in covers:
            if fileIndex in have:
                continue
            stepIndex += 1
            self.steps.append(BilibiliCoverStep(
                stepIndex=stepIndex,
                url=url,
                fileSize=size,
                headers=headers,
                canUseRangeRequests=size > 0,
                subworkerCount=1,
                fileIndex=fileIndex,
            ))
            self.steps[-1]._bindTask(self)
            have.add(fileIndex)
        return stepIndex

    def _addFileSteps(self, file: BiliPage, stepIndex: int) -> int:
        hasSubs = bool(self.subtitleLanguages)
        useAudio = self.isAudioEnabled and (self.hasAudio or len(self.files or []) > 1)
        needsMerge = self.isVideoEnabled and useAudio
        pageSuffix = self._pageSuffix(file)
        fileTrim = bool(file.startTime or file.endTime)
        if self.isVideoEnabled:
            stepIndex += 1
            self.steps.append(BilibiliVideoStep(
                stepIndex=stepIndex,
                url=file.videoUrl,
                fileSize=file.videoSize,
                headers=dict(file.headers),
                subworkerCount=file.subworkerCount,
                canUseRangeRequests=True,
                fileIndex=file.index,
                pageSuffix=pageSuffix,
            ))
            self.steps[-1]._bindTask(self)
        if useAudio:
            stepIndex += 1
            self.steps.append(BilibiliAudioStep(
                stepIndex=stepIndex,
                url=file.audioUrl,
                fileSize=file.audioSize,
                headers=dict(file.headers),
                subworkerCount=file.subworkerCount,
                canUseRangeRequests=True,
                fileIndex=file.index,
                pageSuffix=pageSuffix,
            ))
            self.steps[-1]._bindTask(self)
        if needsMerge or fileTrim:
            stepIndex += 1
            self.steps.append(BilibiliMergeStep(
                stepIndex=stepIndex,
                fileIndex=file.index,
                pageSuffix=pageSuffix,
            ))
            self.steps[-1]._bindTask(self)
        if hasSubs and (self.isVideoEnabled or self.isAudioEnabled):
            stepIndex += 1
            self.steps.append(BilibiliSubtitleStep(
                stepIndex=stepIndex,
                fileIndex=file.index,
                pageSuffix=pageSuffix,
            ))
            self.steps[-1]._bindTask(self)
        return stepIndex

    def _pageSuffix(self, page: BiliPage) -> str:
        if len(self.files or []) <= 1:
            return ""
        if page.episodeTitle:
            title = toSafeFilename(page.episodeTitle, fallback=page.bvid or "video")
            same = sum(1 for f in (self.files or []) if f.bvid == page.bvid)
            if same > 1:
                suffix = f" - {title} - P{page.pageNumber}"
                part = toSafeFilename(page.pagePart.strip(), fallback="") if page.pagePart.strip() else ""
                if part and part != title:
                    suffix += f" {part}"
            else:
                suffix = f" - {title}"
        else:
            suffix = f" - P{page.pageNumber}"
            part = page.pagePart.strip()
            if part and part != self._baseName:
                suffix += f" {toSafeFilename(part, fallback=part)}"
        if page.startTime or page.endTime:
            suffix += f" {buildTimeSuffix(page.startTime, page.endTime)}"
        return suffix


def pageStem(taskName: str, pageSuffix: str) -> str:
    stem = Path(taskName).stem
    return f"{stem}{pageSuffix}" if pageSuffix else stem


@dataclass(kw_only=True)
class BilibiliCoverStep(HttpTaskStep):

    @property
    def outputPath(self) -> str:
        stem = self.task._baseName
        if self.fileIndex is not None:
            page = pageByIndex(self.task, self.fileIndex)
            title = (page.episodeTitle or page.bvid or f"#{page.index}") if page else ""
            if title:
                stem = f"{stem} - {title}"
        return str(self.task.filesFolder / toSafeFilename(f"{stem}.jpg", fallback="cover.jpg"))


@dataclass(kw_only=True)
class BilibiliVideoStep(HttpTaskStep):
    fileIndex: int = 0
    pageSuffix: str = ""

    @property
    def outputPath(self) -> str:
        stem = pageStem(self.task.name, self.pageSuffix)
        page = pageByIndex(self.task, self.fileIndex)
        hasTrim = page is not None and bool(page.startTime or page.endTime)
        if (self.task.isAudioEnabled and (self.task.hasAudio or len(self.task.files or []) > 1)) or hasTrim:
            return str(self.task.filesFolder / f"{stem}.video.m4s")
        return str(self.task.filesFolder / f"{stem}.mp4")

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        page = pageByIndex(self.task, self.fileIndex)
        if page and not page.videoUrl:
            from .config import bilibiliConfig
            qn = self.task.requestedQn or bilibiliConfig.defaultQuality.value
            _, _, usedQn = await fetchPlayurl(
                page, qn=qn, headers=page.headers, audioQn=self.task.requestedAudioQn,
            )
            self.task.requestedQn = usedQn
        if page:
            self.url = page.videoUrl
            self.fileSize = page.videoSize
            self.headers = dict(page.headers)
        if not self.url:
            raise TaskError("未获取到视频流地址")
        if page and (page.startTime or page.endTime):
            await self._updateSegmentRange(page)
        else:
            size = await probeSize(self.url, self.headers)
            self.fileSize = size if size > 0 else SpecialFileSize.UNKNOWN
        await super().run(reportSpeed, waitForSpeedLimit)

    async def _updateSegmentRange(self, page: BiliPage) -> None:
        from app.client import buildClient
        from app.container import buildMp4SegmentRange

        endByte = parseSegmentBaseEndByte(page._videoStreams, self.url)
        client = buildClient()
        try:
            headers = {**self.headers, "range": f"bytes=0-{endByte}", "accept-encoding": "identity"}
            response = await client.get(self.url, headers=headers)
            try:
                headerData = await response.bytes()
            finally:
                response.close()
        finally:
            client.close()

        try:
            segRange = buildMp4SegmentRange(headerData, page.startTime, page.endTime)
        except Exception as e:
            logger.warning("segment range parsing failed for {}: {}", self.url, e)
            return

        self.httpByteOffset = segRange.segStart
        self.fileSize = segRange.segEnd - segRange.segStart

        for mergeStep in self.task.steps:
            if isinstance(mergeStep, BilibiliMergeStep) and mergeStep.fileIndex == self.fileIndex:
                mergeStep.patchedVideoHeader = segRange.patchedHeader
                mergeStep.segStartTime = segRange.segStartTime
                break


@dataclass(kw_only=True)
class BilibiliAudioStep(HttpTaskStep):
    fileIndex: int = 0
    pageSuffix: str = ""

    @property
    def outputPath(self) -> str:
        stem = pageStem(self.task.name, self.pageSuffix)
        page = pageByIndex(self.task, self.fileIndex)
        hasTrim = page is not None and bool(page.startTime or page.endTime)
        if self.task.isVideoEnabled or hasTrim:
            return str(self.task.filesFolder / f"{stem}.audio.m4s")
        return str(self.task.filesFolder / f"{stem}.m4a")

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        page = pageByIndex(self.task, self.fileIndex)
        if page and not page.audioUrl:
            from .config import bilibiliConfig
            qn = self.task.requestedQn or bilibiliConfig.defaultQuality.value
            _, _, usedQn = await fetchPlayurl(
                page, qn=qn, headers=page.headers, audioQn=self.task.requestedAudioQn,
            )
            self.task.requestedQn = usedQn
        if page:
            self.url = page.audioUrl
            self.fileSize = page.audioSize
            self.headers = dict(page.headers)
        if not self.url:
            self.setStatus(TaskStatus.COMPLETED)
            return
        if page and (page.startTime or page.endTime):
            await self._updateSegmentRange(page)
        else:
            size = await probeSize(self.url, self.headers)
            self.fileSize = size if size > 0 else SpecialFileSize.UNKNOWN
        await super().run(reportSpeed, waitForSpeedLimit)

    async def _updateSegmentRange(self, page: BiliPage) -> None:
        from app.client import buildClient
        from app.container import buildMp4SegmentRange

        endByte = parseSegmentBaseEndByte(page._audioStreams, self.url)
        client = buildClient()
        try:
            headers = {**self.headers, "range": f"bytes=0-{endByte}", "accept-encoding": "identity"}
            response = await client.get(self.url, headers=headers)
            try:
                headerData = await response.bytes()
            finally:
                response.close()
        finally:
            client.close()

        try:
            segRange = buildMp4SegmentRange(headerData, page.startTime, page.endTime)
        except Exception as e:
            logger.warning("segment range parsing failed for {}: {}", self.url, e)
            return

        self.httpByteOffset = segRange.segStart
        self.fileSize = segRange.segEnd - segRange.segStart

        for mergeStep in self.task.steps:
            if isinstance(mergeStep, BilibiliMergeStep) and mergeStep.fileIndex == self.fileIndex:
                mergeStep.patchedAudioHeader = segRange.patchedHeader
                mergeStep.segStartTime = segRange.segStartTime
                break


@dataclass(kw_only=True)
class BilibiliMergeStep(FFmpegStep):
    fileIndex: int = 0
    pageSuffix: str = ""
    patchedVideoHeader: bytes = field(default=b"", repr=False)
    patchedAudioHeader: bytes = field(default=b"", repr=False)
    segStartTime: float = field(default=0.0, repr=False)

    @property
    def outputFile(self) -> str:
        stem = pageStem(self.task.name, self.pageSuffix)
        ext = "mp4" if self.task.isVideoEnabled else "m4a"
        return str(self.task.filesFolder / f"{stem}.{ext}")

    @property
    def _videoPath(self) -> Path:
        return self.task.filesFolder / f"{pageStem(self.task.name, self.pageSuffix)}.video.m4s"

    @property
    def _audioPath(self) -> Path:
        return self.task.filesFolder / f"{pageStem(self.task.name, self.pageSuffix)}.audio.m4s"

    @property
    def _timeRange(self) -> tuple[int, int] | None:
        page = pageByIndex(self.task, self.fileIndex)
        if page and (page.startTime or page.endTime):
            return page.startTime, page.endTime
        return None

    def _buildTrimArgs(self) -> tuple[list[str], list[str]]:
        tr = self._timeRange
        if not tr:
            return [], []
        relSS = tr[0] - self.segStartTime
        return ["-ss", str(relSS)], ["-t", str(tr[1] - tr[0])]

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        for header, path in [
            (self.patchedVideoHeader, self._videoPath),
            (self.patchedAudioHeader, self._audioPath),
        ]:
            if header and path.exists():
                tmp = path.with_suffix(".tmp")
                with open(tmp, "wb") as f:
                    f.write(header)
                    with open(path, "rb") as seg:
                        shutil.copyfileobj(seg, f)
                tmp.replace(path)

        hasVideo = self._videoPath.exists()
        hasAudio = self._audioPath.exists()

        if hasVideo and hasAudio:
            if self._timeRange:
                await self._runWithTrim()
            else:
                await super().run(reportSpeed, waitForSpeedLimit)
            return

        singleInput = self._videoPath if hasVideo else self._audioPath if hasAudio else None
        if not singleInput:
            self.setStatus(TaskStatus.COMPLETED)
            return

        if self._timeRange:
            await self._runWithTrim()
        else:
            outputPath = Path(self.outputFile)
            outputPath.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(singleInput), str(outputPath))
            Path(f"{singleInput}.ghd").unlink(missing_ok=True)
            self.setStatus(TaskStatus.COMPLETED)

    async def _runWithTrim(self) -> None:
        from ffmpeg_pack.config import ffmpegRuntime
        from app.platform.filesystem import deletePath

        ffmpegPath = ffmpegRuntime.path()
        ffprobePath = ffmpegRuntime.ffprobePath()
        if not ffmpegPath or not ffprobePath:
            raise TaskError("{name} 未安装，请在设置中安装", name="FFmpeg")

        Path(self.outputFile).parent.mkdir(parents=True, exist_ok=True)
        probeInput = self._videoPath if self._videoPath.exists() else self._audioPath
        totalDuration = await self._probeDuration(ffprobePath, probeInput)

        preArgs, postArgs = self._buildTrimArgs()
        args = [ffmpegPath, "-y", "-v", "error", "-nostats", "-progress", "pipe:1"]
        for path in (self._videoPath, self._audioPath):
            if path.exists():
                args.extend([*preArgs, "-i", str(path)])
        args.extend([*postArgs, "-c", "copy", self.outputFile])

        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        progressTask = asyncio.create_task(self._readProgress(process.stdout, totalDuration))

        try:
            await process.wait()
            await progressTask

            if process.returncode != 0:
                stderr = (await process.stderr.read()).decode("utf-8", errors="ignore").strip()
                raise TaskError(
                    "FFmpeg 合并失败（{code}）：{detail}",
                    code=process.returncode,
                    detail=stderr or "unknown error",
                )

            self.setStatus(TaskStatus.COMPLETED)

            if self.shouldDeleteSource:
                for path in (self._videoPath, self._audioPath):
                    if path.exists():
                        deletePath(path)
                        deletePath(Path(f"{path}.ghd"))
        except asyncio.CancelledError:
            self.setStatus(TaskStatus.PAUSED)
            if process.returncode is None:
                process.kill()
                await process.wait()
            if not progressTask.done():
                progressTask.cancel()
                with suppress(asyncio.CancelledError):
                    await progressTask
            raise


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
        pageHeaders = dict(page.headers) if page and page.headers else {}
        referer = pageHeaders.get("referer") or "https://www.bilibili.com"
        cookie = pageHeaders.get("cookie") or ""
        listHeaders = {"referer": referer}
        if cookie:
            listHeaders["cookie"] = cookie

        if page and not page.subtitles:
            from .stream import fetchSubtitles
            subClient = buildClient(emulation=None, headers=listHeaders)
            try:
                page.subtitles = await fetchSubtitles(subClient, page)
            finally:
                subClient.close()
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

        client = buildClient(headers={"referer": referer})
        written = 0
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
                    if not seq:
                        continue
                    srtFile = folder / f"{stem}.{sub['lan']}.srt"
                    srtFile.write_text("\n".join(lines), encoding="utf-8")
                    written += 1
                except Exception:
                    logger.opt(exception=True).debug("Subtitle download failed: {}", sub.get("lan"))
        finally:
            client.close()

        if written == 0:
            raise TaskError("字幕下载失败")
        self.setStatus(TaskStatus.COMPLETED)
