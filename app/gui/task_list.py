from pathlib import Path

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
    Slot,
)

from app.supports.utils import toReadableSize


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

    @property
    def completed(self) -> bool:
        return self.status == "COMPLETED"

    @property
    def output(self) -> str:
        path = self._task.get("path", "")
        return str(Path(path) / self.title) if path else ""

    @property
    def createdAt(self) -> int:
        return self._task.get("createdAt", 0)

    @property
    def files(self) -> list:
        return self._task.get("files") or []

    @property
    def fileCount(self) -> int:
        return len(self.files)

    @property
    def errorText(self) -> str:
        return self._task.get("error", "")

    @property
    def metaText(self) -> str:
        return self._task.get("meta", "")

    @property
    def progress(self) -> float:
        return self._task.get("progress", 0.0)

    @property
    def speedText(self) -> str:
        speed = self._task.get("speed", 0)
        return f"{toReadableSize(speed)}/s" if speed else ""

    @property
    def progressText(self) -> str:
        fileSize = self._task.get("fileSize", 0)
        if fileSize <= 0:
            return ""
        return f"{toReadableSize(self._task.get('received', 0))} / {toReadableSize(fileSize)}"

    def update(self, task: dict) -> None:
        self._task = task


class TaskList(QAbstractListModel):
    """界面上的任务列表，喂给 QML 的 ListView。"""

    IdRole = Qt.ItemDataRole.UserRole + 1
    TitleRole = Qt.ItemDataRole.UserRole + 2
    StatusRole = Qt.ItemDataRole.UserRole + 3
    RunningRole = Qt.ItemDataRole.UserRole + 4
    ProgressRole = Qt.ItemDataRole.UserRole + 5
    SpeedTextRole = Qt.ItemDataRole.UserRole + 6
    ProgressTextRole = Qt.ItemDataRole.UserRole + 7
    CompletedRole = Qt.ItemDataRole.UserRole + 8
    OutputRole = Qt.ItemDataRole.UserRole + 9
    CreatedRole = Qt.ItemDataRole.UserRole + 10
    SelectedRole = Qt.ItemDataRole.UserRole + 11
    FileCountRole = Qt.ItemDataRole.UserRole + 12
    ErrorRole = Qt.ItemDataRole.UserRole + 13
    MetaRole = Qt.ItemDataRole.UserRole + 14

    selectionModeChanged = Signal()
    selectedCountChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[TaskItem] = []
        self._selected: set[str] = set()
        self._selectionMode = False

    def _isSelectionMode(self) -> bool:
        return self._selectionMode

    @Slot(bool)
    def setSelectionMode(self, on: bool) -> None:
        if on == self._selectionMode:
            return
        self._selectionMode = on
        if not on:
            self._selected.clear()
        self.selectionModeChanged.emit()
        self.selectedCountChanged.emit()
        self._refreshAll()

    selectionMode = Property(bool, _isSelectionMode, notify=selectionModeChanged)

    def _count(self) -> int:
        return len(self._selected)

    selectedCount = Property(int, _count, notify=selectedCountChanged)

    @Slot(str)
    def toggleSelect(self, taskId: str) -> None:
        if taskId in self._selected:
            self._selected.discard(taskId)
        else:
            self._selected.add(taskId)
        self.selectedCountChanged.emit()
        self._refresh(taskId)

    @Slot()
    def selectAll(self) -> None:
        self._selected = {item.taskId for item in self._items}
        self.selectedCountChanged.emit()
        self._refreshAll()

    def selectedIds(self) -> list[str]:
        return list(self._selected)

    def _rowOf(self, taskId: str) -> int | None:
        for row, item in enumerate(self._items):
            if item.taskId == taskId:
                return row
        return None

    def _refreshAll(self) -> None:
        if self._items:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._items) - 1, 0))

    def _refresh(self, taskId: str) -> None:
        row = self._rowOf(taskId)
        if row is not None:
            self.dataChanged.emit(self.index(row, 0), self.index(row, 0))

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
        row = self._rowOf(task["taskId"])
        if row is None:
            return
        self._items[row].update(task)
        index = self.index(row, 0)
        self.dataChanged.emit(index, index)

    def remove(self, taskId: str) -> None:
        row = self._rowOf(taskId)
        if row is None:
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._items[row]
        self.endRemoveRows()

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
        if role == TaskList.ProgressRole:
            return item.progress
        if role == TaskList.SpeedTextRole:
            return item.speedText
        if role == TaskList.ProgressTextRole:
            return item.progressText
        if role == TaskList.CompletedRole:
            return item.completed
        if role == TaskList.OutputRole:
            return item.output
        if role == TaskList.CreatedRole:
            return item.createdAt
        if role == TaskList.SelectedRole:
            return item.taskId in self._selected
        if role == TaskList.FileCountRole:
            return item.fileCount
        if role == TaskList.ErrorRole:
            return item.errorText
        if role == TaskList.MetaRole:
            return item.metaText
        return None

    def roleNames(self) -> dict:
        return {
            TaskList.IdRole: b"taskId",
            TaskList.TitleRole: b"title",
            TaskList.StatusRole: b"status",
            TaskList.RunningRole: b"running",
            TaskList.ProgressRole: b"progress",
            TaskList.SpeedTextRole: b"speedText",
            TaskList.ProgressTextRole: b"progressText",
            TaskList.CompletedRole: b"completed",
            TaskList.OutputRole: b"output",
            TaskList.CreatedRole: b"created",
            TaskList.SelectedRole: b"selected",
            TaskList.FileCountRole: b"fileCount",
            TaskList.ErrorRole: b"error",
            TaskList.MetaRole: b"meta",
        }

    def filesOf(self, taskId: str) -> list:
        row = self._rowOf(taskId)
        return self._items[row].files if row is not None else []


class TaskFilter(QSortFilterProxyModel):
    """按关键词筛任务标题，喂给 QML 的 ListView。子串匹配走内置过滤；TaskList 不动。"""

    keywordChanged = Signal()

    def __init__(self, source: TaskList, parent=None) -> None:
        super().__init__(parent)
        self.setSourceModel(source)
        self.setFilterRole(TaskList.TitleRole)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setSortRole(TaskList.CreatedRole)
        self.sort(0, Qt.SortOrder.DescendingOrder)  # 新任务排最前
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
