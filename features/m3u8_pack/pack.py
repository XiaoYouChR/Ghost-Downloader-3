from __future__ import annotations

import asyncio
from email.message import Message
from email.utils import collapse_rfc2231_value
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, unquote, urlparse

import m3u8
from loguru import logger
from mpegdash.parser import MPEGDASHParser

from app.client import buildClient, toEmulation
from app.config.cfg import cfg
from app.i18n import N

from app.models.pack import FeaturePack, TaskParser, FileType
from app.models.task import PageTaskOptions, ResourceTaskOptions, Task, TaskOptions
from app.platform.filesystem import localFilePath, toSafeFilename
from .config import m3u8Config, m3u8Runtime
from .task import MANIFEST_SUFFIXES, M3U8SubtitleStep, M3U8Task, M3U8TaskStep
from .vimeo import buildVimeoFiles, matchVimeoPlaylist

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
    from app.view.cards.draft_cards import DraftCard
    from app.view.cards.task_cards import TaskCard
    from app.view.components.option_cards import OptionCard
    from app.models.pack import BinaryRuntime, PackServices


MEDIA_SUFFIXES = {
    ".m3u8", ".m3u", ".mpd", ".mp4", ".mkv",
    ".ts", ".webm", ".m4a", ".m4v", ".vtt", ".srt",
}
MANIFEST_CONTENT_TYPES = {"application/vnd.apple.mpegurl", "application/x-mpegurl", "application/mpegurl",
                          "audio/mpegurl", "audio/x-mpegurl", "application/dash+xml"}
# Only the tags we read: m3u8 crashes on vendor attributes in other tags, which RFC 8216 says to ignore.
READ_TAGS = ("#EXTINF", "#EXT-X-ENDLIST", "#EXT-X-STREAM-INF", "#EXT-X-MEDIA:")


def parsePlaylist(body: str, uri: str | None = None) -> m3u8.M3U8:
    return m3u8.loads(body, uri=uri, custom_tags_parser=lambda line, *_: not line.startswith(READ_TAGS))


