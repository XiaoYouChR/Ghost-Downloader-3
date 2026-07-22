from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QSizePolicy, QWidget
from qfluentwidgets import (
    Action, BodyLabel, FluentIcon, IconWidget, LineEdit, RoundMenu, Slider,
    ToolTipFilter, TransparentToolButton, isDarkTheme,
)

from app.config.cfg import cfg

PROFILE_FAMILY_LABELS = {
    "chrome": "Chrome", "edge": "Edge", "firefox": "Firefox",
    "safari": "Safari", "okhttp": "OkHttp",
}


def toProfileLabel(value: str) -> str:
    if value in {"", "auto"}:
        return QCoreApplication.translate("ClientProfileCard", "自动（匹配来源）")
    if value == "raw":
        return QCoreApplication.translate("ClientProfileCard", "不模拟（原样发送）")
    if value in PROFILE_FAMILY_LABELS:
        return QCoreApplication.translate("ClientProfileCard", "{0}（最新）").format(
            PROFILE_FAMILY_LABELS[value]
        )
    head = value.rstrip("0123456789_")
    version = value[len(head):].replace("_", ".")
    return f"{head} {version}" if version else value


def buildProfileMenu(parent, onPick, *, includeAuto: bool = True) -> RoundMenu:
    from app.client import profileFamilies, profileVersions

    menu = RoundMenu(parent=parent)

    if includeAuto:
        action = Action(FluentIcon.ROBOT, toProfileLabel("auto"), parent)
        action.triggered.connect(lambda checked=False: onPick("auto"))
        menu.addAction(action)
    else:
        action = Action(toProfileLabel(""), parent)
        action.triggered.connect(lambda checked=False: onPick(""))
        menu.addAction(action)

    rawAction = Action(FluentIcon.CANCEL, toProfileLabel("raw"), parent)
    rawAction.triggered.connect(lambda checked=False: onPick("raw"))
    menu.addAction(rawAction)

    menu.addSeparator()

    for family in profileFamilies():
        submenu = RoundMenu(PROFILE_FAMILY_LABELS.get(family, family), parent)
        latest = Action(toProfileLabel(family), parent)
        latest.triggered.connect(lambda checked=False, v=family: onPick(v))
        submenu.addAction(latest)
        submenu.addSeparator()
        for name in profileVersions(family):
            action = Action(toProfileLabel(name), parent)
            action.triggered.connect(lambda checked=False, v=name: onPick(v))
            submenu.addAction(action)
        menu.addMenu(submenu)

    return menu


class OptionCard(QWidget):

    def options(self) -> dict:
        return {}

    def reset(self) -> None:
        pass

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(0, 0, self.width(), 1, QColor(0, 0, 0, 96 if isDarkTheme() else 24))


class OutputFolderCard(OptionCard):

    def __init__(self, parent=None, *, initial: Path | None = None):
        super().__init__(parent)
        from app.view.components.editors import FolderPicker

        self.setFixedHeight(50)
        self.iconWidget = IconWidget(FluentIcon.DOWNLOAD, self)
        self.iconWidget.setFixedSize(16, 16)
        self.titleLabel = BodyLabel(self.tr("选择下载路径"), self)
        self.folderPicker = FolderPicker(self)
        self.folderPicker.setPath(str(initial) if initial else cfg.downloadFolder.value)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.folderPicker.refreshHistory()

    def _initLayout(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 5, 24, 5)
        layout.setSpacing(15)
        layout.addWidget(self.iconWidget)
        layout.addWidget(self.titleLabel)
        layout.addStretch(1)
        layout.addWidget(self.folderPicker, stretch=3)

    def _bind(self) -> None:
        self.folderPicker.pathChanged.connect(self.folderPicker.saveHistory)

    def options(self) -> dict:
        return {"outputFolder": Path(self.folderPicker.path())}

    def reset(self) -> None:
        self.folderPicker.setPath(cfg.downloadFolder.value)


class SubworkerCountCard(OptionCard):

    def __init__(self, parent=None, *, initial: int = 0):
        super().__init__(parent)
        self.setFixedHeight(50)
        self.iconWidget = IconWidget(FluentIcon.CLOUD, self)
        self.iconWidget.setFixedSize(16, 16)
        self.titleLabel = BodyLabel(self.tr("预分配线程数"), self)
        self.slider = Slider(Qt.Orientation.Horizontal, self)
        self.valueLabel = BodyLabel(self)

        value = initial or cfg.preBlockNum.value
        self.slider.setMinimumWidth(268)
        self.slider.setSingleStep(1)
        self.slider.setRange(*cfg.preBlockNum.range)
        self.slider.setValue(value)
        self.valueLabel.setNum(value)
        self.slider.valueChanged.connect(self._onValueChanged)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 5, 24, 5)
        layout.setSpacing(15)
        layout.addWidget(self.iconWidget)
        layout.addWidget(self.titleLabel)
        layout.addStretch(1)
        layout.addWidget(self.valueLabel)
        layout.addSpacing(6)
        layout.addWidget(self.slider)
        layout.addSpacing(16)

    def options(self) -> dict:
        return {"subworkerCount": self.slider.value()}

    def reset(self) -> None:
        self.slider.setValue(cfg.preBlockNum.value)

    def _onValueChanged(self, value: int) -> None:
        self.valueLabel.setNum(value)
        self.valueLabel.adjustSize()


