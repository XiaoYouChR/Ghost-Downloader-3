from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse

from loguru import logger

from app.models.pack import FeaturePack, TaskParser
from app.models.task import Task, TaskOptions, SpecialFileSize
from app.platform.filesystem import toPosixPath, toSafeFilename
from .task import (
    FTP_DEFAULT_PORT,
    FtpConnectionInfo,
    FtpFile,
    FtpStep,
    FtpTask,
)


class FtpParser(TaskParser):
    priority = 95

    def match(self, options: TaskOptions) -> bool:
        return urlparse(options.url).scheme.lower() in {"ftp", "ftps"}

    async def parse(self, options: TaskOptions) -> Task:
        url = options.url.strip()
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()

        sourcePath = PurePosixPath(unquote(parsed.path or "/"))
        connectionInfo = FtpConnectionInfo(
            scheme=scheme,
            host=parsed.hostname or "",
            port=parsed.port or FTP_DEFAULT_PORT,
            username=unquote(parsed.username or "anonymous"),
            password=unquote(parsed.password or "anon@"),
            sourcePath=str(sourcePath),
            hasPort=parsed.port is not None,
        )

        client = await connectionInfo.connect()
        try:
            sourceInfo = await client.stat(sourcePath)
            sourceType = sourceInfo["type"]
            if sourceType not in {"file", "dir"}:
                raise ValueError("当前 FTP 路径既不是普通文件，也不是目录")

            try:
                await client.command("TYPE I", "200")
                await client.command("REST 1", "350")
                canUseRangeRequests = True
            except Exception as e:
                logger.info("FTP 服务器不支持 REST 断点续传: {}", repr(e))
                canUseRangeRequests = False

            files: list[FtpFile] = []
            if sourceType == "file":
                files.append(FtpFile(
                    index=0,
                    remotePath=str(sourcePath),
                    relativePath=sourcePath.name or "ftp_file",
                    size=max(int(sourceInfo.get("size") or 0), 0) or SpecialFileSize.UNKNOWN,
                ))
            else:
                entries = [item async for item in client.list(sourcePath, recursive=True)]
                index = 0
                for remotePath, info in entries:
                    if info["type"] != "file":
                        continue
                    relPath = (
                        str(remotePath.relative_to(sourcePath))
                        if sourcePath in remotePath.parents
                        else remotePath.name
                    )
                    files.append(FtpFile(
                        index=index,
                        remotePath=str(remotePath),
                        relativePath=relPath,
                        size=max(int(info.get("size") or 0), 0) or SpecialFileSize.UNKNOWN,
                    ))
                    index += 1

                if not files:
                    raise ValueError("该 FTP 目录中没有可下载的普通文件")

            name = toSafeFilename(
                sourcePath.name or connectionInfo.host,
                fallback="ftp_download",
            )

            steps = []
            for file in files:
                steps.append(FtpStep(
                    stepIndex=len(steps) + 1,
                    fileIndex=file.index,
                    remotePath=file.remotePath,
                    fileSize=file.size,
                    canUseRangeRequests=canUseRangeRequests,
                    subworkerCount=options.subworkerCount,
                ))

            task = FtpTask(
                name=name,
                url=url,
                fileSize=sum(f.size for f in files),
                outputFolder=options.outputFolder,
                steps=steps,
                connectionInfo=connectionInfo,
                sourceType=sourceType,
                files=files,
            )
            return task
        finally:
            try:
                await client.quit()
            except Exception:
                client.close()


class FtpPack(FeaturePack):
    packId = "ftp"
    proxySchemes = {"socks4", "socks5"}

    def parsers(self):
        return [FtpParser()]

    def taskCard(self, task, parent=None):
        from .cards import FtpTaskCard
        return FtpTaskCard(task, self._services.taskService, self._services.featureService, self._services.categoryService, parent)

    def draftCard(self, task, parent=None):
        from .cards import FtpDraftCard
        return FtpDraftCard(task, self._services.categoryService, parent)

    def optionCards(self, task, parent=None):
        from app.view.components.option_cards import OutputFolderCard, SubworkerCountCard
        step = task.steps[0] if task.steps else None
        if step is None:
            return []
        return [
            OutputFolderCard(parent, initial=task.outputFolder),
            SubworkerCountCard(parent, initial=step.subworkerCount),
        ]
