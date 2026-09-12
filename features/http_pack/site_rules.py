from __future__ import annotations

import asyncio
from dataclasses import dataclass
from email.message import Message
from email.utils import collapse_rfc2231_value, parsedate_to_datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from loguru import logger

from app.client import buildClient, toEmulation
from app.config.cfg import cfg
from app.models.task import TaskError, TaskStatus
from app.platform.filesystem import toSafeFilename
from .task import HttpTaskStep, PERMANENT_STATUS

UUPDUMP_BODY = "autodl=2&updates=1"
UUPDUMP_CONTENT_TYPE = "application/x-www-form-urlencoded"

@dataclass(frozen=True)
class HttpSiteRule:
    url: str
    headers: dict[str, str]
    subworkerCount: int
    action: str = "standard"
    requestBody: str = ""
    requestContentType: str = ""

def _is_host(host: str, domain: str) -> bool:
    host = host.lower().rstrip(".")
    domain = domain.lower().rstrip(".")
    return host == domain or host.endswith("." + domain)

def _origin(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"

def _uupdump_urls(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if not _is_host(parsed.hostname or "", "uupdump.net"):
        return None
    path = parsed.path.lower().lstrip("/")
    if path not in {"download.php", "get.php"}:
        return None
    query = f"?{parsed.query}" if parsed.query else ""
    return f"https://uupdump.net/get.php{query}", f"https://uupdump.net/download.php{query}"

def _filename_from_content_disposition(value: str | bytes | None) -> str:
    if not value:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    msg = Message()
    msg["Content-Disposition"] = value
    params = msg.get_params(header="Content-Disposition") or []
    paramDict = {str(k).lower(): v for k, v in params}
    filename = paramDict.get("filename") or paramDict.get("filename*") or ""
    if not filename:
        return ""
    filename = unquote(collapse_rfc2231_value(filename)).strip("\"' ")
    return toSafeFilename(filename, fallback="") if filename else ""

def apply_http_site_rule(url: str, headers: dict[str, str], subworkerCount: int) -> HttpSiteRule:
    uupdump = _uupdump_urls(url)
    if uupdump is not None:
        downloadUrl, referer = uupdump
        effectiveHeaders = dict(headers)
        effectiveHeaders["Referer"] = referer
        effectiveHeaders["Origin"] = _origin(referer)
        effectiveHeaders["Content-Type"] = UUPDUMP_CONTENT_TYPE
        return HttpSiteRule(downloadUrl, effectiveHeaders, 1, "uupdump_post", UUPDUMP_BODY, UUPDUMP_CONTENT_TYPE)
    parsed = urlparse(url)
    if _is_host(parsed.hostname or "", "pixeldrain.com"):
        return HttpSiteRule(url, dict(headers), 1, "single_connection")
    return HttpSiteRule(url, dict(headers), subworkerCount)

class SingleConnectionHttpTaskStep(HttpTaskStep):
    def _reassignSubworker(self) -> None:
        return
    def _autoSpeedUp(self) -> None:
        return

class UupdumpPostTaskStep(SingleConnectionHttpTaskStep):
    requestBody: str = UUPDUMP_BODY
    requestContentType: str = UUPDUMP_CONTENT_TYPE
    preferResponseFilename: bool = False

    @property
    def canPause(self) -> bool:
        return False

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        self._reportSpeed = reportSpeed
        self._waitForSpeedLimit = waitForSpeedLimit
        Path(self.outputPath).parent.mkdir(parents=True, exist_ok=True)
        headers = dict(self.headers)
        headers["Content-Type"] = self.requestContentType or UUPDUMP_CONTENT_TYPE
        headers["Accept-Encoding"] = "identity"
        if self.userAgent and not any(k.lower() == "user-agent" for k in headers):
            headers["User-Agent"] = self.userAgent
        emulation = toEmulation(self.clientProfile or cfg.clientProfile.value, "")
        while True:
            client = buildClient(emulation=emulation, userAgent=self.userAgent or None, readTimeout=30)
            try:
                self.receivedBytes = 0
                self.progress = 0
                response = await client.post(self.url, headers=headers, body=(self.requestBody or UUPDUMP_BODY).encode("utf-8"))
                try:
                    status = response.status.as_int()
                    if status in PERMANENT_STATUS or response.headers.contains_key("cf-mitigated"):
                        raise TaskError("服务器返回了错误（{status}）", status=status)
                    if status not in {200, 206}:
                        response.raise_for_status()
                    if self.preferResponseFilename:
                        responseName = _filename_from_content_disposition(response.headers.get("content-disposition"))
                        if responseName:
                            self.task.name = responseName
                    Path(self.outputPath).parent.mkdir(parents=True, exist_ok=True)
                    with open(self.outputPath, "wb") as output:
                        async for chunk in response.stream():
                            if not chunk:
                                continue
                            output.write(chunk)
                            self.receivedBytes += len(chunk)
                            if self.fileSize > 0:
                                self.progress = min(100.0, self.receivedBytes / self.fileSize * 100)
                            self._reportSpeed(len(chunk))
                            await self._waitForSpeedLimit()
                    if self.fileSize <= 0:
                        self.fileSize = self.receivedBytes
                        self.task.fileSize = self.receivedBytes
                    self.progress = 100
                    self.setStatus(TaskStatus.COMPLETED)
                    if cfg.shouldPreserveLastModified.value and self.lastModified:
                        try:
                            mtime = parsedate_to_datetime(self.lastModified).timestamp()
                            import os
                            os.utime(self.outputPath, (mtime, mtime))
                        except Exception as error:
                            logger.opt(exception=error).warning("设置文件修改时间失败 {}", self.outputPath)
                    return
                finally:
                    response.close()
            except asyncio.CancelledError:
                self.setStatus(TaskStatus.PAUSED)
                raise
            except TaskError:
                raise
            except Exception as error:
                logger.opt(exception=error).error("UUP dump 下载失败，将在 5 秒后重试 {}", self.outputPath)
                await asyncio.sleep(5)
            finally:
                client.close()
