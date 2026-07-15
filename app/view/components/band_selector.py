from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QRubberBand, QScrollArea, QWidget


class BandSelector(QObject):

    dragStarted = Signal(bool)
    bandChanged = Signal(int, int)
    dragFinished = Signal()

    def __init__(self, scrollArea: QScrollArea, scrollWidget: QWidget,
                 rowHeight: int, rowSpacing: int, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._scrollArea = scrollArea
        self._scrollWidget = scrollWidget
        self._stride = rowHeight + rowSpacing
        self._itemCount = 0
        self._isEnabled = True

        self._isDragging = False
        self._isPending = False
        self._pressPos = QPoint()
        self._startX = 0
        self._startY = 0
        self._lastX = 0
        self._lastViewportY = 0
        self._isShiftHeld = False
        self._scrollDelta = 0

        self._band = QRubberBand(QRubberBand.Shape.Rectangle, scrollWidget)
        self._autoScrollTimer = QTimer(self)
        self._autoScrollTimer.setInterval(30)
        self._autoScrollTimer.timeout.connect(self._onAutoScroll)

        scrollWidget.installEventFilter(self)
        scrollArea.verticalScrollBar().valueChanged.connect(self._onScrollChanged)

    def setItemCount(self, count: int) -> None:
        self._itemCount = count
        if self._isDragging:
            self._cancelDrag()

    def setEnabled(self, enabled: bool) -> None:
        self._isEnabled = enabled
        if not enabled and self._isDragging:
            self._cancelDrag()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if not self._isEnabled:
            return False

        t = event.type()

        if t == QEvent.Type.WindowDeactivate and self._isDragging:
            self._cancelDrag()
            return False

        if t == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._isPending = True
            self._pressPos = event.position().toPoint()
            self._startX = self._pressPos.x()
            self._startY = self._pressPos.y()
            self._lastX = self._startX
            self._lastViewportY = self._startY - self._scrollArea.verticalScrollBar().value()
            self._isShiftHeld = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            return False

        if t == QEvent.Type.MouseMove and (self._isPending or self._isDragging):
            pos = event.position().toPoint()
            self._lastX = pos.x()
            self._lastViewportY = pos.y() - self._scrollArea.verticalScrollBar().value()

            if not self._isDragging:
                if (pos - self._pressPos).manhattanLength() < QApplication.startDragDistance():
                    return False
                self._isDragging = True
                self._isPending = False
                self._band.show()
                self.dragStarted.emit(self._isShiftHeld)

            self._updateBand(self._lastX, pos.y())
            return True

        if t == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            if self._isDragging:
                self._cancelDrag()
                return True
            self._isPending = False
            return False

        return False

    def _updateBand(self, scrollWidgetX: int, scrollWidgetY: int) -> None:
        left = min(self._startX, scrollWidgetX)
        top = min(self._startY, scrollWidgetY)
        right = max(self._startX, scrollWidgetX)
        bottom = max(self._startY, scrollWidgetY)

        self._band.setGeometry(left, top, max(1, right - left), max(1, bottom - top))
        self._band.raise_()

        first = max(0, top // self._stride)
        last = min(self._itemCount - 1, bottom // self._stride)
        self.bandChanged.emit(first, last) if first <= last else self.bandChanged.emit(-1, -1)

        viewportY = self._lastViewportY
        viewportHeight = self._scrollArea.viewport().height()
        margin = 30
        if viewportY < margin:
            self._scrollDelta = max(-20, -(margin - viewportY) // 2)
            if not self._autoScrollTimer.isActive():
                self._autoScrollTimer.start()
        elif viewportY > viewportHeight - margin:
            self._scrollDelta = min(20, (viewportY - viewportHeight + margin) // 2)
            if not self._autoScrollTimer.isActive():
                self._autoScrollTimer.start()
        else:
            self._autoScrollTimer.stop()

    def _onAutoScroll(self) -> None:
        bar = self._scrollArea.verticalScrollBar()
        bar.setValue(bar.value() + self._scrollDelta)
        self._updateBand(self._lastX, self._lastViewportY + bar.value())

    def _onScrollChanged(self) -> None:
        if self._isDragging:
            self._updateBand(self._lastX, self._lastViewportY + self._scrollArea.verticalScrollBar().value())

    def _cancelDrag(self) -> None:
        self._isDragging = False
        self._isPending = False
        self._band.hide()
        self._autoScrollTimer.stop()
        self.dragFinished.emit()
