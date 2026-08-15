from __future__ import annotations

from pathlib import Path

from loguru import logger

from app.config.paths import APP_DATA_DIR
from app.models.task import TaskError
from .config import ed2kConfig, ed2kRuntime
from .python_ed2k import Client, Settings


class ED2kSession:

    def __init__(self):
        self._client: Client | None = None
        self.submit = None

    def removeHash(self, fileHash: str) -> None:
        if self._client is None or self.submit is None:
            return
        try:
            self.submit(self._client.remove(fileHash, deleteFile=True))
        except Exception:
            pass

    def client(self) -> Client:
        if self._client is None:
            raise TaskError("ED2kSession 未启动")
        return self._client

    async def open(self) -> None:
        if self._client is not None:
            return
        path = ed2kRuntime.path()
        if not path:
            raise TaskError(
                "{name} 未安装，请在设置中安装", name=ed2kRuntime.name
            )
        client = Client(Path(path), Path(APP_DATA_DIR) / "ed2k_data")
        try:
            await client.start(Settings(
            enableDht=ed2kConfig.enableDht.value,
            enableUpnp=ed2kConfig.enableUpnp.value,
            listenPort=ed2kConfig.listenPort.value,
            serverMetSource=ed2kConfig.serverMetSource.value or None,
            nodesDatSource=ed2kConfig.nodesDatSource.value or None,
        ))
        except Exception:
            await client.terminate()
            raise
        self._client = client

    async def close(self) -> None:
        if self._client is None:
            return
        await self._client.close()
        self._client = None


ed2kSession = ED2kSession()
