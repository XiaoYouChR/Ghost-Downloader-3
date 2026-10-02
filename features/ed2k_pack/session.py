from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator, Callable
from contextlib import aclosing, asynccontextmanager
from typing import TYPE_CHECKING

from app.config.cfg import cfg
from app.models.task import TaskError
from app.signal import Signal
from .config import ed2kConfig, kelpieRuntime
from .kelpie import Error, ErrorCode, Kelpie, Link, Network, Progress, Run, Settings
from .lists import nodeList, serverList

if TYPE_CHECKING:
    from app.services.coroutine_runner import CoroutineRunner
    from .task import ED2kTask


LIVE_SETTINGS = (
    cfg.isSpeedLimitEnabled, cfg.speedLimitation,
    ed2kConfig.uploadRateLimit, ed2kConfig.enableKad, ed2kConfig.enableUpnp,
)


def buildSettings() -> Settings:
    return Settings(
        port=ed2kConfig.listenPort.value,
        enableKad=ed2kConfig.enableKad.value,
        enableUpnp=ed2kConfig.enableUpnp.value,
        serverLists=tuple(serverList.paths()),
        nodeLists=tuple(nodeList.paths()),
        downloadRateLimit=cfg.speedLimitation.value if cfg.isSpeedLimitEnabled.value else 0,
        uploadRateLimit=ed2kConfig.uploadRateLimit.value,
    )


class ED2kSession:
    networkChanged = Signal()
    runsChanged = Signal()

    def __init__(self):
        self._runner: CoroutineRunner | None = None
        self._kelpie: Kelpie | None = None
        self._progresses: dict[str, Progress] = {}
        self._network: Network | None = None
        self._openRunCount = 0
        self._stopping: asyncio.Task[None] | None = None
        self._removals: set[asyncio.Task] = set()

    def open(
        self, coroutineRunner: CoroutineRunner, createKelpie: Callable[[Callable[[Network | None], None]], Kelpie],
    ) -> None:
        self._runner = coroutineRunner
        self._kelpie = createKelpie(self._onNetwork)
        for item in LIVE_SETTINGS:
            item.valueChanged.connect(self._onSettingsChanged)

    @property
    def network(self) -> Network | None:
        return self._network

    @property
    def isIdle(self) -> bool:
        return self._openRunCount == 0

    def progressOf(self, task: ED2kTask) -> Progress | None:
        return self._progresses.get(task.taskId)

    def isActive(self, task: ED2kTask) -> bool:
        return self._kelpie is not None and self._kelpie.isActive(Link.parse(task.url).hash)

    @asynccontextmanager
    async def run(self, task: ED2kTask, isSeed: bool) -> AsyncIterator[AsyncIterator[Progress]]:
        if self._kelpie is None:
            raise asyncio.CancelledError()
        if not kelpieRuntime.path():
            raise TaskError("{name} 未安装，请在设置中安装", name=kelpieRuntime.name)
        start = self._kelpie.runSeed if isSeed else self._kelpie.runDownload
        self._openRunCount += 1
        self._runner.post(self.runsChanged.emit)
        try:
            if self._stopping is not None:
                await asyncio.shield(self._stopping)
            async with start(Link.parse(task.url), task.outputFolder / task.name) as transfer:
                async with aclosing(self._record(task.taskId, transfer)) as recorded:
                    yield recorded
        except Error as error:
            raise toTaskError(error) from error
        finally:
            self._progresses.pop(task.taskId, None)
            self._openRunCount -= 1
            self._runner.post(self.runsChanged.emit)

    def delete(self, task: ED2kTask) -> None:
        if not kelpieRuntime.path():
            return
        kelpie = self._kelpie
        hash = Link.parse(task.url).hash

        async def remove():
            removal = asyncio.current_task()
            self._removals.add(removal)
            try:
                if self._stopping is not None:
                    await asyncio.shield(self._stopping)
                await kelpie.remove(hash)
            finally:
                self._removals.discard(removal)

        self._runner.submit(remove())

    async def stop(self) -> None:
        if not self.isIdle or self._stopping is not None:
            return
        self._stopping = asyncio.ensure_future(self._kelpie.close())
        try:
            await self._stopping
        finally:
            self._stopping = None

    async def close(self) -> None:
        kelpie, self._kelpie = self._kelpie, None
        if kelpie is None:
            return
        for item in LIVE_SETTINGS:
            item.valueChanged.disconnect(self._onSettingsChanged)
        if self._removals:
            await asyncio.wait(self._removals)
        await kelpie.close()

    async def _record(self, taskId: str, transfer: Run) -> AsyncIterator[Progress]:
        async for progress in transfer:
            self._progresses[taskId] = progress
            yield progress

    def _onNetwork(self, network: Network | None) -> None:
        self._network = network
        self._runner.post(self.networkChanged.emit)

    def _onSettingsChanged(self, *_) -> None:
        kelpie = self._kelpie

        async def update():
            kelpie.update()

        self._runner.submit(update())
        self.networkChanged.emit()


def toHeldMinutes(progress: Progress | None, now: int) -> int | None:
    if progress is None or progress.heldSources == 0 or progress.heldUntil <= now:
        return None
    remaining = progress.heldUntil - now
    return 0 if remaining < 60_000 else math.ceil(remaining / 60_000)


def toTaskError(error: Error) -> TaskError:
    name = kelpieRuntime.name
    match error.code:
        case ErrorCode.INVALID_LINK:
            return TaskError("不是有效的 eD2k 链接")
        case ErrorCode.OUTPUT_EXISTS:
            return TaskError("目标文件已被占用")
        case ErrorCode.TRANSFER_BUSY:
            return TaskError("该 eD2k 链接已在下载中")
        case ErrorCode.DISK_FULL:
            return TaskError("磁盘空间不足")
        case ErrorCode.FILE_ERROR:
            return TaskError("无法读写文件：{detail}", detail=error.message)
        case ErrorCode.OUTDATED:
            return TaskError("{name} 版本过旧，请在设置中更新", name=name)
        case ErrorCode.START_FAILED:
            return TaskError("{name} 启动失败：{detail}", name=name, detail=error.message)
        case ErrorCode.ENGINE_EXITED:
            return TaskError("{name} 意外退出：{detail}", name=name, detail=error.message)
        case _:
            return TaskError("ED2k 错误：{detail}", detail=error.message)


ed2kSession = ED2kSession()
