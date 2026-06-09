from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt


class TaskItem:
    """屏幕上的一个任务。tracer 阶段只装标题；pack 之后子类化加字段。"""

    def __init__(self, task: dict) -> None:
        self.taskId = task["taskId"]
        self.title = task["title"]


class TaskList(QAbstractListModel):
    """界面上的任务列表，喂给 QML 的 ListView。"""

    TitleRole = Qt.ItemDataRole.UserRole + 1

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[TaskItem] = []

    def add(self, item: TaskItem) -> None:
        row = len(self._items)
        self.beginInsertRows(QModelIndex(), row, row)
        self._items.append(item)
        self.endInsertRows()

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        item = self._items[index.row()]
        if role == TaskList.TitleRole:
            return item.title
        return None

    def roleNames(self) -> dict:
        return {TaskList.TitleRole: b"title"}
