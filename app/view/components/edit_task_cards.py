from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    Action,
    BodyLabel,
    ComboBox,
    FluentIcon,
    IconWidget,
    LineEdit,
    RoundMenu,
    TransparentToolButton,
    isDarkTheme,
)

from app.supports.config import cfg, defaultHeaders
from app.view.components.cards import ParseSettingCard
from app.view.components.editors import AutoSizingEdit


class UrlEditCard(ParseSettingCard):
    def __init__(self, icon, title: str, parent=None, *, initial: str = "") -> None:
        super().__init__(icon, title, parent)
        # super 在 initCustomWidget 里已建好 urlEdit, 这里只是把初值灌进去
        self.urlEdit.setText(initial)

    def initCustomWidget(self) -> None:
        self.urlEdit = LineEdit(self)
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.urlEdit.setPlaceholderText(self.tr("下载链接"))

    def _initLayout(self) -> None:
        self.hBoxLayout.addWidget(self.urlEdit, stretch=3)

    def _bind(self) -> None:
        # LineEdit.textChanged 带 str, payloadChanged 是 0 参, 直连会 TypeError
        self.urlEdit.textChanged.connect(lambda _: self.payloadChanged.emit())

    @property
    def payload(self) -> dict[str, Any]:
        return {"url": self.urlEdit.text().strip()}


class _VerticalCardBase(QWidget):
    payloadChanged = Signal()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(0, 0, 0, 96 if isDarkTheme() else 48))
        painter.drawLine(self.rect().topLeft(), self.rect().topRight())


class HeadersEditCard(_VerticalCardBase):
    def __init__(self, icon, title: str, parent=None, *, initial: dict | None = None) -> None:
        super().__init__(parent)

        # instant widget
        self.iconWidget = IconWidget(icon, self)
        self.titleLabel = BodyLabel(title, self)
        self.uaInsertButton = TransparentToolButton(FluentIcon.ROBOT, self)
        self.uaInsertMenu = RoundMenu(parent=self.uaInsertButton)
        self.resetButton = TransparentToolButton(FluentIcon.SYNC, self)
        self.headersEdit = AutoSizingEdit(self, minimumVisibleLines=6, maximumVisibleLines=14)

        # instant layout
        self.vBoxLayout = QVBoxLayout(self)
        self.titleRowLayout = QHBoxLayout()

        self._initWidget()
        self._initLayout()
        self._bind()

        self.headersEdit.setPlainText(self._toText(initial or defaultHeaders()))
        self._refreshUaMenu()

    def _initWidget(self) -> None:
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.iconWidget.setFixedSize(16, 16)
        self.uaInsertButton.setToolTip(self.tr("插入 User-Agent 预设"))
        self.resetButton.setToolTip(self.tr("恢复默认请求标头"))
        self.headersEdit.setPlaceholderText(self.tr("每行一个 Name: Value"))

    def _initLayout(self) -> None:
        self.titleRowLayout.setSpacing(15)
        self.titleRowLayout.addWidget(self.iconWidget)
        self.titleRowLayout.addWidget(self.titleLabel)
        self.titleRowLayout.addStretch(1)
        self.titleRowLayout.addWidget(self.uaInsertButton)
        self.titleRowLayout.addWidget(self.resetButton)

        self.vBoxLayout.setContentsMargins(24, 10, 24, 12)
        self.vBoxLayout.setSpacing(10)
        self.vBoxLayout.addLayout(self.titleRowLayout)
        self.vBoxLayout.addWidget(self.headersEdit)

    def _bind(self) -> None:
        self.headersEdit.textChanged.connect(self.payloadChanged.emit)
        self.uaInsertButton.clicked.connect(self._showUaMenu)
        self.resetButton.clicked.connect(self._reset)
        cfg.userAgents.valueChanged.connect(self._refreshUaMenu)

    def _refreshUaMenu(self) -> None:
        self.uaInsertMenu.clear()
        for preset in cfg.userAgents.value:
            name = preset.get("name", "")
            value = preset.get("value", "")
            if not name or not value:
                continue
            action = Action(name, self)
            action.triggered.connect(lambda checked=False, v=value: self._insertUserAgent(v))
            self.uaInsertMenu.addAction(action)

    def _showUaMenu(self) -> None:
        if not self.uaInsertMenu.actions():
            return
        bottomLeft = self.uaInsertButton.mapToGlobal(
            self.uaInsertButton.rect().bottomLeft()
        )
        self.uaInsertMenu.exec(bottomLeft)

    def _insertUserAgent(self, value: str) -> None:
        lines = self.headersEdit.toPlainText().splitlines()
        replaced = False
        for i, line in enumerate(lines):
            name, separator, _ = line.partition(":")
            if separator and name.strip().lower() == "user-agent":
                lines[i] = f"user-agent: {value}"
                replaced = True
                break
        if not replaced:
            lines.insert(0, f"user-agent: {value}")
        self.headersEdit.setPlainText("\n".join(lines))

    def _reset(self) -> None:
        self.headersEdit.setPlainText(self._toText(defaultHeaders()))

    def _toText(self, headers: dict) -> str:
        return "\n".join(f"{name}: {value}" for name, value in headers.items())

    def _toDict(self, text: str) -> dict:
        # HTTP header 大小写不敏感; 统一小写避免 "Cookie" / "cookie" 同时存在
        result: dict[str, str] = {}
        for line in text.splitlines():
            name, separator, value = line.partition(":")
            if not separator:
                continue
            key = name.strip().lower()
            if not key:
                continue
            result[key] = value.strip()
        return result

    @property
    def payload(self) -> dict[str, Any]:
        return {"headers": self._toDict(self.headersEdit.toPlainText())}


