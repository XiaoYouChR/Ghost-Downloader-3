from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, TYPE_CHECKING

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


class TaskDraft(QObject):
    parsingBusyChanged = Signal(bool)
    parseSucceeded = Signal(str, object)
    parseFailed = Signal(str, str)
    itemsChanged = Signal()
    itemsCleared = Signal()
    taskConfirmed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[DraftItem] = []
        self._baseOptions: dict[str, Any] = {}

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
        self._baseOptions = options
        for item in self._items:
            if item.task is not None:
                item.task.setOptions(self._buildOptions(item))

    def setUrlCategory(self, url: str, categoryId: str) -> None:
        for item in self._items:
            if item.url == url:
                item.categoryOverride = categoryId
                break

    def setUrls(self, urls: list[str]) -> None:
        from app.models.task import TaskOptions
        from app.services.coroutine_runner import coroutineRunner
        from app.services.feature_service import featureService

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
                    coroutineRunner.cancel(item.parseId)
                    item.parseId = ""
            for url in urls[newStart:newEnd]:
                item = DraftItem(url=url)
                try:
                    options = TaskOptions.fromOptions({**self._baseOptions, "url": url})
                    parseId = coroutineRunner.submit(
                        featureService.parse(options),
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
        from app.services.coroutine_runner import coroutineRunner

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
                    coroutineRunner.cancel(item.parseId)
                    item.parseId = ""
            else:
                newUrls.append(url)
                item = DraftItem(url=url)
                self._items.append(item)
                byUrl[url] = item

            task.setOptions(self._buildOptions(item))
            item.task = task
            self.parseSucceeded.emit(url, task)

        self.parsingBusyChanged.emit(self._isParsing())
        self.itemsChanged.emit()
        return newUrls

    def confirm(self) -> None:
        from app.services.coroutine_runner import coroutineRunner

        for item in self._items:
            if item.task is not None:
                item.task.setOptions(self._buildOptions(item))
                self.taskConfirmed.emit(item.task)
            elif item.parseId:
                item.confirmedOptions = self._buildOptions(item)

        for item in self._items:
            if item.parseId and item.confirmedOptions is None:
                coroutineRunner.cancel(item.parseId)
                item.parseId = ""

        self._items.clear()
        self.parsingBusyChanged.emit(self._isParsing())
        self.itemsCleared.emit()

    def clear(self) -> None:
        from app.services.coroutine_runner import coroutineRunner
        for item in self._items:
            if item.parseId:
                coroutineRunner.cancel(item.parseId)
                item.parseId = ""
        self._items.clear()
        self.itemsCleared.emit()
        self.parsingBusyChanged.emit(self._isParsing())

    def _buildOptions(self, item: DraftItem) -> dict[str, Any]:
        options = self._baseOptions.copy()
        if item.categoryOverride is not None:
            options["category"] = item.categoryOverride
        return options

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
        task.setOptions(self._buildOptions(item))
        item.task = task
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
