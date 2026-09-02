from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget
from qfluentwidgets import LineEdit, isDarkTheme, themeColor
from qfluentwidgets.common.font import getFont, setFont

HANDLE_SIZE = 22
HANDLE_RADIUS = HANDLE_SIZE // 2
INNER_RADIUS = 5
GROOVE_HEIGHT = 4
GROOVE_RADIUS = 2
LABEL_HEIGHT = 24
LABEL_GAP = 4
LABEL_PADDING_H = 8
LABEL_PADDING_V = 6
LABEL_BORDER_RADIUS = 4
LABEL_FONT_SIZE = 12
PREVIEW_W = 160
PREVIEW_H = 90
PREVIEW_BORDER = 2
PREVIEW_BORDER_RADIUS = 4
PREVIEW_MARGIN = 6


class PreviewPopup(QWidget):

    def __init__(self):
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._pixmap = QPixmap()
        self.setFixedSize(PREVIEW_W + PREVIEW_BORDER * 2, PREVIEW_H + PREVIEW_BORDER * 2)

    def setPixmap(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self.update()

    def paintEvent(self, event):
        if self._pixmap.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        outerRect = QRectF(self.rect())
        innerRect = QRectF(PREVIEW_BORDER, PREVIEW_BORDER, PREVIEW_W, PREVIEW_H)
        dark = isDarkTheme()

        if dark:
            p.setBrush(QColor(50, 50, 50))
            p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        else:
            p.setBrush(QColor(249, 249, 249))
            p.setPen(QPen(QColor(0, 0, 0, 25), 1))
        p.drawRoundedRect(outerRect, PREVIEW_BORDER_RADIUS + PREVIEW_BORDER, PREVIEW_BORDER_RADIUS + PREVIEW_BORDER)

        clip = QPainterPath()
        clip.addRoundedRect(innerRect, PREVIEW_BORDER_RADIUS, PREVIEW_BORDER_RADIUS)
        p.setClipPath(clip)
        p.drawPixmap(innerRect, self._pixmap, QRectF(self._pixmap.rect()))


class RangeSlider(QWidget):
    rangeChanged = Signal(int, int)

    def __init__(self, parent=None, *, formatter=str, parser=int):
        super().__init__(parent)
        self._minimum = 0
        self._maximum = 100
        self._startValue = 0
        self._endValue = 100
        self._dragging = None
        self._editingHandle = None
        self._lineEdit = None
        self._formatter = formatter
        self._parser = parser
        self._previewProvider: Callable[[int], QPixmap | None] | None = None
        self._preview: PreviewPopup | None = None
        self._previewFrameIndex = -1
        self.setFixedHeight(LABEL_HEIGHT + LABEL_GAP + HANDLE_SIZE)
        self.setMouseTracking(True)

    def setRange(self, minimum: int, maximum: int) -> None:
        self._minimum = minimum
        self._maximum = max(minimum, maximum)
        self._startValue = max(self._minimum, min(self._startValue, self._maximum))
        self._endValue = max(self._startValue, min(self._endValue, self._maximum))
        self.update()

    def setValues(self, start: int, end: int) -> None:
        self._startValue = max(self._minimum, min(start, self._maximum))
        self._endValue = max(self._startValue, min(end, self._maximum))
        self.update()

    def clear(self) -> None:
        self._startValue = self._minimum
        self._endValue = self._maximum
        self.update()

    def startValue(self) -> int:
        return self._startValue

    def endValue(self) -> int:
        return self._endValue

    def setPreviewProvider(self, provider: Callable[[int], QPixmap | None] | None) -> None:
        self._previewProvider = provider

    def _toPixelX(self, value: int) -> float:
        span = self._maximum - self._minimum
        if span <= 0:
            return float(HANDLE_RADIUS)
        return HANDLE_RADIUS + (value - self._minimum) / span * (self.width() - HANDLE_SIZE)

    def _toValue(self, x: float) -> int:
        grooveLen = self.width() - HANDLE_SIZE
        if grooveLen <= 0:
            return self._minimum
        ratio = max(0.0, min(1.0, (x - HANDLE_RADIUS) / grooveLen))
        return self._minimum + round(ratio * (self._maximum - self._minimum))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        dark = isDarkTheme()
        accent = themeColor()
        handleCenterY = LABEL_HEIGHT + LABEL_GAP + HANDLE_RADIUS
        grooveY = handleCenterY - GROOVE_HEIGHT / 2

        startX = self._toPixelX(self._startValue)
        endX = self._toPixelX(self._endValue)

        # Inactive groove
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 115) if dark else QColor(0, 0, 0, 100))
        p.drawRoundedRect(
            QRectF(HANDLE_RADIUS, grooveY, self.width() - HANDLE_SIZE, GROOVE_HEIGHT),
            GROOVE_RADIUS, GROOVE_RADIUS,
        )

        # Active groove
        if endX > startX:
            p.setBrush(accent)
            p.drawRoundedRect(
                QRectF(startX, grooveY, endX - startX, GROOVE_HEIGHT),
                GROOVE_RADIUS, GROOVE_RADIUS,
            )

        # Handles
        for hx in (startX, endX):
            if dark:
                p.setBrush(QColor(69, 69, 69))
                p.setPen(QPen(QColor(0, 0, 0, 90), 1))
            else:
                p.setBrush(QColor(255, 255, 255))
                p.setPen(QPen(QColor(0, 0, 0, 25), 1))
            p.drawEllipse(QPointF(hx, handleCenterY), HANDLE_RADIUS, HANDLE_RADIUS)

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent)
            p.drawEllipse(QPointF(hx, handleCenterY), INNER_RADIUS, INNER_RADIUS)

        # Label bubbles
        p.setFont(getFont(LABEL_FONT_SIZE))

        startRect, endRect = self._labelRects()
        for rect, text in (
            (startRect, self._formatter(self._startValue)),
            (endRect, self._formatter(self._endValue)),
        ):
            if dark:
                p.setBrush(QColor(50, 50, 50))
                p.setPen(QPen(QColor(255, 255, 255, 15), 1))
            else:
                p.setBrush(QColor(249, 249, 249))
                p.setPen(QPen(QColor(0, 0, 0, 15), 1))
            p.drawRoundedRect(rect, LABEL_BORDER_RADIUS, LABEL_BORDER_RADIUS)

            p.setPen(QColor(255, 255, 255) if dark else QColor(0, 0, 0))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        x = event.position().x()
        startX = self._toPixelX(self._startValue)
        endX = self._toPixelX(self._endValue)

        # Label bubble click → inline edit
        if event.position().y() < LABEL_HEIGHT:
            startRect, endRect = self._labelRects()
            if endRect.contains(event.position()):
                self._startInlineEdit("end")
            elif startRect.contains(event.position()):
                self._startInlineEdit("start")
            return

        # Nearest handle → drag
        self._dragging = "start" if abs(x - startX) <= abs(x - endX) else "end"
        self._updateDrag(x)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._updateDrag(event.position().x())
        self._updatePreview(event.position().x())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = None

    def leaveEvent(self, event):
        self._hidePreview()

    def hideEvent(self, event):
        self._hidePreview()
        super().hideEvent(event)

    def _updatePreview(self, x: float) -> None:
        if not self._previewProvider:
            return

        value = self._toValue(x)
        if value != self._previewFrameIndex:
            self._previewFrameIndex = value
            frame = self._previewProvider(value)
            if frame is None:
                self._hidePreview()
                return
            if self._preview is None:
                self._preview = PreviewPopup()
            self._preview.setPixmap(frame)
            self._preview.show()

        if self._preview and self._preview.isVisible():
            globalPos = self.mapToGlobal(QPointF(x, 0)).toPoint()
            self._preview.move(
                globalPos.x() - self._preview.width() // 2,
                globalPos.y() - self._preview.height() - PREVIEW_MARGIN,
            )

    def _hidePreview(self) -> None:
        if self._preview is not None:
            self._preview.hide()
        self._previewFrameIndex = -1

    def _labelRects(self) -> tuple[QRectF, QRectF]:
        fm = QFontMetrics(getFont(LABEL_FONT_SIZE))

        startX = self._toPixelX(self._startValue)
        endX = self._toPixelX(self._endValue)
        bubbleH = fm.height() + LABEL_PADDING_V * 2
        bubbleY = LABEL_HEIGHT - bubbleH

        startW = fm.horizontalAdvance(self._formatter(self._startValue)) + LABEL_PADDING_H * 2
        endW = fm.horizontalAdvance(self._formatter(self._endValue)) + LABEL_PADDING_H * 2
        startBX = startX - startW / 2
        endBX = endX - endW / 2

        if startBX + startW + 2 > endBX:
            mid = (startX + endX) / 2
            startBX = mid - startW - 1
            endBX = mid + 1

        startBX = max(0.0, min(float(self.width()) - startW, startBX))
        endBX = max(0.0, min(float(self.width()) - endW, endBX))

        return QRectF(startBX, bubbleY, startW, bubbleH), QRectF(endBX, bubbleY, endW, bubbleH)

    def _updateDrag(self, x: float) -> None:
        value = self._toValue(x)
        if self._dragging == "start":
            value = max(self._minimum, min(value, self._endValue))
            if value != self._startValue:
                self._startValue = value
                self.update()
                self.rangeChanged.emit(self._startValue, self._endValue)
        elif self._dragging == "end":
            value = max(self._startValue, min(value, self._maximum))
            if value != self._endValue:
                self._endValue = value
                self.update()
                self.rangeChanged.emit(self._startValue, self._endValue)

    def _startInlineEdit(self, handle: str) -> None:
        if self._lineEdit is not None:
            self._onInlineEditFinished()

        self._editingHandle = handle
        value = self._startValue if handle == "start" else self._endValue
        hx = self._toPixelX(value)

        self._lineEdit = LineEdit(self)
        setFont(self._lineEdit, LABEL_FONT_SIZE)
        self._lineEdit.setFixedSize(56, LABEL_HEIGHT)
        self._lineEdit.setText(self._formatter(value))
        self._lineEdit.selectAll()
        self._lineEdit.move(int(max(0, min(self.width() - 56, hx - 28))), 0)
        self._lineEdit.show()
        self._lineEdit.setFocus()
        self._lineEdit.editingFinished.connect(self._onInlineEditFinished)

    def _onInlineEditFinished(self) -> None:
        if self._lineEdit is None:
            return
        text = self._lineEdit.text()
        handle = self._editingHandle

        self._lineEdit.deleteLater()
        self._lineEdit = None
        self._editingHandle = None

        try:
            value = self._parser(text)
        except (ValueError, TypeError):
            self.update()
            return

        if handle == "start":
            value = max(self._minimum, min(value, self._endValue))
            self._startValue = value
        else:
            value = max(self._startValue, min(value, self._maximum))
            self._endValue = value

        self.update()
        self.rangeChanged.emit(self._startValue, self._endValue)
