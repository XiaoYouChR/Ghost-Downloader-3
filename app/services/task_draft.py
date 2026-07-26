from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

from PySide6.QtCore import QObject, Signal
from loguru import logger

if TYPE_CHECKING:
    from app.models.task import Task


@dataclass
class DraftItem:
    url: str
    parseId: str = ""
    task: Task | None = None
    categoryOverride: str | None = None
    confirmedOptions: dict | None = None
    changes: list[Callable[[], None]] = field(default_factory=list)
    shouldDeleteFiles: bool = False
    isDiscarded: bool = False
    isConfirmed: bool = False


class TaskDraft(QObject):
    parsingBusyChanged = Signal(bool)
    parseSucceeded = Signal(str, object)
    parseFailed = Signal(str, str)
    itemsChanged = Signal()
    itemsCleared = Signal()
    taskConfirmed = Signal(object)
    taskUpdated = Signal(str, object)

    def __init__(
        self, coroutineRunner, featureService, taskService, categoryService, config, parent=None,
    ):
        super().__init__(parent)
        self._coroutineRunner = coroutineRunner
        self._featureService = featureService
        self._taskService = taskService
        self._categoryService = categoryService
        self._config = config
        self._items: list[DraftItem] = []
        self._stoppingItems: dict[Task, DraftItem] = {}
        self._baseOptions: dict[str, Any] = {}
        self._taskService.taskCancelled.connect(self._onTaskCancelled)
        self._config.shouldStartAheadDownload.valueChanged.connect(self._onAheadSettingChanged)

    def urls(self) -> list[str]:
        return [item.url for item in self._items]

    def taskByUrl(self, url: str) -> Task | None:
        for item in self._items:
            if item.url == url:
                return item.task
        return None

    def canConfirm(self) -> bool:
        return any(item.parseId or item.task is not None for item in self._items)

    def setBaseOptions(self, options: dict) -> None:
        if options == self._baseOptions:
            return
        self._baseOptions = options
        for item in self._items:
            if item.task is not None:
                self.setOptions(item.url, self._buildOptions(item))

    def setUrlCategory(self, url: str, categoryId: str) -> None:
        for item in self._items:
            if item.url == url:
                item.categoryOverride = categoryId
                if item.task is not None:
                    self.setOptions(url, self._buildOptions(item))
                break

    def setOptions(self, url: str, options: dict) -> None:
        for item in self._items:
            if item.url != url or item.task is None:
                continue
            task = item.task
            self.update(
                url,
                lambda: task.setOptions(options),
                shouldDeleteFiles=not task.canReuseOptions(options),
            )
            return

    def update(
        self,
        url: str,
        change: Callable[[], None] | None,
        shouldDeleteFiles: bool,
    ) -> None:
        for item in self._items:
            if item.url != url or item.task is None or item.isDiscarded:
                continue
            if change is not None:
                item.changes.append(change)
            item.shouldDeleteFiles |= shouldDeleteFiles
            if item.task in self._stoppingItems:
                return
            self._stoppingItems[item.task] = item
            self._taskService.cancel(item.task)
            return

    def setUrls(self, urls: list[str]) -> None:
        from app.models.task import TaskOptions

        previous = self._items
        previousUrls = [item.url for item in previous]
        nextItems: list[DraftItem] = []
        matcher = SequenceMatcher(a=previousUrls, b=urls, autojunk=False)

        for tag, oldStart, oldEnd, newStart, newEnd in matcher.get_opcodes():
            if tag == "equal":
                nextItems.extend(previous[oldStart:oldEnd])
                continue
            for item in previous[oldStart:oldEnd]:
                if item.parseId:
                    self._coroutineRunner.cancel(item.parseId)
                    item.parseId = ""
                elif item.task is not None:
                    self._delete(item)
            for url in urls[newStart:newEnd]:
                item = DraftItem(url=url)
                try:
                    options = TaskOptions.fromOptions({**self._baseOptions, "url": url})
                    parseId = self._coroutineRunner.submit(
                        self._featureService.parse(options),
                        done=self._onParsed,
                        failed=self._onParseFailed,
                        item=item,
                    )
                except Exception as e:
                    logger.opt(exception=e).error("提交解析请求失败 {}", url)
                    self.parseFailed.emit(url, str(e) or repr(e))
                    nextItems.append(item)
                    continue
                item.parseId = parseId
                nextItems.append(item)

        self._items = nextItems
        self.parsingBusyChanged.emit(self._isParsing())
        self.itemsChanged.emit()

    def addParsedTasks(self, tasks: list[Task]) -> list[str]:
        if not tasks:
            return []

        byUrl = {item.url: item for item in self._items}
        newUrls: list[str] = []

        for task in tasks:
            url = task.url
            item = byUrl.get(url)
            if item is not None:
                if item.task is not None:
                    continue
                if item.parseId:
                    self._coroutineRunner.cancel(item.parseId)
                    item.parseId = ""
            else:
                newUrls.append(url)
                item = DraftItem(url=url)
                self._items.append(item)
                byUrl[url] = item

            self._setTask(item, task)
            self.parseSucceeded.emit(url, task)

        self.parsingBusyChanged.emit(self._isParsing())
        self.itemsChanged.emit()
        return newUrls

    def confirm(self) -> None:
        for item in self._items:
            if item.task is not None:
                if item.task in self._stoppingItems:
                    item.isConfirmed = True
                else:
                    self.taskConfirmed.emit(item.task)
            elif item.parseId:
                item.confirmedOptions = self._buildOptions(item)

        for item in self._items:
            if item.parseId and item.confirmedOptions is None:
                self._coroutineRunner.cancel(item.parseId)
                item.parseId = ""

        self._items.clear()
        self.parsingBusyChanged.emit(self._isParsing())
        self.itemsCleared.emit()

    def clear(self) -> None:
        for item in self._items:
            if item.parseId:
                self._coroutineRunner.cancel(item.parseId)
                item.parseId = ""
            elif item.task is not None:
                self._delete(item)
        self._items.clear()
        self.itemsCleared.emit()
        self.parsingBusyChanged.emit(self._isParsing())

    def _buildOptions(self, item: DraftItem) -> dict[str, Any]:
        options = self._baseOptions.copy()
        if item.categoryOverride is not None:
            options["category"] = item.categoryOverride
            baseFolder = Path(options.get("outputFolder", self._config.downloadFolder.value))
            if (
                self._config.isCategoryEnabled.value
                and item.categoryOverride
                and baseFolder == Path(self._config.downloadFolder.value)
            ):
                folder = self._categoryService.folderOf(item.categoryOverride)
                if folder:
                    options["outputFolder"] = Path(folder)
        return options

    def _setTask(self, item: DraftItem, task: Task) -> None:
        if self._config.isCategoryEnabled.value and item.categoryOverride is None:
            item.categoryOverride = self._categoryService.categoryOf(task) or ""
        task.setOptions(self._buildOptions(item))
        task.deduplicateFilename()
        item.task = task
        if self._config.shouldStartAheadDownload.value:
            self._taskService.start(task)

    def _delete(self, item: DraftItem) -> None:
        item.isDiscarded = True
        item.changes.clear()
        item.shouldDeleteFiles = True
        if item.task in self._stoppingItems:
            return
        self._stoppingItems[item.task] = item
        self._taskService.cancel(item.task)

    def _onTaskCancelled(self, task: Task) -> None:
        item = self._stoppingItems.pop(task, None)
        if item is None:
            return
        if item.isDiscarded:
            try:
                task.deleteFiles()
            except Exception as e:
                logger.opt(exception=e).error("failed to delete task {}", task.name)
            return

        changes = item.changes
        shouldDeleteFiles = item.shouldDeleteFiles
        item.changes = []
        item.shouldDeleteFiles = False

        try:
            if shouldDeleteFiles:
                task.deleteFiles()
                task.reset()
            for change in changes:
                change()
            if shouldDeleteFiles:
                task.deduplicateFilename()
        except Exception as e:
            logger.opt(exception=e).error("failed to update task {}", task.name)
            task.reset()

        self.taskUpdated.emit(item.url, task)
        if item.isConfirmed:
            self.taskConfirmed.emit(task)
        elif self._config.shouldStartAheadDownload.value:
            from app.models.task import TaskStatus
            if task.status != TaskStatus.COMPLETED:
                self._taskService.start(task)

    def _onAheadSettingChanged(self, isEnabled: bool) -> None:
        for item in self._items:
            if item.task is None or item.isDiscarded or item.isConfirmed:
                continue
            if isEnabled:
                if item.task not in self._stoppingItems:
                    from app.models.task import TaskStatus
                    if item.task.status != TaskStatus.COMPLETED:
                        self._taskService.start(item.task)
            else:
                self.update(item.url, None, shouldDeleteFiles=True)

    def _isParsing(self) -> bool:
        return any(item.parseId for item in self._items)

    def _onParsed(self, task: Task, item: DraftItem) -> None:
        if item.confirmedOptions is not None:
            task.setOptions(item.confirmedOptions)
            item.confirmedOptions = None
            self.taskConfirmed.emit(task)
            return

        if not item.parseId:
            return

        item.parseId = ""
        self._setTask(item, task)
        self.parseSucceeded.emit(item.url, task)
        self.parsingBusyChanged.emit(self._isParsing())
        self.itemsChanged.emit()

    def _onParseFailed(self, error: str, item: DraftItem) -> None:
        if item.confirmedOptions is not None:
            item.confirmedOptions = None
            logger.warning("后台确认任务解析失败: {}", error)
            return

        if not item.parseId:
            return

        item.parseId = ""
        self.parseFailed.emit(item.url, error)
        logger.warning("解析任务失败 {}: {}", item.url, error)
        self.parsingBusyChanged.emit(self._isParsing())
