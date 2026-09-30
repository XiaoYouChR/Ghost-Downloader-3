from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from loguru import logger

from app.models.task import Task, TaskOptions

class ClipboardListener(QObject):
    tasksDetected = Signal(list)

    def __init__(self, coroutineRunner, featureService, parent=None):
        super().__init__(parent)
        self._coroutineRunner = coroutineRunner
        self._featureService = featureService
        self._matchPassive = featureService.matchPassive
        self._clipboard = None
        self._enabled = False
        self._selfCopied = False
        self._lastUrls: tuple[str, ...] = ()
        self._parsing: set[str] = set()
        self._results: list[Task] = []

    def setUrls(self, urls: list[str]) -> None:
        if self._enabled:
            self._selfCopied = True
        QApplication.clipboard().setText("\n".join(urls))

    def setEnabled(self, enabled: bool) -> None:
        if self._clipboard is None:
            self._clipboard = QApplication.clipboard()

        if enabled and not self._enabled:
            self._clipboard.dataChanged.connect(self._onDataChanged)
        elif not enabled and self._enabled:
            self._clipboard.dataChanged.disconnect(self._onDataChanged)
            for workId in self._parsing:
                self._coroutineRunner.cancel(workId)
            self._parsing.clear()
            self._results.clear()
        self._enabled = enabled

    def _onDataChanged(self) -> None:
        if self._selfCopied:
            self._selfCopied = False
            return

        urls = self._downloadableUrls()
        if not urls:
            return

        if QApplication.platformName() == "wayland":
            snapshot = tuple(urls)
            if snapshot == self._lastUrls:
                return
            self._lastUrls = snapshot

        self._parse(urls)

    def _parse(self, urls: list[str]) -> None:
        for url in urls:
            self._submit(url)

    def _submit(self, url: str) -> None:
        workId = ""

        def settle(task=None, error=None):
            if workId:
                self._parsing.discard(workId)
            if not self._enabled:
                self._results.clear()
                return
            if error:
                logger.warning("剪贴板链接解析失败 {}: {}", url, error)
            else:
                self._results.append(task)
            if self._parsing:
                return
            results, self._results = self._results, []
            if results:
                self.tasksDetected.emit(results)

        try:
            workId = self._coroutineRunner.submit(
                self._featureService.parse(TaskOptions.fromOptions({"url": url})),
                done=lambda task: settle(task=task),
                failed=lambda error: settle(error=error),
            )
        except Exception as error:
            settle(error=error)
            return
        self._parsing.add(workId)

    def _downloadableUrls(self) -> list[str]:
        candidates = [line.strip() for line in self._clipboard.text().splitlines()]
        candidates += [qurl.toLocalFile().strip() for qurl in self._clipboard.mimeData().urls() if qurl.isLocalFile()]

        urls: list[str] = []
        for candidate in dict.fromkeys(filter(None, candidates)):
            url = self._toTorrentUrl(candidate)
            if url is None:
                if Path(candidate).is_file():
                    continue
                url = candidate
            try:
                parsed = urlparse(url)
            except ValueError as error:
                logger.warning("跳过无效剪贴板链接 {}: {}", url, error)
                continue
            if parsed.path.lower().endswith((".html", ".htm")):
                continue
            if not parsed.scheme or parsed.geturl() != url:
                continue
            if self._matchPassive(url) and url not in urls:
                urls.append(url)
        return urls

    def _toTorrentUrl(self, text: str) -> str | None:
        # 资源管理器“复制为路径”带引号
        text = text.strip('"')  
        if not text.lower().endswith(".torrent"):
            return None
        if "://" in text:
            return text
        path = Path(text)
        if not path.is_file():
            return None
        return path.as_uri()