class M3U8Parser(TaskParser):
    priority = 80

    def match(self, options: TaskOptions) -> bool:
        if localFilePath(options.url, MANIFEST_SUFFIXES) is not None or matchVimeoPlaylist(options.url):
            return True
        lowered = options.url.lower()
        if ".m3u" in lowered or ".mpd" in lowered:
            return True
        if not options.isProbed:
            return False
        # The MIME alone is enough: parse checks the body and falls back to a plain file.
        return (Path(options.file.name).suffix.lower() in MANIFEST_SUFFIXES
                or options.file.contentType in MANIFEST_CONTENT_TYPES)

    async def parse(self, options: TaskOptions) -> Task:
        url = options.url.strip()
        headers = dict(options.headers)
        outputFolder = options.outputFolder

        localPath = localFilePath(url, MANIFEST_SUFFIXES)
        if localPath is not None:
            url = str(localPath.resolve())
            body = await asyncio.to_thread(localPath.read_text, encoding="utf-8", errors="ignore")
            if "http://" not in body and "https://" not in body:
                raise ValueError("该本地清单只含相对段路径, 缺少 base URL 无法下载, 请改用原始在线链接")
            manifestUrl = url
            responseHeaders: dict[str, str] = {}
        else:
            emulation = toEmulation(
                options.clientProfile or cfg.clientProfile.value,
                options.sourceUserAgent,
            )
            client = buildClient(emulation=emulation, headers=headers,
                                 userAgent=options.userAgent or None,
                                 sourceUserAgent=options.sourceUserAgent)
            try:
                response = await client.get(url)
                response.raise_for_status()
                body = await response.text()
                responseHeaders = {bytes(k).decode().lower(): bytes(v).decode() for k, v in response.headers}
                manifestUrl = str(response.url)
            finally:
                client.close()

        isVimeo = matchVimeoPlaylist(url)
        if isVimeo:
            body = buildVimeoFiles(body, manifestUrl)["master.m3u8"].decode()

        loweredUrl = manifestUrl.lower()
        contentType = responseHeaders.get("content-type", "").lower()
        sample = body.lstrip()[:256].lower()
        if options.isProbed and not (sample.startswith("#extm3u") or "<mpd" in sample):
            raise ValueError("不是流媒体清单")
        if ".mpd" in loweredUrl or "dash+xml" in contentType or sample.startswith("<mpd"):
            manifestType = "mpd"
        else:
            manifestType = "m3u8"

        if manifestType == "mpd":
            lowered = body.lower()
            isLive = 'type="dynamic"' in lowered or "type='dynamic'" in lowered
        elif isVimeo:
            isLive = False
        else:
            playlist = parsePlaylist(body, uri=manifestUrl)
            if playlist.segments:
                isLive = not playlist.is_endlist
            elif playlist.playlists:
                variantUrl = playlist.playlists[0].absolute_uri or ""
                if variantUrl.lower().startswith(("http://", "https://")):
                    try:
                        variantClient = buildClient(emulation=toEmulation(
                            options.clientProfile or cfg.clientProfile.value,
                            options.sourceUserAgent,
                        ), headers=headers, userAgent=options.userAgent or None,
                            sourceUserAgent=options.sourceUserAgent)
                        try:
                            variantResponse = await variantClient.get(variantUrl)
                            variantResponse.raise_for_status()
                            variantBody = await variantResponse.text()
                        finally:
                            variantClient.close()
                        isLive = not parsePlaylist(variantBody, uri=variantUrl).is_endlist
                    except Exception as e:
                        logger.warning("取变体清单判活失败, 按点播处理: {}", repr(e))
                        isLive = False
                else:
                    isLive = False
            else:
                isLive = "#ext-x-endlist" not in body.lower()

        extension = "ts" if isLive else m3u8Config.outputFormat.value
        streams = self._parseStreams(body, manifestType)

        name = ""
        if isinstance(options, PageTaskOptions) and options.pageTitle:
            name = toSafeFilename(options.pageTitle, fallback="")
        elif isinstance(options, ResourceTaskOptions) and options.name:
            name = options.name

        if not name:
            cd = responseHeaders.get("content-disposition", "")
            if cd:
                msg = Message()
                msg["Content-Disposition"] = cd
                params = msg.get_params(header="Content-Disposition")
                paramDict = {k.lower(): v for k, v in params}
                name = collapse_rfc2231_value(
                    paramDict.get("filename") or paramDict.get("filename*") or ""
                ).strip("\"' ")

        if not name:
            parsedManifest = urlparse(manifestUrl)
            for key in ("filename", "file", "name", "title"):
                values = parse_qs(parsedManifest.query).get(key)
                if values:
                    name = values[0]
                    break

        if not name and urlparse(manifestUrl).path:
            name = unquote(Path(urlparse(manifestUrl).path).name)

        if name:
            suffix = Path(name).suffix
            stem = name[:-len(suffix)] if suffix.lower() in MEDIA_SUFFIXES else name
            name = toSafeFilename(stem, fallback="stream")
            name = f"{name}.{extension}"
        else:
            name = f"stream.{extension}"

        task = M3U8Task(
            name=name,
            url=url,
            fileSize=1,
            outputFolder=outputFolder,
            manifestType=manifestType,
            isLive=isLive,
            streams=streams,
        )

        stepOptions = dict(
            headers=headers,

            threadCount=m3u8Config.threadCount.value,
            retryCount=m3u8Config.retryCount.value,
            requestTimeout=m3u8Config.requestTimeout.value,
            shouldAutoSelect=m3u8Config.shouldAutoSelect.value,
            shouldConcurrentDownload=m3u8Config.shouldConcurrentDownload.value,
            shouldAppendUrlParams=m3u8Config.shouldAppendUrlParams.value,
            shouldBinaryMerge=m3u8Config.shouldBinaryMerge.value,
            shouldCheckSegmentsCount=m3u8Config.shouldCheckSegmentsCount.value,
            shouldDeleteTemp=m3u8Config.shouldDeleteTemp.value,
            customMuxAfterDone=m3u8Config.customMuxAfterDone.value,
            subtitleFormat=m3u8Config.subtitleFormat.value,
            shouldSelectAllAudioSubtitle=m3u8Config.shouldSelectAllAudioSubtitle.value,
            maxSpeed=m3u8Config.maxSpeed.value,
            speedUnit=m3u8Config.speedUnit.value,
            adKeyword=m3u8Config.adKeyword.value,
            shouldOmitDateInfo=m3u8Config.shouldOmitDateInfo.value,
            shouldKeepImageSegments=m3u8Config.shouldKeepImageSegments.value,
            decryptionEngine=m3u8Config.decryptionEngine.value,
            decryptionBinaryPath=m3u8Config.decryptionBinaryPath.value,
            shouldUseMp4RealTimeDecryption=m3u8Config.shouldUseMp4RealTimeDecryption.value,
            shouldKeepLiveSegments=m3u8Config.shouldKeepLiveSegments.value,
            shouldFixLiveVtt=m3u8Config.shouldFixLiveVtt.value,
            liveWaitTime=m3u8Config.liveWaitTime.value,
            liveTakeCount=m3u8Config.liveTakeCount.value,
        )
        task.addStep(M3U8TaskStep(stepIndex=1, **stepOptions))
        if not isLive:
            for index, (language, subtitleName) in enumerate(self._parseSubtitles(body, manifestType), start=2):
                task.addStep(M3U8SubtitleStep(stepIndex=index, language=language, name=subtitleName, **stepOptions))
        return task

    def _parseSubtitles(self, body: str, manifestType: str) -> list[tuple[str, str]]:
        """每种语言取清单中的第一路字幕，返回 (language, name)；language 缺失时以 name 区分。"""
        try:
            if manifestType == "mpd":
                mpd = MPEGDASHParser.parse(body)
                renditions = [
                    (adaptationSet.lang or "", adaptationSet.lang or "")
                    for period in mpd.periods[:1] for adaptationSet in period.adaptation_sets
                    if (adaptationSet.content_type or "").lower() == "text"
                    or (adaptationSet.mime_type or "").lower().startswith(("text/", "application/ttml"))
                ]
            else:
                renditions = [
                    (media.language or "", media.name or "")
                    for media in parsePlaylist(body).media if (media.type or "").upper() == "SUBTITLES"
                ]
        except Exception as e:
            logger.warning("枚举字幕失败: {}", repr(e))
            return []
        subtitles: dict[str, tuple[str, str]] = {}
        for language, subtitleName in renditions:
            key = language or subtitleName
            if key and key not in subtitles:
                subtitles[key] = (language, subtitleName)
        return list(subtitles.values())

    def _parseStreams(self, body: str, manifestType: str) -> list[dict]:
        try:
            if manifestType == "mpd":
                return self._mpdStreams(body)
            return self._hlsStreams(body)
        except Exception as e:
            logger.warning("枚举可选视频流失败: {}", repr(e))
            return []

    def _hlsStreams(self, body: str) -> list[dict]:
        playlist = parsePlaylist(body)
        streams = []
        for variant in playlist.playlists:
            resolution = variant.stream_info.resolution
            if not resolution:
                continue
            width, height = resolution
            streams.append({
                "width": width,
                "height": height,
                "codecs": variant.stream_info.codecs,
                "frameRate": variant.stream_info.frame_rate,
            })
        return streams

    def _mpdStreams(self, body: str) -> list[dict]:
        mpd = MPEGDASHParser.parse(body)
        if not mpd.periods:
            return []
        streams = []
        for adaptationSet in mpd.periods[0].adaptation_sets:
            for representation in adaptationSet.representations:
                if not representation.width:
                    continue
                contentType = (adaptationSet.content_type or "").lower()
                mimeType = (adaptationSet.mime_type or representation.mime_type or "").lower()
                isVideo = (
                    contentType == "video"
                    or mimeType.startswith("video")
                    or (representation.id and "video" in representation.id)
                )
                if not isVideo:
                    continue

                frameRate = None
                if representation.frame_rate:
                    text = str(representation.frame_rate)
                    if "/" in text:
                        num, den = text.split("/")
                        frameRate = int(num) / int(den) if int(den) else None
                    else:
                        frameRate = float(text)

                streams.append({
                    "width": representation.width,
                    "height": representation.height,
                    "codecs": representation.codecs,
                    "frameRate": frameRate,
                })
        return streams


