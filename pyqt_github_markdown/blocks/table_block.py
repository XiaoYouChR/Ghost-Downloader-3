from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QWidget


class TableBlock(QWidget):
    def __init__(
        self,
        headers: list[str],
        rows: list[list[str]],
        aligns: list[Qt.AlignmentFlag],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._headers = headers
        self._rows = rows
        self._aligns = aligns
        # instant layout
        self._grid = QGridLayout(self)
        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
        self.setObjectName("table")

    def _initLayout(self) -> None:
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(0)
        for col, cellHtml in enumerate(self._headers):
            self._grid.addWidget(self._cell(cellHtml, self._aligns[col], "header", False), 0, col)
        for row, cells in enumerate(self._rows, start=1):
            for col, cellHtml in enumerate(cells):
                cell = self._cell(cellHtml, self._aligns[col], "cell", row % 2 == 1)
                self._grid.addWidget(cell, row, col)

    def _cell(self, cellHtml: str, align: Qt.AlignmentFlag, role: str, odd: bool) -> QLabel:
        label = QLabel(cellHtml)
        label.setTextFormat(Qt.RichText)
        label.setProperty("role", role)
        label.setProperty("odd", odd)
        label.setAlignment(align | Qt.AlignVCenter)
        label.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse
        )
        return label
