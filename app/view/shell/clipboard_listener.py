from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

class ClipboardListener(QObject):
    urlsDetected = Signal(list)

    def __init__(self, matchPassive, parent=None):
        super().__init__(parent)
        self._matchPassive = matchPassive
        self._clipboard = None
        self._enabled = False
        self._selfCopied = False
        self._lastUrls: tuple[str, ...] = ()

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

        self.urlsDetected.emit(urls)

    def _downloadableUrls(self) -> list[str]:
        return [url for line in self._clipboard.text().splitlines()
                if (url := line.strip()) and self._matchPassive(url)]
