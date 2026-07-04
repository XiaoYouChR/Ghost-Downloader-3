from __future__ import annotations

import asyncio
import json
from urllib.parse import urlparse, parse_qs, quote

from app.models.pack import FeaturePack, TaskParser
from app.models.task import Task, TaskOptions, SpecialFileSize
from app.platform.filesystem import toSafeFilename
from .config import jsRuntime, ytDlpConfig, ytDlpRuntime
from .task import YtDlpTask, YtDlpTaskStep


YOUTUBE_HOSTS = ("youtube.com", "youtu.be")


class YouTubeParser(TaskParser):
    priority = 70

    def match(self, options: TaskOptions) -> bool:
        host = (urlparse(options.url).hostname or "").lower()
        return any(host == h or host.endswith(f".{h}") for h in YOUTUBE_HOSTS)

    async def parse(self, options: TaskOptions) -> Task:
        url = options.url.strip()
        headers = dict(options.headers)

        title = await self._fetchTitle(url)
        name = toSafeFilename(title) if title else "YouTube 视频"
        isPlaylist = bool(parse_qs(urlparse(url).query).get("list"))

        task = YtDlpTask(
            name=f"{name}.mp4",
            url=url,
            fileSize=SpecialFileSize.UNKNOWN,
            outputFolder=options.outputFolder,
            isPlaylist=isPlaylist,
        )
        task.addStep(YtDlpTaskStep(
            stepIndex=1,
            headers=headers,
        ))
        return task

    async def fetchMediaInfo(self, url: str) -> dict:
        stdout = await self._runCommand([url, "--dump-json", "--no-playlist", "--no-warnings"])
        if stdout:
            return json.loads(stdout.decode("utf-8", errors="ignore"))
        return {}

    async def _fetchTitle(self, url: str) -> str:
        from app.client import buildClient
        oembedUrl = f"https://www.youtube.com/oembed?url={quote(url, safe='')}&format=json"
        try:
            client = buildClient(timeout=5)
            response = await client.get(oembedUrl)
            data = await response.json()
            return str(data.get("title") or "")
        except Exception:
            return ""

    async def probePlaylist(self, url: str) -> list[dict]:
        stdout = await self._runCommand([url, "--flat-playlist", "--dump-json", "--no-warnings"], timeout=60)
        entries: list[dict] = []
        if stdout:
            for line in stdout.decode("utf-8", errors="ignore").strip().splitlines():
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return entries

    async def _runCommand(self, args: list[str], timeout: int = 30) -> bytes | None:
        execPath = ytDlpRuntime.path()
        if not execPath:
            return None

        from app.config.cfg import proxy
        proxyUrl = proxy()
        if proxyUrl:
            args.extend(["--proxy", proxyUrl])
        browser = ytDlpConfig.loginBrowser.value
        if browser:
            args.extend(["--cookies-from-browser", browser])
        args.extend(jsRuntime.buildArgs())

        process = await asyncio.create_subprocess_exec(
            execPath, *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        if process.returncode == 0:
            return stdout

        errorText = stderr.decode("utf-8", errors="ignore").strip()
        for line in reversed(errorText.splitlines()):
            if "ERROR:" in line:
                errorText = line.split("ERROR:", 1)[-1].strip()
                break
        raise RuntimeError(errorText or f"yt-dlp 退出码异常: {process.returncode}")


class YouTubePack(FeaturePack):
    packId = "ytdlp"

    def __init__(self):
        self.config = ytDlpConfig

    def parsers(self):
        return [YouTubeParser()]

    def taskCard(self, task, parent=None):
        from .cards import YtDlpTaskCard
        return YtDlpTaskCard(task, parent)

    def draftCard(self, task, parent=None):
        from .cards import YtDlpDraftCard
        return YtDlpDraftCard(task, parent)

    def optionCards(self, task, parent=None):
        from app.view.components.option_cards import OutputFolderCard
        return [
            OutputFolderCard(parent, initial=task.outputFolder),
        ]