class ClientProfileCard(OptionCard):

    def __init__(self, parent=None, *, initial: str = "", initialUserAgent: str = ""):
        from qfluentwidgets import DropDownPushButton
        from app.config.cfg import cfg

        super().__init__(parent)
        self.setFixedHeight(50)
        self._value = initial
        self._userAgent = initialUserAgent
        self.iconWidget = IconWidget(FluentIcon.ROBOT, self)
        self.iconWidget.setFixedSize(16, 16)
        self.titleLabel = BodyLabel(self.tr("模拟身份"), self)

        label = self._presetLabelFor(initial, initialUserAgent) or toProfileLabel(initial)
        self.button = DropDownPushButton(label, self)
        self.button.setMinimumWidth(200)

        menu = buildProfileMenu(self, self._onPick, includeAuto=True)

        presets = cfg.identityPresets.value
        if presets:
            menu.addSeparator()
            for preset in presets:
                action = Action(preset["name"], self)
                action.triggered.connect(
                    lambda _=False, p=preset: self._onPickPreset(p))
                menu.addAction(action)

        self.button.setMenu(menu)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 5, 24, 5)
        layout.setSpacing(15)
        layout.addWidget(self.iconWidget)
        layout.addWidget(self.titleLabel)
        layout.addStretch(1)
        layout.addWidget(self.button)

    def options(self) -> dict:
        result = {"clientProfile": self._value}
        if self._userAgent:
            result["userAgent"] = self._userAgent
        return result

    def reset(self) -> None:
        self._value = ""
        self._userAgent = ""
        self.button.setText(toProfileLabel(""))

    def _onPick(self, value: str) -> None:
        self._value = value
        self._userAgent = ""
        self.button.setText(toProfileLabel(value))

    def _onPickPreset(self, preset: dict) -> None:
        self._value = preset["clientProfile"]
        self._userAgent = preset["userAgent"]
        self.button.setText(preset["name"])

    def _presetLabelFor(self, clientProfile: str, userAgent: str) -> str:
        if not userAgent:
            return ""
        from app.config.cfg import cfg
        for preset in cfg.identityPresets.value:
            if preset["clientProfile"] == clientProfile and preset["userAgent"] == userAgent:
                return preset["name"]
        return ""


class UrlEditCard(OptionCard):

    def __init__(self, parent=None, *, initial: str = ""):
        super().__init__(parent)
        self.setFixedHeight(50)
        self._initial = initial
        self.iconWidget = IconWidget(FluentIcon.LINK, self)
        self.iconWidget.setFixedSize(16, 16)
        self.titleLabel = BodyLabel(self.tr("下载链接"), self)
        self.urlEdit = LineEdit(self)
        self.urlEdit.setText(initial)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 5, 24, 5)
        layout.setSpacing(15)
        layout.addWidget(self.iconWidget)
        layout.addWidget(self.titleLabel)
        layout.addStretch(1)
        layout.addWidget(self.urlEdit, stretch=3)

    def options(self) -> dict:
        return {"url": self.urlEdit.text().strip()}

    def reset(self) -> None:
        self.urlEdit.setText(self._initial)


class HeadersEditCard(OptionCard):

    def __init__(self, parent=None, *, initial: dict[str, str] | None = None):
        from app.view.components.editors import HeadersEditor

        super().__init__(parent)
        self.iconWidget = IconWidget(FluentIcon.GLOBE, self)
        self.iconWidget.setFixedSize(16, 16)
        self.titleLabel = BodyLabel(self.tr("请求标头"), self)
        self.resetButton = TransparentToolButton(FluentIcon.SYNC, self)
        self.headersEditor = HeadersEditor(self)

        self.vBoxLayout = QVBoxLayout(self)
        self.titleRowLayout = QHBoxLayout()

        self._initWidget()
        self._initLayout()
        self._bind()

        self.headersEditor.setHeaders(initial or dict(cfg.defaultRequestHeaders.value))

    def _initWidget(self) -> None:
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.resetButton.setToolTip(self.tr("恢复默认请求标头"))
        self.resetButton.installEventFilter(ToolTipFilter(self.resetButton))

    def _initLayout(self) -> None:
        self.titleRowLayout.setSpacing(15)
        self.titleRowLayout.addWidget(self.iconWidget)
        self.titleRowLayout.addWidget(self.titleLabel)
        self.titleRowLayout.addStretch(1)
        self.titleRowLayout.addWidget(self.resetButton)

        self.vBoxLayout.setContentsMargins(24, 10, 24, 12)
        self.vBoxLayout.setSpacing(10)
        self.vBoxLayout.addLayout(self.titleRowLayout)
        self.vBoxLayout.addWidget(self.headersEditor)

    def _bind(self) -> None:
        self.resetButton.clicked.connect(self.reset)

    def options(self) -> dict:
        return {"headers": self.headersEditor.headers()}

    def reset(self) -> None:
        self.headersEditor.setHeaders(dict(cfg.defaultRequestHeaders.value))
