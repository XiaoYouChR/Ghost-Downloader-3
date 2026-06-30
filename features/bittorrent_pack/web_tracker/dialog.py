from urllib.parse import urlsplit

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    FluentIcon,
    InfoBar,
    LineEdit,
    MessageBoxBase,
    PrimaryPushButton,
    SubtitleLabel,
    TransparentToolButton,
)

from app.config.cfg import cfg
from app.view.components.editors import AutoSizingEdit
from ..config import bittorrentConfig
from .schema import DEFAULT_WEB_TRACKER_SOURCE


TRACKER_SCHEMES = {"http", "https", "udp", "ws", "wss"}


class WebTrackerSourceCard(QWidget):
    removed = Signal(object)

    def __init__(self, url: str = "", cachedCount: int | None = None, parent=None):
        super().__init__(parent)
        self.urlEdit = LineEdit(self)
        self.statusLabel = BodyLabel(self)
        self.deleteButton = TransparentToolButton(FluentIcon.CLOSE, self)
        self.hBoxLayout = QHBoxLayout(self)

        self._initWidget(url, cachedCount)
        self._initLayout()
        self._bind()

    @property
    def url(self) -> str:
        value = self.urlEdit.text().strip()
        if not value:
            return ""
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        return value

    def setCachedCount(self, count: int | None):
        if count is None:
            self.statusLabel.setText(self.tr("未拉取"))
        else:
            self.statusLabel.setText(self.tr("{0} 条").format(count))

    def _initWidget(self, url: str, cachedCount: int | None):
        self.urlEdit.setText(url)
        self.urlEdit.setPlaceholderText(DEFAULT_WEB_TRACKER_SOURCE)
        self.setCachedCount(cachedCount)

    def _initLayout(self):
        self.hBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.hBoxLayout.setSpacing(8)
        self.hBoxLayout.addWidget(self.urlEdit, 1)
        self.hBoxLayout.addWidget(self.statusLabel)
        self.hBoxLayout.addWidget(self.deleteButton)

    def _bind(self):
        self.deleteButton.clicked.connect(lambda: self.removed.emit(self))


class WebTrackerDialog(MessageBoxBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.sourceHeaderLabel = SubtitleLabel(self.tr("Tracker 源"), self.widget)
        self.addSourceButton = PrimaryPushButton(FluentIcon.ADD, self.tr("添加"), self.widget)
        self.sourceContainer = QWidget(self.widget)
        self.customLabel = SubtitleLabel(self.tr("自定义 Tracker"), self.widget)
        self.customEdit = AutoSizingEdit(self.widget)
        self.sourceHeaderLayout = QHBoxLayout()
        self.sourceLayout = QVBoxLayout(self.sourceContainer)
        self._sourceCards: list[WebTrackerSourceCard] = []

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self):
        self.widget.setMinimumWidth(720)
        self.yesButton.setText(self.tr("保存并刷新"))
        self.cancelButton.setText(self.tr("取消"))
        customText = bittorrentConfig.webTrackerCustomList.value
        customTrackers = [
            t for t in customText.split()
            if urlsplit(t).scheme.lower() in TRACKER_SCHEMES and urlsplit(t).netloc
        ]
        self.customEdit.setPlaceholderText(self.tr("每行一个 tracker URL，不会被源刷新覆盖"))
        self.customEdit.setPlainText("\n".join(customTrackers))
        for url in list(bittorrentConfig.webTrackerSources.value):
            self._addSourceCard(url)

    def _initLayout(self):
        self.sourceHeaderLayout.setContentsMargins(0, 0, 0, 0)
        self.sourceHeaderLayout.addWidget(self.sourceHeaderLabel)
        self.sourceHeaderLayout.addStretch(1)
        self.sourceHeaderLayout.addWidget(self.addSourceButton)

        self.sourceLayout.setContentsMargins(0, 0, 0, 0)
        self.sourceLayout.setSpacing(8)

        self.viewLayout.addLayout(self.sourceHeaderLayout)
        self.viewLayout.addWidget(self.sourceContainer)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.customLabel)
        self.viewLayout.addWidget(self.customEdit)

    def _bind(self):
        self.addSourceButton.clicked.connect(lambda: self._addSourceCard())

    def validate(self) -> bool:
        urls: list[str] = []
        for card in self._sourceCards:
            normalized = card.url
            if not normalized:
                InfoBar.error(
                    self.tr("源地址无效"),
                    self.tr("请输入有效的 HTTP/HTTPS 地址"),
                    parent=self,
                )
                card.urlEdit.setFocus()
                return False
            urls.append(normalized)

        uniqueUrls = list(dict.fromkeys(urls))
        cfg.set(bittorrentConfig.webTrackerSources, uniqueUrls)

        customTrackers = [
            t for t in self.customEdit.toPlainText().split()
            if urlsplit(t).scheme.lower() in TRACKER_SCHEMES and urlsplit(t).netloc
        ]
        cfg.set(bittorrentConfig.webTrackerCustomList, "\n".join(customTrackers))
        return True

    def _addSourceCard(self, url: str = ""):
        cache = dict(bittorrentConfig.webTrackerSourceCache.value)
        cachedCount = len(cache[url]) if url in cache else None
        card = WebTrackerSourceCard(url, cachedCount, self.sourceContainer)
        card.removed.connect(self._onSourceRemoved)
        self.sourceLayout.addWidget(card)
        self._sourceCards.append(card)

    def _onSourceRemoved(self, card: WebTrackerSourceCard):
        self._sourceCards.remove(card)
        self.sourceLayout.removeWidget(card)
        card.deleteLater()
