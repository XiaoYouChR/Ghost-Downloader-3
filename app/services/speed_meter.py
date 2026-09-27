from __future__ import annotations

import asyncio

from app.config.cfg import cfg
from app.signal import Signal


class SpeedMeter:
    speedChanged = Signal()
    def __init__(self, coroutineRunner):
        self._coroutineRunner = coroutineRunner
        self._bytes = 0
        self._currentSpeed = 0
        self._tickWorkId: str | None = None

    @property
    def currentSpeed(self) -> int:
        return self._currentSpeed

    def start(self) -> None:
        if self._tickWorkId is not None:
            return
        self._tickWorkId = self._coroutineRunner.submit(
            self._tickLoop(), failed=self._onTickFailed)

    def stop(self) -> None:
        if self._tickWorkId is None:
            return
        self._coroutineRunner.cancel(self._tickWorkId)
        self._tickWorkId = None
        self._bytes = 0
        self._currentSpeed = 0
        self.speedChanged.emit(0)

    def addSpeed(self, byteCount: int) -> None:
        self._bytes += byteCount

    async def waitForSpeedLimit(self) -> None:
        while cfg.isSpeedLimitEnabled.value and self._bytes > cfg.speedLimitation.value:
            await asyncio.sleep(0.1)

    async def _tickLoop(self) -> None:
        while True:
            await asyncio.sleep(1)
            self._coroutineRunner.post(self._tick)

    def _tick(self) -> None:
        self._currentSpeed = self._bytes
        self._bytes = 0
        self.speedChanged.emit(self._currentSpeed)

    def _onTickFailed(self, error) -> None:
        self._tickWorkId = None
