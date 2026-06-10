from typing import Callable
from urllib.parse import urlparse

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

_SCHEMES = ("http", "https", "ftp", "ftps", "magnet")


def parseDownloadableUrls(text: str) -> list[str]:
    """从剪贴板文本里挑出像可下载链接的行（每行一个）。只做轻量 scheme 判断，
    真正能不能下交给引擎在 add 时匹配——这样 daemon 模式下 gui 不依赖已加载的 packs。"""
    urls: list[str] = []
    for line in text.splitlines():
        url = line.strip()
        if not url:
            continue
        try:
            parsed = urlparse(url)
        except ValueError:
            continue
        if parsed.scheme not in _SCHEMES:
            continue
        if parsed.scheme == "magnet":
            if parsed.query:  # magnet 没 netloc，靠 ?xt=... 判
                urls.append(url)
        elif parsed.netloc and parsed.geturl() == url:  # 有主机名且不被 urlparse 改写（排除带尾巴的脏串）
            urls.append(url)
    return urls


class ClipboardWatcher(QObject):
    """盯系统剪贴板，复制到可下载链接时回调通知 owner。纯桌面 gui 功能（headless/Android 不涉及）。
    owner 用构造时注入的 callback 收结果，不走 Signal（单订阅者）。"""

    def __init__(self, onUrls: Callable[[list[str]], None], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._onUrls = onUrls
        self._enabled = False
        self._lastUrls: tuple[str, ...] = ()  # 去重：部分平台 dataChanged 会就同一内容连发

    def setEnabled(self, enabled: bool) -> None:
        if enabled == self._enabled:
            return
        self._enabled = enabled
        clipboard = QApplication.clipboard()
        if enabled:
            clipboard.dataChanged.connect(self._onDataChanged)
        else:
            clipboard.dataChanged.disconnect(self._onDataChanged)

    def _onDataChanged(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard.ownsClipboard():  # 是我们自己写进去的（如复制链接），别反弹
            return
        urls = parseDownloadableUrls(clipboard.text())
        if not urls:
            return
        current = tuple(urls)
        if current == self._lastUrls:
            return
        self._lastUrls = current
        self._onUrls(urls)
