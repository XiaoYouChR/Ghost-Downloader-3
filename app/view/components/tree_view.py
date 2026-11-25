from __future__ import annotations

import sys

from PySide6.QtCore import QAbstractAnimation, QModelIndex, QPoint, QSize, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QAbstractItemView, QSizePolicy
from qfluentwidgets import TreeView

from app.view.components.scroll_area import SCROLL_BAR_WIDTH


class AutoSizingTreeView(TreeView):
    def __init__(self, parent=None, minimumVisibleRows: int = 1,
                 maximumVisibleRows: int | None = None):
        super().__init__(parent)
        self._minimumVisibleRows = minimumVisibleRows
        self._maximumVisibleRows = maximumVisibleRows
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.expanded.connect(self.updateGeometry)
        self.collapsed.connect(self.updateGeometry)
        if sys.platform == "win32":
            # 走 SmoothScrollBar 动画才能跟上高刷屏帧间隔，并经由 valueChanged 对齐物理像素
            self.scrollDelagate.useAni = True
            smoothBar = self.scrollDelagate.vScrollBar
            nativeBar = self.verticalScrollBar()
            smoothBar.valueChanged.disconnect(nativeBar.setValue)
            smoothBar.valueChanged.connect(self._onScrollValueChanged)
            nativeBar.valueChanged.connect(self._onNativeScrollChanged)

    if sys.platform == "win32":
        def updateGeometries(self) -> None:
            super().updateGeometries()
            # 滚动条盖住视口时 Qt 不平移
            margins = self.viewportMargins()
            if margins.right() != SCROLL_BAR_WIDTH:
                self.setViewportMargins(margins.left(), margins.top(), SCROLL_BAR_WIDTH, margins.bottom())

        def scrollContentsBy(self, dx: int, dy: int) -> None:
            if dx == 0 and dy != 0 and self.state() != QAbstractItemView.State.EditingState:
                viewport = self.viewport()
                # QTreeView 按像素滚动默认整视口重画；只在平移时声明不透明，让 Qt 只重画新露出的条带
                viewport.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
                viewport.scroll(0, dy)
                viewport.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
                pos = viewport.mapFromGlobal(QCursor.pos())
                if viewport.rect().contains(pos):
                    for point in (pos, QPoint(pos.x(), pos.y() + dy)):
                        index = self.indexAt(point)
                        if index.isValid():
                            rect = self.visualRect(index)
                            viewport.update(0, rect.y(), viewport.width(), rect.height())
                return
            super().scrollContentsBy(dx, dy)

        def _onScrollValueChanged(self, value: int) -> None:
            # 滚动距离是整物理像素时 Qt 才平移，滚到底时不对齐
            bar = self.verticalScrollBar()
            if value < bar.maximum():
                ratio = self.devicePixelRatioF()
                value -= value % next((n for n in (1, 2, 4) if (n * ratio).is_integer()), 1)
            bar.setValue(value)

        def _onNativeScrollChanged(self, value: int) -> None:
            smoothBar = self.scrollDelagate.vScrollBar
            if smoothBar.ani.state() != QAbstractAnimation.State.Running:
                smoothBar.resetValue(value)

    def setModel(self, model):
        super().setModel(model)
        if model is not None:
            model.rowsInserted.connect(self.updateGeometry)
            model.rowsRemoved.connect(self.updateGeometry)
            model.modelReset.connect(self.updateGeometry)

    def _visibleRowCount(self) -> int:
        return self._countVisible(QModelIndex())

    def _countVisible(self, parent: QModelIndex) -> int:
        model = self.model()
        if model is None:
            return 0
        count = 0
        for row in range(model.rowCount(parent)):
            count += 1
            index = model.index(row, 0, parent)
            if self.isExpanded(index):
                count += self._countVisible(index)
        return count

    def _rowHeight(self) -> int:
        if self.model() and self.model().rowCount() > 0:
            return max(self.sizeHintForRow(0), 1)
        return 30

    def _contentWidth(self) -> int:
        header = self.header()
        if header.count() == 0:
            return super().sizeHint().width()
        columns = sum(max(self.sizeHintForColumn(i), header.sectionSizeHint(i)) for i in range(header.count()))
        return columns + self.frameWidth() * 2 + self.verticalScrollBar().sizeHint().width()

    def _heightForRows(self, count: int) -> int:
        headerHeight = self.header().height() if self.header().isVisible() else 0
        return headerHeight + count * self._rowHeight() + 4

    def minimumSizeHint(self) -> QSize:
        rows = min(self._minimumVisibleRows, self._visibleRowCount())
        return QSize(super().minimumSizeHint().width(), self._heightForRows(rows))

    def sizeHint(self) -> QSize:
        count = self._visibleRowCount()
        if self._maximumVisibleRows is not None:
            count = min(count, self._maximumVisibleRows)
        return QSize(self._contentWidth(), self._heightForRows(count)).expandedTo(self.minimumSizeHint())
