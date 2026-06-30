from PySide6.QtCore import QSize
from qfluentwidgets import TreeView


class AutoSizingTreeView(TreeView):
    def __init__(self, parent=None, minimumVisibleRows: int = 1, maximumVisibleRows: int = 10):
        super().__init__(parent)
        self._minimumVisibleRows = minimumVisibleRows
        self._maximumVisibleRows = maximumVisibleRows

    def sizeHint(self) -> QSize:
        model = self.model()
        rowCount = model.rowCount() if model else 0
        visibleRows = max(self._minimumVisibleRows, min(rowCount, self._maximumVisibleRows))
        rowHeight = self.sizeHintForRow(0) if rowCount > 0 else 30
        headerHeight = self.header().height() if self.header().isVisible() else 0
        return QSize(super().sizeHint().width(), headerHeight + visibleRows * rowHeight + 4)