class M3U8Pack(FeaturePack):
    packId = "m3u8"
    capturedLinks = N("M3U8Pack", "M3U8 / DASH 流媒体")
    parsers = [M3U8Parser]

    def taskCardClass(self, task: Task) -> type[TaskCard] | None:
        if getattr(task, "isLive", False):
            from .cards import M3U8LiveTaskCard
            return M3U8LiveTaskCard
        from .cards import M3U8TaskCard
        return M3U8TaskCard

    def draftCardClass(self, task: Task) -> type[DraftCard] | None:
        from .cards import M3U8DraftCard
        return M3U8DraftCard

    def __init__(self, services: PackServices) -> None:
        self.config = m3u8Config
        super().__init__(services)

    def runtimes(self) -> list[BinaryRuntime]:
        return [m3u8Runtime]

    def optionCards(self, task: Task, parent: QWidget | None = None) -> list[OptionCard]:
        from app.view.components.option_cards import HeadersEditCard, OutputFolderCard
        from .cards import StreamSelectCard, RecordLimitCard, DecryptionKeyCard, MuxImportCard
        from .task import M3U8TaskStep

        step = task.steps[0] if task.steps else None
        if not isinstance(step, M3U8TaskStep):
            return []

        cards: list[OptionCard] = [
            OutputFolderCard(parent, initial=task.outputFolder),
            HeadersEditCard(parent, initial=step.headers),
        ]
        if len(task.streams) > 1:
            cards.append(StreamSelectCard(parent, streams=task.streams, initial=step.selectVideo))
        if task.isLive:
            cards.append(RecordLimitCard(parent, initial=step.recordLimit))
        cards.append(DecryptionKeyCard(parent, keys=step.decryptionKeys, keyTextFile=step.decryptionKeyFile))
        cards.append(MuxImportCard(parent, initial=step.muxImports))
        return cards

    def editCards(self, task: Task, parent: QWidget | None = None) -> list[OptionCard]:
        from app.view.components.option_cards import HeadersEditCard, OutputFolderCard
        from .cards import RecordLimitCard, DecryptionKeyCard, MuxImportCard, SubtitleCard
        from .task import M3U8TaskStep, subtitleChoices

        step = task.steps[0] if task.steps else None
        if not isinstance(step, M3U8TaskStep):
            return []

        cards: list[OptionCard] = [
            OutputFolderCard(parent, initial=task.outputFolder),
            HeadersEditCard(parent, initial=step.headers),
        ]
        if task.isLive:
            cards.append(RecordLimitCard(parent, initial=step.recordLimit))
        if subtitleChoices(task):
            cards.append(SubtitleCard(parent, task=task))
        cards.append(DecryptionKeyCard(parent, keys=step.decryptionKeys, keyTextFile=step.decryptionKeyFile))
        cards.append(MuxImportCard(parent, initial=step.muxImports))
        return cards

    def fileTypes(self) -> list[FileType]:
        return [
            FileType(
                extensions=(".m3u8", ".m3u"),
                displayName=N("M3U8Pack", "M3U8 播放列表"),
                mimeType="application/vnd.apple.mpegurl",
                icon="m3u8",
            ),
            FileType(
                extensions=(".mpd",),
                displayName=N("M3U8Pack", "DASH 清单"),
                mimeType="application/dash+xml",
                icon="m3u8",
            ),
        ]
