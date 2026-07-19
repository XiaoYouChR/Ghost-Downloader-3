from __future__ import annotations

import asyncio

from PySide6.QtCore import QObject, QTimer, Signal

from app.config.cfg import cfg


class SpeedMeter(QObject):
    speedChanged = Signal(int)
    _bytesAdded = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bytes = 0
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._bytesAdded.connect(self.start)

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._bytes = 0
        self.speedChanged.emit(0)

    def addSpeed(self, byteCount: int) -> None:
        self._bytes += byteCount
        self._bytesAdded.emit()

    async def waitForSpeedLimit(self) -> None:
        while cfg.isSpeedLimitEnabled.value and self._bytes > cfg.speedLimitation.value:
            await asyncio.sleep(0.1)

    def _tick(self) -> None:
        byteCount = self._bytes
        self.speedChanged.emit(byteCount)
        self._bytes = 0
        if byteCount == 0:
            self._timer.stop()


speedMeter = SpeedMeter()
