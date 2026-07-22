from __future__ import annotations

from typing import Callable
from urllib.parse import urlparse

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from loguru import logger


class ClipboardListener(QObject):
    urlsDetected = Signal(list)

    def __init__(self, matchPassive: Callable[[str], bool],
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._matchPassive = matchPassive
        self._clipboard = None
        self._enabled = False
        self._lastUrls: tuple[str, ...] = ()

    def setEnabled(self, enabled: bool) -> None:
        if self._clipboard is None:
            self._clipboard = QApplication.clipboard()

        if enabled and not self._enabled:
            self._clipboard.dataChanged.connect(self._onDataChanged)
        elif not enabled and self._enabled:
            self._clipboard.dataChanged.disconnect(self._onDataChanged)
        self._enabled = enabled

    def _onDataChanged(self) -> None:
        if self._clipboard.ownsClipboard():
            return

        urls = self._downloadableUrls()
        if not urls:
            return

        if QApplication.platformName() == "wayland":
            snapshot = tuple(urls)
            if snapshot == self._lastUrls:
                return
            self._lastUrls = snapshot

        self.urlsDetected.emit(urls)

    def _downloadableUrls(self) -> list[str]:
        urls: list[str] = []
        for line in self._clipboard.text().splitlines():
            url = line.strip()
            if not url:
                continue
            try:
                parsed = urlparse(url)
            except ValueError as error:
                logger.warning("跳过无效剪贴板链接 {}: {}", url, error)
                continue
            if not parsed.scheme or parsed.geturl() != url:
                continue
            if self._matchPassive(url):
                urls.append(url)
        return urls
