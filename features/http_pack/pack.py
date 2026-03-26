import re
from email.message import Message
from mimetypes import guess_extension
from pathlib import Path
from time import time_ns
from urllib.parse import unquote, urlparse, parse_qs

import niquests
from loguru import logger

from app.bases.interfaces import FeaturePack
from app.bases.models import Task, SpecialFileSize
from app.supports.config import cfg, DEFAULT_HEADERS
from app.supports.utils import getProxies, sanitizeFilename, splitRequestHeadersAndCookies
from app.view.components.cards import UniversalTaskCard, UniversalResultCard
from .task import HttpTask, HttpTaskStage


def _createTaskFromPayload(payload: dict) -> HttpTask | None:
    fileName = sanitizeFilename(str(payload.get("filename") or "").strip(), fallback="")
    if not fileName:
        return None

    url = str(payload.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return None

    rawSize = payload.get("size")
    fileSize = rawSize if isinstance(rawSize, int) and rawSize > 0 else SpecialFileSize.UNKNOWN
    headers = payload.get("headers", DEFAULT_HEADERS)
    proxies = payload.get("proxies", getProxies())
    blockNum = payload.get("preBlockNum", cfg.preBlockNum.value)
    path = payload.get("path", Path(cfg.downloadFolder.value))
    supportsRange = bool(payload.get("supportsRange"))
    resolvePath = str(path / fileName)

    task = HttpTask(
        title=fileName,
        url=url,
        fileSize=fileSize,
        headers=headers,
        proxies=proxies,
        blockNum=blockNum,
        supportsRange=supportsRange,
        path=path,
    )
    task.addStage(
        HttpTaskStage(
            stageIndex=1,
            url=url,
            fileSize=fileSize,
            headers=headers,
            proxies=proxies,
            resolvePath=resolvePath,
            blockNum=blockNum,
            supportsRange=supportsRange,
        )
    )
    return task


def _parsePositiveContentLength(headers: dict[str, str]) -> int:
    value = headers.get("content-length", "").strip()
    if not value:
        return SpecialFileSize.UNKNOWN

    try:
        length = int(value)
    except ValueError:
        return SpecialFileSize.UNKNOWN

    return length if length > 0 else SpecialFileSize.UNKNOWN


def _parseContentRangeTotal(headers: dict[str, str]) -> int:
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


def _buildRangeProbeHeaders(headers: dict, rangeValue: str) -> dict:
    requestHeaders = headers.copy()
    requestHeaders["range"] = rangeValue
    requestHeaders["accept-encoding"] = "identity"
    return requestHeaders


async def _requestProbe(client: niquests.AsyncSession, url: str, headers: dict, proxies: dict) -> tuple[int, dict[str, str], str]:
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
        return response.status_code, {k.lower(): v for k, v in response.headers.items()}, str(response.url)
    finally:
        await response.close()


async def _probeDownloadInfo(url: str, headers: dict, proxies: dict) -> tuple[int, bool, str, dict[str, str]]:
    client = niquests.AsyncSession(happy_eyeballs=True)
    client.trust_env = False

    try:
        statusCode, responseHeaders, finalUrl = await _requestProbe(
            client,
            url,
            _buildRangeProbeHeaders(headers, "bytes=1-1"),
            proxies,
        )

        fileSize = _parseContentRangeTotal(responseHeaders)
        supportsRange = statusCode == 206 and "content-range" in responseHeaders

        if supportsRange:
            if fileSize == SpecialFileSize.UNKNOWN:
                logger.info(f"偏移 Range 探测成功, content-range: {responseHeaders.get('content-range', '')}, fileSize: unknown")
            else:
                logger.info(
                    f"偏移 Range 探测成功, content-range: {responseHeaders.get('content-range', '')}, fileSize: {fileSize}"
                )
            return fileSize, True, finalUrl, responseHeaders

        fileSize = _parsePositiveContentLength(responseHeaders)

        if statusCode == 200:
            logger.info(
                f"偏移 Range 探测返回 200, content-length: {responseHeaders.get('content-length', '')}"
            )
            if fileSize in {SpecialFileSize.UNKNOWN, 1}:
                fallbackStatus, fallbackHeaders, _, = await _requestProbe(
                    client,
                    url,
                    _buildRangeProbeHeaders(headers, "bytes=0-0"),  # bytes=0- 和 bytes=0-0 哪个更好存疑
                    proxies,
                )
                fallbackSize = _parseContentRangeTotal(fallbackHeaders)
                if fallbackStatus == 206 and "content-range" in fallbackHeaders:
                    if fallbackSize == SpecialFileSize.UNKNOWN:
                        logger.info(f"回退 Range 探测成功, content-range: {fallbackHeaders.get('content-range', '')}, fileSize: unknown")
                    else:
                        logger.info(
                            f"回退 Range 探测成功, content-range: {fallbackHeaders.get('content-range', '')}, fileSize: {fallbackSize}"
                        )
                    return fallbackSize, True, finalUrl, fallbackHeaders

                if fileSize == SpecialFileSize.UNKNOWN:
                    fileSize = _parsePositiveContentLength(fallbackHeaders)
                    if fileSize == SpecialFileSize.UNKNOWN and fallbackStatus == 416:
                        fileSize = _parseContentRangeTotal(fallbackHeaders)

        if fileSize == SpecialFileSize.UNKNOWN:
            logger.info("文件大小未知，按不支持断点续传处理")
        else:
            logger.info(f"文件大小已知但未探测到 Range 支持, fileSize: {fileSize}")

        return fileSize, False, finalUrl, responseHeaders
    finally:
        await client.close()


def _extractFileName(url: str, headers: dict) -> str:

    fileName = ""

    # Content-Disposition (RFC 6266/5987)
    cd = headers.get("content-disposition", "")
    if cd:
        msg = Message()
        msg['Content-Disposition'] = cd
        params = msg.get_params(header='Content-Disposition')
        paramDict = {k.lower(): v for k, v in params if isinstance(v, str)}

        if "filename*" in paramDict:
            val = paramDict["filename*"]  # charset'lang'encoded_text
            if "'" in val:
                parts = val.split("'", 2)
                if len(parts) == 3:
                    encoding, _, encodedText = parts
                    fileName = unquote(encodedText, encoding=encoding or "utf-8")
                    logger.info(f"方案 A 获取文件名: {fileName}")

        if not fileName and "filename" in paramDict:
            fileName = paramDict["filename"].strip("\"' ")
            logger.info(f"方案 B 获取文件名: {fileName}")

    # Content-Location (RFC 7231)
    if not fileName and "content-location" in headers:
        cl = headers["content-location"]
        fileName = unquote(urlparse(cl).path.split("/")[-1])
        logger.info(f"方案 C 获取文件名: {fileName}")

    # OSS/S3 覆盖响应头
    if not fileName:
        parsedUrl = urlparse(url)
        queryParams = parse_qs(parsedUrl.query)
        rcd = queryParams.get("response-content-disposition", [""])[0]
        if "filename=" in rcd.lower():
            match = re.search(r'filename\s*=\s*["\']?([^"\';]+)["\']?', rcd, re.IGNORECASE)
            if match:
                fileName = unquote(match.group(1)).strip("\"' ")
                logger.info(f"方案 D 获取文件名: {fileName}")

    # URL 路径解析
    if not fileName:
        path = urlparse(url).path
        if path and "/" in path:
            # 移除路径中的参数 (如 ;jsessionid=...)
            cleanPath = path.split(";")[0]
            fileName = unquote(cleanPath.split("/")[-1])
            logger.info(f"方案 E 获取文件名: {fileName}")

    # 兜底处理
    if not fileName:
        contentType = headers.get("content-type", "").split(";")[0].lower().strip()
        standardExt = guess_extension(contentType) or ""
        timestamp = int(time_ns())
        fileName = f"file_{timestamp}.{standardExt}"
        logger.info(f"方案 F 获取文件名: {fileName}")
    else:
        if "." not in fileName:
            contentType = headers.get("content-type", "").split(";")[0].lower().strip()
            standardExt = guess_extension(contentType) or ""
            fileName = f"{fileName}.{standardExt}"

    return sanitizeFilename(fileName, fallback=f"file_{int(time_ns())}")

async def parse(payload: dict) -> HttpTask:
    url: str = payload['url']
    headers: dict = payload.get('headers', DEFAULT_HEADERS)
    proxies: dict = payload.get('proxies', getProxies())
    blockNum: int = payload.get('preBlockNum', cfg.preBlockNum.value)
    path: Path = payload.get('path', Path(cfg.downloadFolder.value))
    fileSize, supportsRange, finalUrl, head = await _probeDownloadInfo(url, headers, proxies)

    # 获取文件名
    fileName = _extractFileName(finalUrl, head)

    resolvePath = str(path / fileName)

    task = HttpTask(
        title=fileName,
        url=url,
        fileSize=fileSize,
        headers=headers,
        proxies=proxies,
        blockNum=blockNum,
        supportsRange=supportsRange,
        path=path
    )
    stage = HttpTaskStage(
        stageIndex=1,
        url=url,
        fileSize=fileSize,
        headers=headers,
        proxies=proxies,
        resolvePath=resolvePath,
        blockNum=blockNum,
        supportsRange=supportsRange,
    )
    task.addStage(stage)
    return task


class HttpPack(FeaturePack):
    priority = 100
    taskType = HttpTask

    async def createTaskFromPayload(self, payload: dict) -> Task | None:
        return _createTaskFromPayload(payload)

    def canHandle(self, url: str) -> bool:
        return urlparse(url).scheme.lower() in {"http", "https"}

    async def parse(self, payload: dict) -> Task:
        return await parse(payload)

    def createTaskCard(self, task: Task, parent=None):
        if isinstance(task, HttpTask):
            return UniversalTaskCard(task, parent)
        return None

    def createResultCard(self, task: Task, parent=None):
        if isinstance(task, HttpTask):
            return UniversalResultCard(task, parent)
        return None