class ProxiesEditCard(_VerticalCardBase):
    # 故意不提供"自动检测系统代理"选项: HttpPack.parse 已经 snapshot 过 getProxies()
    # 写进 task.proxies, EditDialog 再做一次 auto resolve, 当 cfg.proxyServer == Off
    # 时拿回来是 None, 跟"不使用代理"撞了, 下次重开会显示 Off — 语义错位

    _OFF = "off"
    _CUSTOM = "custom"
    _PROTOCOLS = ("http", "https", "ftp")

    def __init__(self, icon, title: str, parent=None, *, initial: dict | None = None) -> None:
        super().__init__(parent)

        # instant widget
        self.iconWidget = IconWidget(icon, self)
        self.titleLabel = BodyLabel(title, self)
        self.modeCombo = ComboBox(self)
        self.urlEdit = LineEdit(self)

        # instant layout
        self.vBoxLayout = QVBoxLayout(self)
        self.titleRowLayout = QHBoxLayout()

        self._initWidget()
        self._initLayout()
        self._bind()

        initialUrl = self._toInitialUrl(initial)
        if initialUrl:
            self.modeCombo.setCurrentIndex(1)
            self.urlEdit.setText(initialUrl)
        else:
            self.modeCombo.setCurrentIndex(0)
        self.urlEdit.setVisible(bool(initialUrl))

    def _initWidget(self) -> None:
        self.iconWidget.setFixedSize(16, 16)
        self.urlEdit.setPlaceholderText(self.tr("http://host:port 或 socks5://host:port"))
        self.modeCombo.addItem(self.tr("不使用代理"), userData=self._OFF)
        self.modeCombo.addItem(self.tr("自定义代理"), userData=self._CUSTOM)

    def _initLayout(self) -> None:
        self.titleRowLayout.setSpacing(15)
        self.titleRowLayout.addWidget(self.iconWidget)
        self.titleRowLayout.addWidget(self.titleLabel)
        self.titleRowLayout.addStretch(1)

        self.vBoxLayout.setContentsMargins(24, 10, 24, 12)
        self.vBoxLayout.setSpacing(10)
        self.vBoxLayout.addLayout(self.titleRowLayout)
        self.vBoxLayout.addWidget(self.modeCombo)
        self.vBoxLayout.addWidget(self.urlEdit)

    def _bind(self) -> None:
        self.modeCombo.currentIndexChanged.connect(self._onModeChanged)
        self.urlEdit.textChanged.connect(lambda _: self.payloadChanged.emit())

    def _onModeChanged(self, _index: int) -> None:
        self.urlEdit.setVisible(self.modeCombo.currentData() == self._CUSTOM)
        self.payloadChanged.emit()

    def _toInitialUrl(self, initial: dict | None) -> str:
        if not initial:
            return ""
        for value in initial.values():
            if value:
                return str(value)
        return ""

    @property
    def payload(self) -> dict[str, Any]:
        if self.modeCombo.currentData() == self._OFF:
            return {"proxies": None}
        url = self.urlEdit.text().strip()
        if not url:
            return {"proxies": None}
        return {"proxies": {protocol: url for protocol in self._PROTOCOLS}}
