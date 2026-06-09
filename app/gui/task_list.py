from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
)


class TaskItem:
    """屏幕上的一个任务。持有 engine 同步来的字段；pack 之后子类化加字段。"""

    def __init__(self, task: dict) -> None:
        self._task = task

    @property
    def taskId(self) -> str:
        return self._task["taskId"]

    @property
    def title(self) -> str:
        return self._task["title"]

    @property
    def status(self) -> str:
        return self._task["status"]

    @property
    def running(self) -> bool:
        return self.status == "RUNNING"

    def update(self, task: dict) -> None:
        self._task = task


class TaskList(QAbstractListModel):
    """界面上的任务列表，喂给 QML 的 ListView。"""

    IdRole = Qt.ItemDataRole.UserRole + 1
    TitleRole = Qt.ItemDataRole.UserRole + 2
    StatusRole = Qt.ItemDataRole.UserRole + 3
    RunningRole = Qt.ItemDataRole.UserRole + 4

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[TaskItem] = []

    def reset(self, tasks: list[dict]) -> None:
        self.beginResetModel()
        self._items = [TaskItem(task) for task in tasks]
        self.endResetModel()

    def add(self, item: TaskItem) -> None:
        row = len(self._items)
        self.beginInsertRows(QModelIndex(), row, row)
        self._items.append(item)
        self.endInsertRows()

    def update(self, task: dict) -> None:
        for row, item in enumerate(self._items):
            if item.taskId == task["taskId"]:
                item.update(task)
                index = self.index(row, 0)
                self.dataChanged.emit(index, index)
                return

    def remove(self, taskId: str) -> None:
        for row, item in enumerate(self._items):
            if item.taskId == taskId:
                self.beginRemoveRows(QModelIndex(), row, row)
                del self._items[row]
                self.endRemoveRows()
                return

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        item = self._items[index.row()]
        if role == TaskList.IdRole:
            return item.taskId
        if role == TaskList.TitleRole:
            return item.title
        if role == TaskList.StatusRole:
            return item.status
        if role == TaskList.RunningRole:
            return item.running
        return None

    def roleNames(self) -> dict:
        return {
            TaskList.IdRole: b"taskId",
            TaskList.TitleRole: b"title",
            TaskList.StatusRole: b"status",
            TaskList.RunningRole: b"running",
        }


class TaskFilter(QSortFilterProxyModel):
    """按关键词筛任务标题，喂给 QML 的 ListView。子串匹配走内置过滤；TaskList 不动。"""

    keywordChanged = Signal()

    def __init__(self, source: TaskList, parent=None) -> None:
        super().__init__(parent)
        self.setSourceModel(source)
        self.setFilterRole(TaskList.TitleRole)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._word = ""

    def _keyword(self) -> str:
        return self._word

    def _setKeyword(self, keyword: str) -> None:
        if keyword == self._word:
            return
        self._word = keyword
        self.keywordChanged.emit()
        self.setFilterFixedString(keyword)

    keyword = Property(str, _keyword, _setKeyword, notify=keywordChanged)
