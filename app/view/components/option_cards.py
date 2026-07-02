from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QSizePolicy, QWidget
from qfluentwidgets import (
    Action, BodyLabel, FluentIcon, IconWidget, LineEdit, Slider,
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


class OptionCard(QWidget):

    def options(self) -> dict:
        return {}

    def reset(self) -> None:
        pass

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QColor(0, 0, 0, 96 if isDarkTheme() else 80))
        painter.drawLine(self.rect().topLeft(), self.rect().topRight())


class OutputFolderCard(OptionCard):

    def __init__(self, parent=None, *, initial: Path | None = None):
        super().__init__(parent)
        self.setFixedHeight(50)
        self.iconWidget = IconWidget(FluentIcon.DOWNLOAD, self)
        self.iconWidget.setFixedSize(16, 16)
        self.titleLabel = BodyLabel(self.tr("选择下载路径"), self)
        self.pathEdit = LineEdit(self)
        self.pathEdit.setReadOnly(True)
        self.pathEdit.setText(str(initial) if initial else cfg.downloadFolder.value)
        browseAction = Action(FluentIcon.FOLDER, "", self)
        browseAction.triggered.connect(self._onBrowse)
        self.pathEdit.addAction(browseAction)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 5, 24, 5)
        layout.setSpacing(15)
        layout.addWidget(self.iconWidget)
        layout.addWidget(self.titleLabel)
        layout.addStretch(1)
        layout.addWidget(self.pathEdit, stretch=3)

    def options(self) -> dict:
        return {"outputFolder": Path(self.pathEdit.text())}

    def reset(self) -> None:
        self.pathEdit.setText(cfg.downloadFolder.value)

    def _onBrowse(self) -> None:
        path = Path(self.pathEdit.text())
        startDir = str(path if path.exists() else path.parent)
        selected = QFileDialog.getExistingDirectory(self, self.tr("选择下载路径"), startDir)
        if selected:
            self.pathEdit.setText(selected)


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

    def __init__(self, parent=None, *, initial: str = ""):
        from qfluentwidgets import DropDownPushButton, RoundMenu
        from app.client import profileFamilies, profileVersions

        super().__init__(parent)
        self.setFixedHeight(50)
        self._value = initial
        self.iconWidget = IconWidget(FluentIcon.ROBOT, self)
        self.iconWidget.setFixedSize(16, 16)
        self.titleLabel = BodyLabel(self.tr("模拟身份"), self)
        self.button = DropDownPushButton(toProfileLabel(initial), self)
        self.button.setMinimumWidth(200)

        menu = RoundMenu(parent=self)
        for value, icon in (("auto", FluentIcon.ROBOT), ("raw", FluentIcon.CANCEL)):
            action = Action(icon, toProfileLabel(value), self)
            action.triggered.connect(lambda _=False, v=value: self._onPick(v))
            menu.addAction(action)
        for family in profileFamilies():
            submenu = RoundMenu(PROFILE_FAMILY_LABELS.get(family, family), self)
            latest = Action(toProfileLabel(family), self)
            latest.triggered.connect(lambda _=False, v=family: self._onPick(v))
            submenu.addAction(latest)
            submenu.addSeparator()
            for name in profileVersions(family):
                action = Action(toProfileLabel(name), self)
                action.triggered.connect(lambda _=False, v=name: self._onPick(v))
                submenu.addAction(action)
            menu.addMenu(submenu)
        self.button.setMenu(menu)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 5, 24, 5)
        layout.setSpacing(15)
        layout.addWidget(self.iconWidget)
        layout.addWidget(self.titleLabel)
        layout.addStretch(1)
        layout.addWidget(self.button)

    def options(self) -> dict:
        return {"clientProfile": self._value}

    def reset(self) -> None:
        self._value = ""
        self.button.setText(toProfileLabel(""))

    def _onPick(self, value: str) -> None:
        self._value = value
        self.button.setText(toProfileLabel(value))


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
        from app.view.components.editors import AutoSizingEdit

        super().__init__(parent)
        self.iconWidget = IconWidget(FluentIcon.GLOBE, self)
        self.iconWidget.setFixedSize(16, 16)
        self.titleLabel = BodyLabel(self.tr("请求标头"), self)
        self.resetButton = TransparentToolButton(FluentIcon.SYNC, self)
        self.headersEdit = AutoSizingEdit(self, minimumVisibleLines=4, maximumVisibleLines=10)

        self.vBoxLayout = QVBoxLayout(self)
        self.titleRowLayout = QHBoxLayout()

        self._initWidget()
        self._initLayout()
        self._bind()

        self.headersEdit.setPlainText(self._headersToText(initial or dict(cfg.defaultRequestHeaders.value)))

    def _initWidget(self) -> None:
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.resetButton.setToolTip(self.tr("恢复默认请求标头"))
        self.resetButton.installEventFilter(ToolTipFilter(self.resetButton))
        self.headersEdit.setPlaceholderText(self.tr("每行一个 Name: Value"))

    def _initLayout(self) -> None:
        self.titleRowLayout.setSpacing(15)
        self.titleRowLayout.addWidget(self.iconWidget)
        self.titleRowLayout.addWidget(self.titleLabel)
        self.titleRowLayout.addStretch(1)
        self.titleRowLayout.addWidget(self.resetButton)

        self.vBoxLayout.setContentsMargins(24, 10, 24, 12)
        self.vBoxLayout.setSpacing(10)
        self.vBoxLayout.addLayout(self.titleRowLayout)
        self.vBoxLayout.addWidget(self.headersEdit)

    def _bind(self) -> None:
        self.resetButton.clicked.connect(self.reset)

    def options(self) -> dict:
        return {"headers": self._textToHeaders(self.headersEdit.toPlainText())}

    def reset(self) -> None:
        self.headersEdit.setPlainText(self._headersToText(dict(cfg.defaultRequestHeaders.value)))

    def _headersToText(self, headers: dict[str, str]) -> str:
        return "\n".join(f"{name}: {value}" for name, value in headers.items())

    def _textToHeaders(self, text: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for line in text.splitlines():
            name, separator, value = line.partition(":")
            if not separator:
                continue
            key = name.strip().lower()
            if key:
                result[key] = value.strip()
        return result
