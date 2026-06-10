from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, Slot

from app.supports.utils import toReadableSize


class FileSelection(QAbstractListModel):
    """选择文件对话框的模型：列任务里的文件，勾选哪些要下。selectedIndexes 交回 engine。"""

    PathRole = Qt.ItemDataRole.UserRole + 1
    SizeTextRole = Qt.ItemDataRole.UserRole + 2
    SelectedRole = Qt.ItemDataRole.UserRole + 3

    def __init__(self, files: list[dict], parent=None) -> None:
        super().__init__(parent)
        self._files = [dict(file) for file in files]

    @Slot(int)
    def toggle(self, row: int) -> None:
        self._files[row]["selected"] = not self._files[row].get("selected", True)
        index = self.index(row, 0)
        self.dataChanged.emit(index, index)

    def selectedIndexes(self) -> list[int]:
        return [file["index"] for file in self._files if file.get("selected", True)]

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._files)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        file = self._files[index.row()]
        if role == FileSelection.PathRole:
            return file.get("relativePath", "")
        if role == FileSelection.SizeTextRole:
            return toReadableSize(file.get("size", 0))
        if role == FileSelection.SelectedRole:
            return file.get("selected", True)
        return None

    def roleNames(self) -> dict:
        return {
            FileSelection.PathRole: b"path",
            FileSelection.SizeTextRole: b"sizeText",
            FileSelection.SelectedRole: b"selected",
        }
