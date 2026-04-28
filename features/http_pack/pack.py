# pyright: reportImportCycles=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportArgumentType=false, reportCallIssue=false, reportOptionalIterable=false, reportAny=false, reportImplicitOverride=false

from __future__ import annotations

import re
from collections.abc import Mapping
from mimetypes import guess_extension
from pathlib import Path
from time import time_ns
from urllib.parse import parse_qs
from urllib.parse import unquote
from urllib.parse import urlparse

import niquests
from loguru import logger

from app.feature_pack.api import SpecialFileSize
from app.feature_pack.api import FeaturePack
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskInput
from app.supports.config import DEFAULT_HEADERS
from app.supports.config import cfg
from app.supports.utils import sanitizeFilename
from app.supports.utils import splitRequestHeadersAndCookies

from .task import HttpTask


def _copyHeaders(
    headers: Mapping[str, str] | None,
    *,
    useDefaults: bool = False,
) -> dict[str, str]:
    if headers:
        return {str(key): str(value) for key, value in headers.items()}
    if useDefaults:
        return DEFAULT_HEADERS.copy()
    return {}


def _copyProxies(
    proxies: Mapping[str, str] | None,
) -> dict[str, str] | None:
    if proxies is None:
        return None
    return {str(key): str(value) for key, value in proxies.items()}


def _normalizeChunks(value: int | None) -> int:
    if value is None or isinstance(value, bool):
        return max(1, int(cfg.preBlockNum.value))
    return max(1, int(value))


def _normalizeSize(value: int | None) -> int:
    if value is None or isinstance(value, bool):
        return SpecialFileSize.UNKNOWN
    normalized = int(value)
    if normalized <= 0:
        return SpecialFileSize.UNKNOWN
    return normalized


def _normalizeConfig(config: TaskConfig) -> TaskConfig:
    rawName = str(config.name).strip()
    return TaskConfig(
        source=str(config.source).strip(),
        folder=Path(config.folder),
        name=sanitizeFilename(rawName) if rawName else "",
        headers=_copyHeaders(config.headers, useDefaults=True),
        proxies=_copyProxies(config.proxies),
        chunks=_normalizeChunks(config.chunks),
    )


def _parsePositiveContentLength(headers: Mapping[str, str]) -> int:
    value = str(headers.get("content-length", "")).strip()
    if not value:
        return SpecialFileSize.UNKNOWN

    try:
        length = int(value)
    except ValueError:
        return SpecialFileSize.UNKNOWN

    return length if length > 0 else SpecialFileSize.UNKNOWN


def _parseContentRangeTotal(headers: Mapping[str, str]) -> int:
    contentRange = str(headers.get("content-range", "")).strip()
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


def _buildRangeProbeHeaders(headers: Mapping[str, str], rangeValue: str) -> dict[str, str]:
    requestHeaders = dict(headers)
    requestHeaders["range"] = rangeValue
    requestHeaders["accept-encoding"] = "identity"
    return requestHeaders


async def _requestProbe(
    client: niquests.AsyncSession,
    url: str,
    headers: Mapping[str, str],
    proxies: Mapping[str, str] | None,
) -> tuple[int, dict[str, str], str]:
    requestHeaders, requestCookies = splitRequestHeadersAndCookies(headers)
    response = await client.get(
        url,
        headers=requestHeaders,
        cookies=requestCookies,
        proxies=proxies,
        verify=cfg.SSLVerify.value,
        allow_redirects=True,
        stream=True,
    )
    try:
        if response.status_code not in {200, 206, 416}:
            response.raise_for_status()
        return (
            response.status_code,
            {str(key).lower(): str(value) for key, value in response.headers.items()},
            str(response.url),
        )
    finally:
        await response.close()


async def _probeDownloadInfo(
    url: str,
    headers: Mapping[str, str] | None,
    proxies: Mapping[str, str] | None,
) -> tuple[int, bool, str, dict[str, str]]:
    client = niquests.AsyncSession(happy_eyeballs=True)
    client.trust_env = False
    normalizedHeaders = _copyHeaders(headers, useDefaults=True)
    normalizedProxies = _copyProxies(proxies)

    try:
        statusCode, responseHeaders, finalUrl = await _requestProbe(
            client,
            url,
            _buildRangeProbeHeaders(normalizedHeaders, "bytes=1-1"),
            normalizedProxies,
        )

        fileSize = _parseContentRangeTotal(responseHeaders)
        supportsRange = statusCode == 206 and "content-range" in responseHeaders
        if supportsRange:
            logger.info(
                "HTTP Range 探测成功 {} supportsRange={} fileSize={}",
                url,
                supportsRange,
                fileSize,
            )
            return fileSize, True, finalUrl, responseHeaders

        fileSize = _parsePositiveContentLength(responseHeaders)
        if statusCode == 200:
            fallbackStatus, fallbackHeaders, _, = await _requestProbe(
                client,
                url,
                _buildRangeProbeHeaders(normalizedHeaders, "bytes=0-0"),
                normalizedProxies,
            )
            fallbackSize = _parseContentRangeTotal(fallbackHeaders)
            if fallbackStatus == 206 and "content-range" in fallbackHeaders:
                logger.info(
                    "HTTP 回退 Range 探测成功 {} fileSize={}",
                    url,
                    fallbackSize,
                )
                return fallbackSize, True, finalUrl, fallbackHeaders

            if fileSize == SpecialFileSize.UNKNOWN:
                fileSize = _parsePositiveContentLength(fallbackHeaders)
                if fileSize == SpecialFileSize.UNKNOWN and fallbackStatus == 416:
                    fileSize = _parseContentRangeTotal(fallbackHeaders)

        logger.info(
            "HTTP Range 探测未命中 {} supportsRange={} fileSize={}",
            url,
            False,
            fileSize,
        )
        return fileSize, False, finalUrl, responseHeaders
    finally:
        await client.close()


