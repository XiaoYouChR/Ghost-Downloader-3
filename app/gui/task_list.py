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

from app.supports.utils import toReadableSize, toReadableTime

# 文件类型 → Fluent 图标名（纯展示映射，图标资源名只 gui 认识，不下到引擎）
_TYPE_ICONS = {
    "zip": "ic_fluent_folder_zip_20_filled", "7z": "ic_fluent_folder_zip_20_filled",
    "rar": "ic_fluent_folder_zip_20_filled", "tar": "ic_fluent_folder_zip_20_filled",
    "gz": "ic_fluent_folder_zip_20_filled",
    "mp4": "ic_fluent_video_clip_20_filled", "mkv": "ic_fluent_video_clip_20_filled",
    "avi": "ic_fluent_video_clip_20_filled", "mov": "ic_fluent_video_clip_20_filled",
    "flv": "ic_fluent_video_clip_20_filled", "webm": "ic_fluent_video_clip_20_filled",
    "ts": "ic_fluent_video_clip_20_filled",
    "mp3": "ic_fluent_music_note_2_20_filled", "flac": "ic_fluent_music_note_2_20_filled",
    "wav": "ic_fluent_music_note_2_20_filled", "aac": "ic_fluent_music_note_2_20_filled",
    "ogg": "ic_fluent_music_note_2_20_filled",
    "jpg": "ic_fluent_image_20_filled", "jpeg": "ic_fluent_image_20_filled",
    "png": "ic_fluent_image_20_filled", "gif": "ic_fluent_image_20_filled",
    "webp": "ic_fluent_image_20_filled", "bmp": "ic_fluent_image_20_filled",
    "exe": "ic_fluent_window_apps_20_filled", "msi": "ic_fluent_window_apps_20_filled",
    "apk": "ic_fluent_window_apps_20_filled", "dmg": "ic_fluent_window_apps_20_filled",
    "pdf": "ic_fluent_document_pdf_20_filled",
}
_DEFAULT_TYPE_ICON = "ic_fluent_document_20_filled"


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
    def chips(self) -> list:
        # pack 专属展示串列表（BT 的 Peers/Seeds、M3U8 的直播态）；引擎算好过缝，核心原样渲染
        return self._task.get("chips") or []

    @property
    def typeIcon(self) -> str:
        ext = self.title.rsplit(".", 1)[-1].lower() if "." in self.title else ""
        return _TYPE_ICONS.get(ext, _DEFAULT_TYPE_ICON)

    @property
    def leftTimeText(self) -> str:
        speed = self._task.get("speed", 0)
        remaining = self._task.get("fileSize", 0) - self._task.get("received", 0)
        if self.status != "RUNNING" or speed <= 0 or remaining <= 0:
            return "--"
        return toReadableTime(int(remaining / speed))

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
    ChipsRole = Qt.ItemDataRole.UserRole + 14
    TypeIconRole = Qt.ItemDataRole.UserRole + 15
    LeftTimeTextRole = Qt.ItemDataRole.UserRole + 16

    # 角色 → (QML 绑定名, TaskItem 属性)。data()/roleNames 都由这单一来源生成，
    # 加一个展示字段 = 加一行 + TaskItem 上一个属性。selected 是模型级（不在 item 上），属性记 None 单独处理。
    _FIELDS = {
        IdRole: ("taskId", "taskId"),
        TitleRole: ("title", "title"),
        StatusRole: ("status", "status"),
        RunningRole: ("running", "running"),
        ProgressRole: ("progress", "progress"),
        SpeedTextRole: ("speedText", "speedText"),
        ProgressTextRole: ("progressText", "progressText"),
        CompletedRole: ("completed", "completed"),
        OutputRole: ("output", "output"),
        CreatedRole: ("created", "createdAt"),
        SelectedRole: ("selected", None),
        FileCountRole: ("fileCount", "fileCount"),
        ErrorRole: ("error", "errorText"),
        ChipsRole: ("chips", "chips"),
        TypeIconRole: ("typeIcon", "typeIcon"),
        LeftTimeTextRole: ("leftTimeText", "leftTimeText"),
    }

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
        if role == TaskList.SelectedRole:
            return item.taskId in self._selected
        field = TaskList._FIELDS.get(role)
        return getattr(item, field[1]) if field and field[1] else None

    def roleNames(self) -> dict:
        return {role: name.encode() for role, (name, _) in TaskList._FIELDS.items()}

    def filesOf(self, taskId: str) -> list:
        row = self._rowOf(taskId)
        return self._items[row].files if row is not None else []


class TaskFilter(QSortFilterProxyModel):
    """按关键词 + 状态筛任务，新任务排最前，喂给 QML 的 ListView。TaskList 不动。"""

    keywordChanged = Signal()
    statusFilterChanged = Signal()
    sortModeChanged = Signal()

    def __init__(self, source: TaskList, parent=None) -> None:
        super().__init__(parent)
        self._word = ""
        self._statusFilter = "all"  # all | active | complete —— 先于 setSourceModel，过滤回调要用
        self._sortMode = "time"  # time | name
        self.setSourceModel(source)
        self.setSortRole(TaskList.CreatedRole)
        self.sort(0, Qt.SortOrder.DescendingOrder)  # 新任务排最前

    def _keyword(self) -> str:
        return self._word

    def _setKeyword(self, keyword: str) -> None:
        if keyword == self._word:
            return
        self._word = keyword
        self.keywordChanged.emit()
        self.invalidate()

    keyword = Property(str, _keyword, _setKeyword, notify=keywordChanged)

    def _getStatusFilter(self) -> str:
        return self._statusFilter

    def _setStatusFilter(self, value: str) -> None:
        if value == self._statusFilter:
            return
        self._statusFilter = value
        self.statusFilterChanged.emit()
        self.invalidate()

    statusFilter = Property(str, _getStatusFilter, _setStatusFilter, notify=statusFilterChanged)

    def _getSortMode(self) -> str:
        return self._sortMode

    def _setSortMode(self, mode: str) -> None:
        if mode == self._sortMode:
            return
        self._sortMode = mode
        self.sortModeChanged.emit()
        if mode == "name":
            self.setSortRole(TaskList.TitleRole)
            self.sort(0, Qt.SortOrder.AscendingOrder)
        else:
            self.setSortRole(TaskList.CreatedRole)
            self.sort(0, Qt.SortOrder.DescendingOrder)  # 新任务排最前

    sortMode = Property(str, _getSortMode, _setSortMode, notify=sortModeChanged)

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:
        index = self.sourceModel().index(row, 0, parent)
        title = self.sourceModel().data(index, TaskList.TitleRole) or ""
        if self._word and self._word.lower() not in title.lower():
            return False
        if self._statusFilter != "all":
            completed = bool(self.sourceModel().data(index, TaskList.CompletedRole))
            if self._statusFilter == "complete":
                return completed
            return not completed  # active：藏掉已完成
        return True
