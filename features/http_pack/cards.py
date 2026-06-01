from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget
from qfluentwidgets import isDarkTheme, themeColor

from app.view.components.cards import UniversalTaskCard
from .task import HttpTaskStage

FILL_EASING = 0.25


class SegmentedProgressBar(QWidget):
    """多连接下载的分段进度条

    整条代表文件 [0, fileSize], 每个分片按真实字节区间 [start, progress) 填充,
    分片间的待下载区天然留缝. 配色与 qfluentwidgets.ProgressBar 对齐.
    """

    def __init__(self, stage: HttpTaskStage, parent: QWidget = None):
        super().__init__(parent)
        self._stage = stage
        self._isPaused = False
        self._isError = False
        self._fillProgress: dict[int, float] = {}
        self._spans: list[tuple[float, float]] = []
        self._fillTimer = QTimer(self, interval=16)
        self._bind()

    def _bind(self):
        self._fillTimer.timeout.connect(self._onFillTimeout)

    def setValue(self, value: float):
        # 数值不看: 段位置取自 subworkers; 立即推进一步免挂载首帧空白
        self._fillTimer.start()
        self._onFillTimeout()

    def _onFillTimeout(self):
        live = {sw.start: sw.progress for sw in list(self._stage.subworkers)}
        fresh = not self._fillProgress  # 首次填充(挂载/恢复运行): 直接到位, 不从头爬
        settled = True
        for start, target in live.items():
            shown = self._fillProgress.get(start, target if fresh else start)
            if target - shown > 1:
                self._fillProgress[start] = shown + (target - shown) * FILL_EASING
                settled = False
            else:
                self._fillProgress[start] = target
        self._fillProgress = {start: self._fillProgress[start] for start in live}  # 剪掉消失的段
        self._spans = self._toMergedSpans()
        if not self._spans and self._stage.receivedBytes > 0:
            # worker 没跑过(重启恢复/等待中): 退化成单根, 按已收字节画
            self._spans = [(0, self._stage.receivedBytes)]
        if settled:
            self._fillTimer.stop()
        self.update()

    def setError(self, isError: bool):
        self._isError = isError
        if not isError:
            self._isPaused = False
        self.update()

    def error(self):
        self._isError = True
        self.update()

    def pause(self):
        self._isPaused = True
        self.update()

    def barColor(self) -> QColor:
        if self._isPaused:
            return QColor(252, 225, 0) if isDarkTheme() else QColor(157, 93, 0)
        if self._isError:
            return QColor(255, 153, 164) if isDarkTheme() else QColor(196, 43, 28)
        return themeColor()

    def _toMergedSpans(self) -> list[tuple[float, float]]:
        # 相邻分片下载完后首尾恰好相接, 合并掉以免接缝处冒出假凹口
        intervals = sorted(
            (start, shown) for start, shown in self._fillProgress.items() if shown > start
        )
        merged: list[tuple[float, float]] = []
        for start, end in intervals:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged

    def paintEvent(self, e):
        fileSize = self._stage.fileSize
        if fileSize <= 0 or not self._spans:
            return

        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.barColor())

        width = self.width()
        height = self.height()
        radius = height / 2
        for start, end in self._spans:
            x = start / fileSize * width
            w = (end - start) / fileSize * width
            painter.drawRoundedRect(QRectF(x, 0, w, height), radius, radius)


class HttpTaskCard(UniversalTaskCard):
    """HTTP 任务卡片: 已知大小且支持续传时用分段进度条, 否则退回通用进度条"""

    def createProgressBar(self) -> QWidget:
        if self.task.fileSize > 0 and self.task.stage.supportsRange:
            return SegmentedProgressBar(self.task.stage, self)
        return super().createProgressBar()
