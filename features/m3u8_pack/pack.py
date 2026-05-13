from pathlib import Path
from urllib.parse import urlparse

import niquests

from app.bases.interfaces import FeaturePack
from app.bases.models import Task
from app.supports.config import DEFAULT_HEADERS, cfg
from app.supports.utils import getProxies, splitCookies, toPosixPath
from .config import m3u8Config
from .task import M3U8TaskStage, _isLive, _manifestType, _stem, _title


class M3U8Pack(FeaturePack):
    packId = "m3u8"
    priority = 80
    config = m3u8Config

    def matches(self, url: str) -> bool:
        parsedUrl = urlparse(url)
        if parsedUrl.scheme.lower() not in {"http", "https"}:
            return False
        loweredUrl = url.lower()
        return ".m3u8" in loweredUrl or ".m3u" in loweredUrl or ".mpd" in loweredUrl

    async def parse(self, payload: dict) -> Task:
        url = str(payload["url"]).strip()
        headers = payload.get("headers", DEFAULT_HEADERS)
        proxies = payload.get("proxies", getProxies())
        path: Path = payload.get("path", Path(cfg.downloadFolder.value))
        requestHeaders, requestCookies = splitCookies(
            headers if isinstance(headers, dict) else DEFAULT_HEADERS
        )

        client = niquests.AsyncSession(timeout=30, happy_eyeballs=True)
        client.trust_env = False

        try:
            response = await client.get(
                url,
                headers=requestHeaders,
                cookies=requestCookies,
                proxies=proxies,
                verify=cfg.SSLVerify.value,
                allow_redirects=True,
            )
            try:
                response.raise_for_status()
                body = response.text
                loweredHeaders = {key.lower(): value for key, value in response.headers.items()}
                manifestType = _manifestType(str(response.url), loweredHeaders, body)
                isLive = _isLive(manifestType, body)
                extension = "ts" if m3u8Config.liveRealTimeMerge.value else m3u8Config.outputFormat.value
                title = _title(str(response.url), loweredHeaders, extension)
            finally:
                response.close()
        finally:
            await client.close()

        if isinstance(headers, dict):
            headers = headers.copy()
        else:
            headers = DEFAULT_HEADERS.copy()

        saveName = _stem(title)
        metadata = {
            "headers": headers,
            "proxies": proxies,
            "threadCount": m3u8Config.threadCount.value,
            "retryCount": m3u8Config.retryCount.value,
            "requestTimeout": m3u8Config.requestTimeout.value,
            "autoSelect": m3u8Config.autoSelect.value,
            "concurrentDownload": m3u8Config.concurrentDownload.value,
            "appendUrlParams": m3u8Config.appendUrlParams.value,
            "binaryMerge": m3u8Config.binaryMerge.value,
            "checkSegmentsCount": m3u8Config.checkSegmentsCount.value,
            "outputFormat": m3u8Config.outputFormat.value,
            "liveRealTimeMerge": m3u8Config.liveRealTimeMerge.value,
            "liveKeepSegments": m3u8Config.liveKeepSegments.value,
            "livePipeMux": m3u8Config.livePipeMux.value,
            "manifestType": manifestType,
            "isLive": isLive,
            "actualExtension": "",
            "saveName": saveName,
            "outputExtension": extension,
        }

        task = Task(
            title=title,
            url=url,
            packId=self.packId,
            fileSize=1,
            path=path,
            metadata=metadata,
        )

        taskId = task.taskId
        outputFile = toPosixPath(path / title)
        tempDir = toPosixPath(path / ".gd3_m3u8" / taskId)

        task.addStage(M3U8TaskStage(
            stageIndex=1,
            outputFile=outputFile,
            tempDir=tempDir,
        ))
        return task
