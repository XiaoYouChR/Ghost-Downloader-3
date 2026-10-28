from __future__ import annotations

from PySide6.QtCore import QModelIndex, QSize
from PySide6.QtWidgets import QSizePolicy
from qfluentwidgets import TreeView


class AutoSizingTreeView(TreeView):
    def __init__(self, parent=None, minimumVisibleRows: int = 1,
                 maximumVisibleRows: int | None = None):
        super().__init__(parent)
        self._minimumVisibleRows = minimumVisibleRows
        self._maximumVisibleRows = maximumVisibleRows
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.expanded.connect(self.updateGeometry)
        self.collapsed.connect(self.updateGeometry)

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
