from collections.abc import Callable

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, Slot


class UserAgentModel(QAbstractListModel):
    """设置页 UA 管理列表：增删自定义 UA，改动经注入的 onChanged 落盘（测试注入 fake，免碰 cfg）。
    通用列表编辑器的范式——后续分类规则编辑器照此。"""

    NameRole = Qt.ItemDataRole.UserRole + 1
    ValueRole = Qt.ItemDataRole.UserRole + 2

    def __init__(self, items: list, onChanged: Callable[[list], None] | None = None, parent=None) -> None:
        super().__init__(parent)
        self._items = [dict(item) for item in items]
        self._onChanged = onChanged

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def data(self, index, role):
        if not index.isValid():
            return None
        item = self._items[index.row()]
        if role == self.NameRole:
            return item["name"]
        if role == self.ValueRole:
            return item["value"]
        return None

    def roleNames(self):
        return {self.NameRole: b"name", self.ValueRole: b"value"}

    @Slot(str, str)
    def add(self, name: str, value: str) -> None:
        if not name.strip() or not value.strip():
            return  # 空名/空值不收
        row = len(self._items)
        self.beginInsertRows(QModelIndex(), row, row)
        self._items.append({"name": name.strip(), "value": value.strip()})
        self.endInsertRows()
        self._persist()

    @Slot(int)
    def removeAt(self, row: int) -> None:
        if not 0 <= row < len(self._items):
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._items[row]
        self.endRemoveRows()
        self._persist()

    def _persist(self) -> None:
        if self._onChanged is not None:
            self._onChanged([dict(item) for item in self._items])
