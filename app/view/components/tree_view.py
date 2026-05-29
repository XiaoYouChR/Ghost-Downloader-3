from PySide6.QtCore import QAbstractItemModel, QModelIndex, QSize
from PySide6.QtWidgets import QSizePolicy
from qfluentwidgets import TreeView


class AutoSizingTreeView(TreeView):
    def __init__(
        self,
        parent=None,
        minimumVisibleRows: int = 5,
        maximumVisibleRows: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._minimumVisibleRows = minimumVisibleRows
        self._maximumVisibleRows = maximumVisibleRows
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.expanded.connect(self.updateGeometry)
        self.collapsed.connect(self.updateGeometry)

    def setModel(self, model: QAbstractItemModel | None) -> None:
        super().setModel(model)
        if model is not None:
            model.rowsInserted.connect(self.updateGeometry)
            model.rowsRemoved.connect(self.updateGeometry)
            model.modelReset.connect(self.updateGeometry)

    def _visibleRowCount(self) -> int:
        rowCount = self._countVisibleRows(QModelIndex())
        if self._maximumVisibleRows is None:
            return rowCount
        return min(rowCount, self._maximumVisibleRows)

    def _countVisibleRows(self, parent: QModelIndex) -> int:
        model = self.model()
        if model is None:
            return 0
        count = 0
        for row in range(model.rowCount(parent)):
            index = model.index(row, 0, parent)
            count += 1
            if self.isExpanded(index):
                count += self._countVisibleRows(index)
        return count

    def _rowHeight(self) -> int:
        if self.model() and self.model().rowCount() > 0:
            h = self.sizeHintForRow(0)
            if h > 0:
                return h
        return self.fontMetrics().height() + 4

    def _viewFrameHeight(self) -> int:
        margins = self.contentsMargins()
        viewportMargins = self.viewportMargins()
        header = self.header()
        headerHeight = header.height() if header and not header.isHidden() else 0
        return (
            margins.top()
            + margins.bottom()
            + viewportMargins.top()
            + viewportMargins.bottom()
            + self.frameWidth() * 2
            + headerHeight
        )

    def _sizeHintForRowCount(self, rowCount: int) -> QSize:
        height = self._viewFrameHeight() + self._rowHeight() * rowCount
        return QSize(super().sizeHint().width(), height)

    def minimumSizeHint(self) -> QSize:
        return self._sizeHintForRowCount(
            min(self._minimumVisibleRows, self._visibleRowCount())
        )

    def maximumSizeHint(self) -> QSize:
        return self._sizeHintForRowCount(self._visibleRowCount())

    def sizeHint(self) -> QSize:
        return self.maximumSizeHint().expandedTo(self.minimumSizeHint())
