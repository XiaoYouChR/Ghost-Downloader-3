from __future__ import annotations

import re
from dataclasses import replace
from email.message import Message
from email.utils import collapse_rfc2231_value
from mimetypes import guess_extension
from time import time_ns
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlparse, parse_qs

from loguru import logger

from app.client import buildClient, toEmulation
from app.config.cfg import cfg
from app.i18n import N
from app.models.pack import FeaturePack, TaskParser
from app.models.task import (
    RemoteFile, Task, TaskOptions, ResourceTaskOptions, SpecialFileSize,
)
from app.platform.filesystem import toSafeFilename
from .task import HttpTask, HttpTaskStep

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
    from app.view.cards.task_cards import TaskCard
    from app.view.components.option_cards import OptionCard


DOWNLOADABLE_EXTENSIONS = frozenset({
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".ts", ".m2ts",
    ".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a", ".wma", ".opus",
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".zst",
    ".exe", ".msi", ".dmg", ".deb", ".rpm", ".appimage", ".pkg",
    ".iso", ".img",
    ".pdf", ".epub",
    ".apk", ".ipa",
})


async def probe(options: TaskOptions) -> RemoteFile:
    url = options.url
    headers = dict(options.headers)
    userAgent = options.userAgent
    name = ""
    emulation = toEmulation(
        options.clientProfile or cfg.clientProfile.value,
        options.sourceUserAgent,
    )
    client = buildClient(emulation=emulation, userAgent=userAgent or None, timeout=30)

    def rangeTotal(h: dict) -> int:
        cr = h.get("content-range", "")
        if not cr or "/" not in cr:
            return SpecialFileSize.UNKNOWN
        _, _, total = cr.rpartition("/")
        if not total or total == "*":
            return SpecialFileSize.UNKNOWN
        try:
            size = int(total)
        except ValueError:
            return SpecialFileSize.UNKNOWN
        return size if size > 0 else SpecialFileSize.UNKNOWN

    def bodyLength(h: dict) -> int:
        val = h.get("content-length", "").strip()
        if not val:
            return SpecialFileSize.UNKNOWN
        try:
            length = int(val)
        except ValueError:
            return SpecialFileSize.UNKNOWN
        return length if length > 0 else SpecialFileSize.UNKNOWN

    async def request(rangeValue: str = "") -> tuple[int, dict[str, str], str]:
        probeHeaders = dict(headers)
        probeHeaders["accept-encoding"] = "identity"
        if rangeValue:
            probeHeaders["range"] = rangeValue
        response = await client.get(url, headers=probeHeaders)
        try:
            status = response.status.as_int()
            if status not in {200, 206, 416}:
                response.raise_for_status()
            return (
                status,
                {bytes(k).decode().lower(): bytes(v).decode() for k, v in response.headers},
                str(response.url),
            )
        finally:
            response.close()

    try:
        statusCode, responseHeaders, finalUrl = await request("bytes=1-1")

        fileSize = rangeTotal(responseHeaders)
        canUseRangeRequests = statusCode == 206 and "content-range" in responseHeaders

        if canUseRangeRequests:
            logger.debug(
                "偏移 Range 探测成功, content-range: {}, fileSize: {}",
                responseHeaders.get("content-range", ""), fileSize,
            )
        else:
            fileSize = bodyLength(responseHeaders)
            logger.debug(
                "偏移 Range 探测返回 {}, content-length: {}",
                statusCode, responseHeaders.get("content-length", ""),
            )

            if statusCode == 200 and fileSize in {SpecialFileSize.UNKNOWN, 1}:
                fbStatus, fbHeaders, _ = await request("bytes=0-0")
                fbSize = rangeTotal(fbHeaders)
                if fbStatus == 206 and "content-range" in fbHeaders:
                    logger.debug(
                        "回退 Range 探测成功, content-range: {}, fileSize: {}",
                        fbHeaders.get("content-range", ""), fbSize,
                    )
                    fileSize = fbSize
                    canUseRangeRequests = True
                else:
                    if fileSize == SpecialFileSize.UNKNOWN:
                        fileSize = bodyLength(fbHeaders)
                        if fileSize == SpecialFileSize.UNKNOWN and fbStatus == 416:
                            fileSize = rangeTotal(fbHeaders)

        cd = responseHeaders.get("content-disposition", "")
        if cd:
            msg = Message()
            msg["Content-Disposition"] = cd
            params = msg.get_params(header="Content-Disposition")
            paramDict = {k.lower(): v for k, v in params}
            name = unquote(collapse_rfc2231_value(
                paramDict.get("filename") or paramDict.get("filename*") or ""
            )).strip("\"' ")

        if not name and "content-location" in responseHeaders:
            cl = responseHeaders["content-location"]
            name = unquote(urlparse(cl).path.split("/")[-1])

        if not name:
            queryParams = parse_qs(urlparse(finalUrl).query)
            rcd = queryParams.get("response-content-disposition", [""])[0]
            if "filename=" in rcd.lower():
                m = re.search(r'filename\s*=\s*["\']?([^"\';]+)["\']?', rcd, re.IGNORECASE)
                if m:
                    name = unquote(m.group(1)).strip("\"' ")

        if not name:
            path = urlparse(finalUrl).path
            if path and "/" in path:
                cleanPath = path.split(";")[0]
                name = unquote(cleanPath.split("/")[-1])

        contentType = responseHeaders.get("content-type", "").split(";", 1)[0].lower().strip()
        standardExt = guess_extension(contentType) if contentType else ""
        standardExt = standardExt or ""

        if not name:
            name = f"file_{time_ns()}{standardExt}"
        elif "." not in name and standardExt:
            name = f"{name}{standardExt}"

        name = toSafeFilename(name, fallback=f"file_{time_ns()}")

        lastModified = responseHeaders.get("last-modified", "")
    finally:
        client.close()

    return RemoteFile(
        name=name,
        fileSize=fileSize,
        canUseRangeRequests=canUseRangeRequests,
        lastModified=lastModified,
        contentType=contentType,
    )


