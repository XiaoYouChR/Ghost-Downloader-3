from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, QRectF, QSize, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from qfluentwidgets import (
    FluentIcon, FluentStyleSheet, InfoBar, InfoBarIcon, InfoBarManager,
    InfoBarPosition, TransparentToolButton, isDarkTheme,
)

from app.error_catalog import toLocalizedError
from app.services.update_service import UpdateState

if TYPE_CHECKING:
    from collections.abc import Callable

    from PySide6.QtWidgets import QWidget

    from app.services.update_service import UpdateInfo

BAR_HEIGHT = 3
CORNER_RADIUS = 6
FILL_EASING = 0.25

COLORS = {
    UpdateState.DOWNLOADING: {"light": QColor("#9D5D00"), "dark": QColor("#FCE100")},
    UpdateState.READY:       {"light": QColor("#0F7B0F"), "dark": QColor("#6CCB5F")},
    UpdateState.FAILED:      {"light": QColor("#C42B1C"), "dark": QColor("#FF99A4")},
}


def barColor(state: UpdateState) -> QColor:
    pair = COLORS.get(state, COLORS[UpdateState.DOWNLOADING])
    return pair["dark"] if isDarkTheme() else pair["light"]


class ProgressToast(InfoBar):

    def __init__(self, onRetry: Callable, parent: QWidget):
        super().__init__(
            icon=InfoBarIcon.WARNING,
            title="",
            content="",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            duration=-1,
            position=InfoBarPosition.BOTTOM_RIGHT,
            parent=parent,
        )
        self.setProperty("type", "")
        FluentStyleSheet.INFO_BAR.apply(self)

        self.titleLabel.show()
        self.contentLabel.show()

        self._targetProgress = 0.0
        self._displayProgress = 0.0
        self._barColor = barColor(UpdateState.DOWNLOADING)
        self._isDismissed = False
        self._fillTimer = QTimer(self, interval=16)
        self._fillTimer.timeout.connect(self._onFillTick)
        self._retryButton = TransparentToolButton(FluentIcon.SYNC, self)
        self._retryButton.setFixedSize(36, 36)
        self._retryButton.setIconSize(QSize(12, 12))
        self._retryButton.hide()
        self._retryButton.clicked.connect(onRetry)

        self._restartButton = TransparentToolButton(FluentIcon.POWER_BUTTON, self)
        self._restartButton.setFixedSize(36, 36)
        self._restartButton.setIconSize(QSize(12, 12))
        self._restartButton.hide()
        self._restartButton.clicked.connect(QCoreApplication.quit)

        closeIdx = self.hBoxLayout.indexOf(self.closeButton)
        self.hBoxLayout.insertWidget(closeIdx, self._restartButton, 0, Qt.AlignTop | Qt.AlignLeft)
        self.hBoxLayout.insertWidget(closeIdx, self._retryButton, 0, Qt.AlignTop | Qt.AlignLeft)

        self.closeButton.clicked.disconnect()
        self.closeButton.clicked.connect(self._onUserClose)

    def setInfo(self, info: UpdateInfo) -> None:
        if info.state == UpdateState.DOWNLOADING:
            if self._isDismissed:
                return
            self._targetProgress = info.progress
            self._barColor = barColor(UpdateState.DOWNLOADING)
            self.iconWidget.icon = InfoBarIcon.WARNING
            self.title = self.tr("正在下载更新")
            self.content = f"{info.latestVersion} ({info.progress:.0f}%)"
            self._retryButton.hide()
            self._restartButton.hide()
            self._fillTimer.start()
        elif info.state == UpdateState.READY:
            self._isDismissed = False
            self._targetProgress = 100
            self._barColor = barColor(UpdateState.READY)
            self.iconWidget.icon = InfoBarIcon.SUCCESS
            self.title = self.tr("更新已就绪")
            self.content = self.tr("重启后生效")
            self._retryButton.hide()
            self._restartButton.show()
            self._fillTimer.start()
        elif info.state == UpdateState.FAILED:
            self._isDismissed = False
            self._targetProgress = 100
            self._displayProgress = 100
            self._barColor = barColor(UpdateState.FAILED)
            self.iconWidget.icon = InfoBarIcon.ERROR
            self.title = self.tr("下载更新失败")
            self.content = (
                toLocalizedError(info.error)
                if info.error is not None else self.tr("未知错误")
            )
            self._retryButton.show()
            self._restartButton.hide()
            self._fillTimer.stop()
        else:
            return

        self._adjustText()
        if not self.isVisible():
            self.show()
        elif self.parent() and self.position != InfoBarPosition.NONE:
            manager = InfoBarManager.make(self.position)
            self.move(manager._pos(self))
        self.iconWidget.update()
        self.update()

    def closeEvent(self, e):
        self._fillTimer.stop()
        self.closedSignal.emit()
        self.hide()
        e.ignore()

    def paintEvent(self, e):
        super().paintEvent(e)
        if self._displayProgress <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), CORNER_RADIUS, CORNER_RADIUS)
        painter.setClipPath(path)
        barW = int(self.width() * self._displayProgress / 100)
        painter.fillRect(0, self.height() - BAR_HEIGHT, barW, BAR_HEIGHT, self._barColor)

    def _onFillTick(self):
        diff = self._targetProgress - self._displayProgress
        if abs(diff) < 0.5:
            self._displayProgress = self._targetProgress
            self._fillTimer.stop()
        else:
            self._displayProgress += diff * FILL_EASING
        self.update()

    def _onUserClose(self):
        self._isDismissed = True
        self.close()
