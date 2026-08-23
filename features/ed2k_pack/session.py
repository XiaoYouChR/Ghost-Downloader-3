from __future__ import annotations

import asyncio
from pathlib import Path

from loguru import logger

from app.config.paths import APP_DATA_DIR
from app.models.task import TaskError
from .config import ed2kConfig, ed2kRuntime
from .python_ed2k import Client, Settings


class ED2kSession:

    def __init__(self):
        self._client: Client | None = None
        self._openLock = asyncio.Lock()
        self._activeTransfers: set[tuple[str, int]] = set()
        self.submit = None

    @staticmethod
    def toTransferKey(fileHash: str, fileSize: int) -> tuple[str, int]:
        return fileHash.upper(), fileSize

    def hasActiveTransfer(self, fileHash: str, fileSize: int) -> bool:
        return self.toTransferKey(fileHash, fileSize) in self._activeTransfers

    def acquireTransfer(self, fileHash: str, fileSize: int) -> tuple[str, int]:
        identity = self.toTransferKey(fileHash, fileSize)
        if identity in self._activeTransfers:
            raise TaskError("该 eD2k 链接已在下载中")
        self._activeTransfers.add(identity)
        return identity

    def releaseTransfer(self, identity: tuple[str, int]) -> None:
        self._activeTransfers.discard(identity)

    def requestRemove(self, fileHash: str) -> None:
        if self.submit is None:
            return
        self.submit(self.remove(fileHash))

    async def remove(self, fileHash: str) -> None:
        await self.open()
        await self.client().remove(fileHash, deleteFile=False)

    def client(self) -> Client:
        if self._client is None:
            raise TaskError("ED2kSession 未启动")
        return self._client

    async def open(self) -> None:
        async with self._openLock:
            if self._client is not None and self._client.isRunning:
                return

            # An unexpected daemon exit is remembered by Client so active tasks
            # can report it.  A later task attempt must replace that dead client
            # instead of replaying the same cached EngineExited forever.
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