def buildStep[S: HttpTaskStep](
    stepType: type[S],
    stepIndex: int,
    url: str,
    options: TaskOptions,
    file: RemoteFile | None = None,
    **kwargs: Any,
) -> S:
    fields = {
        "stepIndex": stepIndex,
        "url": url,
        "fileSize": file.fileSize if file else 0,
        "headers": dict(options.headers),
        "clientProfile": options.clientProfile,
        "userAgent": options.userAgent,
        "subworkerCount": options.subworkerCount,
        "canUseRangeRequests": file.canUseRangeRequests if file else False,
        "lastModified": file.lastModified if file else "",
    }
    return stepType(**{**fields, **kwargs})


def buildTask(options: TaskOptions) -> HttpTask:
    name = options.file.name
    if isinstance(options, ResourceTaskOptions) and options.name:
        name = toSafeFilename(options.name, fallback=f"file_{time_ns()}")
    task = HttpTask(
        name=name,
        url=options.url,
        fileSize=options.file.fileSize,
        outputFolder=options.outputFolder,
    )
    task.addStep(buildStep(HttpTaskStep, 1, options.url, options, options.file))
    return task


class HttpParser(TaskParser):
    priority = 100

    def match(self, options: TaskOptions) -> bool:
        return urlparse(options.url).scheme.lower() in {"http", "https"}

    def matchPassive(self, options: TaskOptions) -> bool:
        parsed = urlparse(options.url)
        if parsed.scheme.lower() not in {"http", "https"}:
            return False
        path = parsed.path.lower()
        return any(path.endswith(ext) for ext in DOWNLOADABLE_EXTENSIONS)

    async def parse(self, options: TaskOptions) -> Task:
        if options.isProbed:
            return buildTask(options)
        if isinstance(options, ResourceTaskOptions) and options.name and options.size > 0:
            file = RemoteFile(name=options.name, fileSize=options.size, canUseRangeRequests=options.canUseRangeRequests)
            return await self.pack.parse(replace(options, file=file))
        return await self.pack.parse(replace(options, file=await probe(options)))


def buildOptionCards(task: Task, parent: QWidget | None = None) -> list[OptionCard]:
    from app.view.components.option_cards import (
        ClientProfileCard, HeadersEditCard, OutputFolderCard, SubworkerCountCard,
    )
    step = task.steps[0] if task.steps else None
    if not isinstance(step, HttpTaskStep):
        return []
    return [
        OutputFolderCard(parent, initial=task.outputFolder),
        HeadersEditCard(parent, initial=step.headers),
        ClientProfileCard(parent, initial=step.clientProfile, initialUserAgent=step.userAgent),
        SubworkerCountCard(parent, initial=step.subworkerCount),
    ]


def buildEditCards(task: Task, parent: QWidget | None = None) -> list[OptionCard]:
    from app.view.components.option_cards import UrlEditCard
    return [
        UrlEditCard(parent, initial=task.url),
        *buildOptionCards(task, parent),
    ]


class HttpPack(FeaturePack):
    packId = "http"
    capturedLinks = N("HttpPack", "文件直链（视频、音频、压缩包、安装包、镜像、文档）")
    parsers = [HttpParser]

    def taskCardClass(self, task: Task) -> type[TaskCard] | None:
        from .cards import HttpTaskCard
        return HttpTaskCard

    def optionCards(self, task: Task, parent: QWidget | None = None) -> list[OptionCard]:
        return buildOptionCards(task, parent)

    def editCards(self, task: Task, parent: QWidget | None = None) -> list[OptionCard]:
        return buildEditCards(task, parent)

