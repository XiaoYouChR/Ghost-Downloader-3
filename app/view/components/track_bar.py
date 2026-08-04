from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import (
    Action, CheckableMenu, FluentIcon, FluentIconBase, IndeterminateProgressRing,
    MenuIndicatorType, ToolTipFilter, TransparentToolButton,
)


class TrackButton(TransparentToolButton):

    # ToolButton.__init__ 内部回调 self.__init__，不能安全 override
    def _postInit(self):
        super()._postInit()
        self.setCheckable(True)
        self.setFixedSize(28, 28)
        self.installEventFilter(ToolTipFilter(self))

    def nextCheckState(self):
        pass

    def setTrackEnabled(self, enabled: bool) -> None:
        self.setEnabled(enabled)
        if not enabled:
            self.setChecked(False)

    def _drawIcon(self, icon, painter, rect, state=None):
        if isinstance(icon, FluentIconBase) and not self.isChecked():
            icon.render(painter, rect, fill="#808080")
        else:
            super()._drawIcon(icon, painter, rect)


class MenuTrackButton(TrackButton):

    optionPicked = Signal(str)

    def _postInit(self):
        super()._postInit()
        self._options: list[tuple[str, str]] = []
        self._selectedValue: str | None = None
        self.clicked.connect(self._openMenu)

    def setOptions(self, options: list[tuple[str, str]], selected: str | None = None) -> None:
        self._options = list(options)
        if selected is not None and any(v == selected for v, _ in options):
            self._selectedValue = selected
        elif self.isChecked() and options:
            values = {v for v, _ in options}
            if self._selectedValue is None or self._selectedValue not in values:
                self._selectedValue = options[0][0]

    def selectedValue(self) -> str | None:
        return self._selectedValue

    def _openMenu(self) -> None:
        menu = CheckableMenu(parent=self, indicatorType=MenuIndicatorType.RADIO)
        group = QActionGroup(menu)

        offAction = Action(self.tr("不下载"), menu, checkable=True)
        offAction.setChecked(not self.isChecked())
        offAction.triggered.connect(self._onTrackDeselected)
        group.addAction(offAction)
        menu.addAction(offAction)
        menu.addSeparator()

        for value, label in self._options:
            action = Action(label, menu, checkable=True)
            action.setChecked(self.isChecked() and value == self._selectedValue)
            action.triggered.connect(lambda _, v=value: self._onOptionPicked(v))
            group.addAction(action)
            menu.addAction(action)

        menu.closedSignal.connect(menu.deleteLater)
        menu.exec(self.mapToGlobal(self.rect().bottomLeft()))

    def _onTrackDeselected(self) -> None:
        self.setChecked(False)
        if not self.isChecked():
            self._selectedValue = None

    def _onOptionPicked(self, value: str) -> None:
        self._selectedValue = value
        if not self.isChecked():
            self.setChecked(True)
        self.optionPicked.emit(value)


class TrackBar(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.videoButton = MenuTrackButton(FluentIcon.VIDEO, self)
        self.videoButton.setToolTip(self.tr("视频"))
        self.audioButton = MenuTrackButton(FluentIcon.HEADPHONE, self)
        self.audioButton.setToolTip(self.tr("音频"))
        self.subtitleButton = TrackButton(FluentIcon.LANGUAGE, self)
        self.subtitleButton.setToolTip(self.tr("字幕"))
        self.coverButton = TrackButton(FluentIcon.PHOTO, self)
        self.coverButton.setToolTip(self.tr("封面"))

        self.spinner = IndeterminateProgressRing(self)
        self.spinner.setFixedSize(20, 20)
        self.spinner.setStrokeWidth(3)
        self.spinner.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.spinner)
        layout.addWidget(self.videoButton)
        layout.addWidget(self.audioButton)
        layout.addWidget(self.subtitleButton)
        layout.addWidget(self.coverButton)

        for button in (self.videoButton, self.audioButton, self.subtitleButton, self.coverButton):
            button.toggled.connect(self._preventAllOff)

        self.videoButton.setChecked(True)
        self.audioButton.setChecked(True)

    def _preventAllOff(self, checked: bool) -> None:
        if checked:
            return
        sender = self.sender()
        if not sender.isEnabled():
            return
        primaryButtons = (self.videoButton, self.audioButton, self.coverButton)
        if not any(b.isChecked() for b in primaryButtons):
            sender.setChecked(True)