def _extensionFromContentType(headers: Mapping[str, str]) -> str:
    contentType = str(headers.get("content-type", "")).split(";", 1)[0].lower().strip()
    extension = guess_extension(contentType) or ""
    return extension.lstrip(".")


def _extractFileName(url: str, headers: Mapping[str, str]) -> str:
    fileName = ""

    contentDisposition = str(headers.get("content-disposition", ""))
    if contentDisposition:
        encodedNameMatch = re.search(
            r"filename\*\s*=\s*([^;]+)",
            contentDisposition,
            re.IGNORECASE,
        )
        if encodedNameMatch:
            encodedName = encodedNameMatch.group(1).strip().strip("\"' ")
            parts = encodedName.split("'", 2)
            if len(parts) == 3:
                encoding, _, encodedText = parts
                fileName = unquote(encodedText, encoding=encoding or "utf-8")
            elif encodedName:
                fileName = unquote(encodedName)

        if not fileName:
            fileNameMatch = re.search(
                r"filename\s*=\s*[\"']?([^\"';]+)[\"']?",
                contentDisposition,
                re.IGNORECASE,
            )
            if fileNameMatch:
                fileName = unquote(fileNameMatch.group(1)).strip("\"' ")

    if not fileName and "content-location" in headers:
        fileName = unquote(urlparse(str(headers["content-location"])).path.split("/")[-1])

    if not fileName:
        parsedUrl = urlparse(url)
        responseContentDisposition = parse_qs(parsedUrl.query).get(
            "response-content-disposition",
            [""],
        )[0]
        if "filename=" in responseContentDisposition.lower():
            match = re.search(
                r"filename\s*=\s*[\"']?([^\"';]+)[\"']?",
                responseContentDisposition,
                re.IGNORECASE,
            )
            if match:
                fileName = unquote(match.group(1)).strip("\"' ")

    if not fileName:
        path = urlparse(url).path.split(";", 1)[0]
        fileName = unquote(path.split("/")[-1])

    extension = _extensionFromContentType(headers)
    if not fileName:
        suffix = f".{extension}" if extension else ".bin"
        fileName = f"file_{int(time_ns())}{suffix}"
    elif "." not in Path(fileName).name and extension:
        fileName = f"{fileName}.{extension}"

    return sanitizeFilename(fileName, fallback=f"file_{int(time_ns())}.bin")


async def _buildTask(
    config: TaskConfig,
    *,
    preferredSize: int = SpecialFileSize.UNKNOWN,
    preferredSupportsRange: bool | None = None,
) -> HttpTask:
    normalizedConfig = _normalizeConfig(config)
    probedSize, probedSupportsRange, finalUrl, responseHeaders = await _probeDownloadInfo(
        normalizedConfig.source,
        normalizedConfig.headers,
        normalizedConfig.proxies,
    )

    fileSize = preferredSize if preferredSize > 0 else probedSize
    supportsRange = (
        preferredSupportsRange
        if preferredSupportsRange is not None
        else probedSupportsRange
    )
    resolvedName = normalizedConfig.name or _extractFileName(finalUrl, responseHeaders)
    resolvedConfig = TaskConfig(
        source=normalizedConfig.source,
        folder=normalizedConfig.folder,
        name=sanitizeFilename(resolvedName, fallback="download.bin"),
        headers=normalizedConfig.headers,
        proxies=normalizedConfig.proxies,
        chunks=normalizedConfig.chunks,
    )

    return HttpTask(
        config=resolvedConfig,
        totalBytes=fileSize,
        supportsRange=supportsRange,
    )


class HttpPack(FeaturePack):
    def accepts(self, source: str) -> bool:
        return urlparse(source).scheme.lower() in {"http", "https"}

    async def createTask(self, data: TaskInput) -> Task | None:
        normalizedConfig = _normalizeConfig(data.config)
        if not self.accepts(normalizedConfig.source):
            return None

        return await _buildTask(
            normalizedConfig,
            preferredSize=_normalizeSize(data.size),
        )

    def owns(self, task: Task) -> bool:
        return isinstance(task, HttpTask) and task.packId == self.manifest.id


__all__ = [
    "HttpPack",
    "_buildRangeProbeHeaders",
    "_extractFileName",
    "_parseContentRangeTotal",
    "_parsePositiveContentLength",
    "_probeDownloadInfo",
]
