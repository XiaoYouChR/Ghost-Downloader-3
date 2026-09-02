from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote

from loguru import logger

from app.config.paths import APP_DATA_DIR
from app.models.task import TaskError
from .config import ed2kConfig, ed2kRuntime
from .python_ed2k import Client, Settings, Transfer, TransferState
from .python_ed2k.errors import ErrorCode, Error


@dataclass(frozen=True)
class RunResult:
    fileHash: str
    name: str
    fileSize: int


class ED2kSession:

    def __init__(self):
        self._client: Client | None = None
        self._openLock = asyncio.Lock()
        self._activeTransfers: set[tuple[str, int]] = set()
        self.submit = None

    def hasActiveTransfer(self, fileHash: str, fileSize: int) -> bool:
        return toTransferKey(fileHash, fileSize) in self._activeTransfers

    async def run(
        self,
        link: str,
        fileHash: str,
        name: str,
        outputFolder: Path,
        onStarted: Callable[[RunResult], None] | None = None,
        onProgress: Callable[[Transfer, int], None] | None = None,
        sharingTimeSeconds: int = 0,
    ) -> None:
        _, linkSize, linkHash = parseEd2kLink(link)
        identity = toTransferKey(linkHash, linkSize)
        if identity in self._activeTransfers:
            raise TaskError("该 eD2k 链接已在下载中")
        self._activeTransfers.add(identity)

        try:
            await self._open()
            client = self._client

            wasCancelled = False
            if fileHash:
                transfer = await client.resume(fileHash)
            else:
                try:
                    addTask = asyncio.create_task(
                        client.addLink(buildEd2kLink(link, name), outputFolder)
                    )
                    try:
                        transfer = await asyncio.shield(addTask)
                    except asyncio.CancelledError:
                        wasCancelled = True
                        transfer = await asyncio.wait_for(addTask, timeout=15)
                except Error as e:
                    if e.code == ErrorCode.TRANSFER_EXISTS:
                        transfer = await client.resume(linkHash.upper())
                    elif wasCancelled:
                        raise asyncio.CancelledError() from e
                    else:
                        raise TaskError("ED2k 错误：{detail}", detail=str(e)) from e

            fileHash = transfer.hash
            if onStarted:
                onStarted(RunResult(
                    fileHash=fileHash,
                    name=transfer.name or name,
                    fileSize=transfer.size,
                ))
            if wasCancelled:
                raise asyncio.CancelledError()

            sharingStart = 0.0
            loop = asyncio.get_running_loop()
            async for snapshot in client.snapshots():
                for t in snapshot.transfers:
                    if t.hash != fileHash:
                        continue
                    if not sharingStart and t.state == TransferState.FINISHED:
                        sharingStart = loop.time() - sharingTimeSeconds
                    elapsed = int(loop.time() - sharingStart) if sharingStart else 0
                    if onProgress:
                        onProgress(t, elapsed)
                    if sharingStart and isSharingLimitReached(elapsed):
                        await client.pause(fileHash)
                        return
                    break
            raise asyncio.CancelledError()
        except asyncio.CancelledError:
            if fileHash and self._client is not None:
                try:
                    await self._client.pause(fileHash)
                except Exception as e:
                    logger.opt(exception=e).warning("暂停 eD2k 传输失败")
            raise
        finally:
            self._activeTransfers.discard(identity)

    def remove(self, fileHash: str) -> None:
        if self.submit is None:
            return
        self.submit(self._remove(fileHash))

    async def _remove(self, fileHash: str) -> None:
        await self._open()
        try:
            await self._client.remove(fileHash, deleteFile=False)
        except Error as e:
            if e.code != ErrorCode.TRANSFER_NOT_FOUND:
                raise

    async def _open(self) -> None:
        async with self._openLock:
            if self._client is not None and self._client.isRunning:
                return

            # Dead client caches EngineExited; drop so the next attempt starts fresh.
            self._client = None

            path = ed2kRuntime.path()
            if not path:
                raise TaskError(
                    "{name} 未安装，请在设置中安装", name=ed2kRuntime.name
                )
            client = Client(Path(path), Path(APP_DATA_DIR) / "ed2k_data")
            await client.start(Settings(
                enableDht=ed2kConfig.enableDht.value,
                enableUpnp=ed2kConfig.enableUpnp.value,
                listenPort=ed2kConfig.listenPort.value,
                serverMetSource=ed2kConfig.serverMetSource.value or None,
                nodesDatSource=ed2kConfig.nodesDatSource.value or None,
            ))
            self._client = client

    async def close(self) -> None:
        async with self._openLock:
            client = self._client
            self._client = None
            if client is not None:
                await client.close()


ed2kSession = ED2kSession()


def isSharingLimitReached(elapsed: int) -> bool:
    limit = ed2kConfig.sharingTimeLimit.value
    return limit > 0 and elapsed >= limit * 60


def toTransferKey(fileHash: str, fileSize: int) -> tuple[str, int]:
    return fileHash.upper(), fileSize


def parseEd2kLink(link: str) -> tuple[str, int, str]:
    link = link.strip()
    if not link.lower().startswith("ed2k://"):
        raise ValueError("不是有效的 eD2k 链接")
    parts = link.strip("/").split("|")
    if len(parts) < 5 or parts[1].lower() != "file":
        raise ValueError("不支持的 eD2k 链接格式")
    name = unquote(parts[2])
    try:
        size = int(parts[3])
    except ValueError:
        size = 0
    fileHash = parts[4] if len(parts) > 4 else ""
    return name, size, fileHash


def buildEd2kLink(link: str, name: str) -> str:
    parts = link.strip().split("|")
    parts[2] = quote(name, safe="")
    return "|".join(parts)
