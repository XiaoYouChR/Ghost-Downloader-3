import re
from email.message import Message
from email.utils import collapse_rfc2231_value
from mimetypes import guess_extension
from pathlib import Path
from time import time_ns
from urllib.parse import unquote, urlparse, parse_qs

from loguru import logger

from app.bases.interfaces import FeaturePack
from app.bases.models import Task, SpecialFileSize
from app.supports.config import cfg, defaultHeaders
from app.supports.utils import (
    buildClient,
    getProxies,
    headerDict,
    stripEmulationHeaders,
    toEmulation,
    toRequestHeaders,
    toSafeFilename,
    userAgent,
)
from .task import HttpTask, HttpTaskStage


def _contentLength(headers: dict[str, str]) -> int:
    value = headers.get("content-length", "").strip()
    if not value:
        return SpecialFileSize.UNKNOWN

    try:
        length = int(value)
    except ValueError:
        return SpecialFileSize.UNKNOWN

    return length if length > 0 else SpecialFileSize.UNKNOWN


def _rangeSize(headers: dict[str, str]) -> int:
    contentRange = headers.get("content-range", "").strip()
    if not contentRange or "/" not in contentRange:
        return SpecialFileSize.UNKNOWN

    _, _, total = contentRange.rpartition("/")
    if not total or total == "*":
        return SpecialFileSize.UNKNOWN

    try:
        size = int(total)
    except ValueError:
        return SpecialFileSize.UNKNOWN

    return size if size > 0 else SpecialFileSize.UNKNOWN



async def _sendProbe(client, url: str, headers: dict) -> tuple[int, dict[str, str], str]:
    response = await client.get(url, headers=headers)
    try:
        status = response.status.as_int()
        if status not in {200, 206, 416}:
            response.raise_for_status()
        return status, headerDict(response.headers), str(response.url)
    finally:
        await response.close()


async def _probe(url: str, headers: dict, proxies: dict, clientProfile: str = "", sourceUa: str | None = None) -> tuple[int, bool, str, dict[str, str]]:
    emulation = toEmulation(clientProfile, sourceUa)
    probeHeaders = toRequestHeaders(headers, emulation)
    client = buildClient(proxies, emulation=emulation)
    try:
        statusCode, responseHeaders, finalUrl = await _sendProbe(
            client,
            url,
            {**probeHeaders, "range": "bytes=1-1", "accept-encoding": "identity"},
        )

        fileSize = _rangeSize(responseHeaders)
        supportsRange = statusCode == 206 and "content-range" in responseHeaders

        if supportsRange:
            logger.info("偏移 Range 探测成功, content-range: {}, fileSize: {}",
                        responseHeaders.get("content-range", ""), fileSize)
            return fileSize, True, finalUrl, responseHeaders

        fileSize = _contentLength(responseHeaders)

        if statusCode == 200:
            logger.info("偏移 Range 探测返回 200, content-length: {}",
                        responseHeaders.get("content-length", ""))
            if fileSize in {SpecialFileSize.UNKNOWN, 1}:
                # bytes=0- 和 bytes=0-0 哪个更好存疑
                fallbackStatus, fallbackHeaders, _ = await _sendProbe(
                    client,
                    url,
                    {**probeHeaders, "range": "bytes=0-0", "accept-encoding": "identity"},
                )
                fallbackSize = _rangeSize(fallbackHeaders)
                if fallbackStatus == 206 and "content-range" in fallbackHeaders:
                    logger.info("回退 Range 探测成功, content-range: {}, fileSize: {}",
                                fallbackHeaders.get("content-range", ""), fallbackSize)
                    return fallbackSize, True, finalUrl, fallbackHeaders

                if fileSize == SpecialFileSize.UNKNOWN:
                    fileSize = _contentLength(fallbackHeaders)
                    if fileSize == SpecialFileSize.UNKNOWN and fallbackStatus == 416:
                        fileSize = _rangeSize(fallbackHeaders)

        if fileSize == SpecialFileSize.UNKNOWN:
            logger.info("文件大小未知，按不支持断点续传处理")
        else:
            logger.info("文件大小已知但未探测到 Range 支持, fileSize: {}", fileSize)

        return fileSize, False, finalUrl, responseHeaders
    finally:
        client.close()


def _fileName(url: str, headers: dict) -> str:
    fileName = ""

    cd = headers.get("content-disposition", "")
    if cd:
        msg = Message()
        msg["Content-Disposition"] = cd
        params = msg.get_params(header="Content-Disposition")
        paramDict = {k.lower(): v for k, v in params}
        fileName = collapse_rfc2231_value(
            paramDict.get("filename") or paramDict.get("filename*") or ""
        ).strip("\"' ")

    if not fileName and "content-location" in headers:
        cl = headers["content-location"]
        fileName = unquote(urlparse(cl).path.split("/")[-1])

    if not fileName:
        parsedUrl = urlparse(url)
        queryParams = parse_qs(parsedUrl.query)
        rcd = queryParams.get("response-content-disposition", [""])[0]
        if "filename=" in rcd.lower():
            match = re.search(r'filename\s*=\s*["\']?([^"\';]+)["\']?', rcd, re.IGNORECASE)
            if match:
                fileName = unquote(match.group(1)).strip("\"' ")

    if not fileName:
        path = urlparse(url).path
        if path and "/" in path:
            cleanPath = path.split(";")[0]
            fileName = unquote(cleanPath.split("/")[-1])

    contentType = headers.get("content-type", "").split(";", 1)[0].lower().strip()
    standardExt = guess_extension(contentType) if contentType else ""
    standardExt = standardExt or ""

    if not fileName:
        fileName = f"file_{int(time_ns())}{standardExt}"
    elif "." not in fileName and standardExt:
        fileName = f"{fileName}{standardExt}"

    return toSafeFilename(fileName, fallback=f"file_{int(time_ns())}")


class HttpPack(FeaturePack):
    packId = "http"
    priority = 100

    def matches(self, url: str) -> bool:
        return urlparse(url).scheme.lower() in {"http", "https"}

    def taskCard(self, task: Task, parent=None):
        from .cards import HttpTaskCard
        return HttpTaskCard(task, parent)

    async def parse(self, payload: dict) -> Task:
        url: str = payload["url"]
        rawHeaders: dict = payload.get("headers", defaultHeaders())
        sourceUa = userAgent(rawHeaders) or ""
        headers = stripEmulationHeaders(rawHeaders)
        proxies: dict = payload.get("proxies", getProxies())
        clientProfile: str = payload.get("clientProfile", "")
        blockNum: int = payload.get("preBlockNum", cfg.preBlockNum.value)
        path: Path = payload.get("path", Path(cfg.downloadFolder.value))

        fileName = str(payload.get("filename") or "").strip()
        fileSize = payload.get("fileSize") or SpecialFileSize.UNKNOWN
        supportsRange = payload.get("supportsRange", False)

        if not fileName:
            fileSize, supportsRange, finalUrl, head = await _probe(url, headers, proxies, clientProfile, sourceUa)
            fileName = _fileName(finalUrl, head)
        else:
            fileName = toSafeFilename(fileName, fallback=f"file_{int(time_ns())}")

        task = HttpTask(
            title=fileName,
            url=url,
            fileSize=fileSize,
            path=path,
        )
        stage = HttpTaskStage(
            stageIndex=1,
            url=url,
            fileSize=fileSize,
            headers=headers,
            proxies=proxies,
            clientProfile=clientProfile,
            sourceUserAgent=sourceUa,
            blockNum=blockNum,
            supportsRange=supportsRange,
        )
        task.addStage(stage)
        return task
