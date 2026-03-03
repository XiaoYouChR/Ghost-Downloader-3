import re
from email.message import Message
from enum import Enum
from mimetypes import guess_extension
from time import time_ns
from urllib.parse import unquote, urlparse, parse_qs

from loguru import logger

from app.bases.interfaces import FeaturePack
from .cards import HttpTaskCard, HttpResultCard

import niquests

from .const import SpecialFileSize
from .task import HttpTask


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

    fileName = re.sub(r'[\x00-\x1f\\/:*?"<>|]', "_", fileName)
    if len(fileName) > 200:
        base, ext = (fileName.rsplit(".", 1) if "." in fileName else (fileName, ""))
        fileName = base[:190] + ("." + ext)

    return fileName.strip()

async def parse(payload: dict) -> HttpTask:
    url: str = payload['url']
    headers: dict = payload['headers']
    proxies: dict = payload['proxies']

    requestHeaders = headers.copy()
    requestHeaders["range"] = "bytes=0-"    # 小写好像更好来着?

    # TODO verify config
    client = niquests.AsyncSession(happy_eyeballs=True)
    client.trust_env = False
    response = await client.get(url, headers=requestHeaders, proxies=proxies, verify=False, allow_redirects=True, stream=True)
    await client.close()
    response.raise_for_status()

    head = response.headers
    head = {k.lower(): v for k, v in head.items()}

    # 获取文件大小, 判断是否可以分块下载
    # 状态码为206才是范围请求，200表示服务器拒绝了范围请求同时将发送整个文件
    if response.status_code == 206 and "content-range" in head:
        # https://developer.mozilla.org/zh-CN/docs/Web/HTTP/Reference/Headers/Content-Range
        _left, _char, right = head["content-range"].rpartition("/")

        if right != "*":
            fileSize = int(right)
            logger.info(
                f"content-range: {head['content-range']}, fileSize: {fileSize}, content-length: {head['content-length']}"
            )

        elif "content-length" in head:
            fileSize = int(head["content-length"])

        else:
            fileSize = SpecialFileSize.UNKNOWN
            logger.info("文件似乎支持续传，但无法获取文件大小")
    else:
        fileSize = SpecialFileSize.NOT_SUPPORTED
        logger.info("文件不支持续传")

    await response.close()

    # 获取文件名
    fileName = _extractFileName(response.url, head)    # 这里取重定向之前的 URL 目的是更好的获取

    task = HttpTask(title=fileName, url=url, fileSize=fileSize, headers=headers)
    return task
