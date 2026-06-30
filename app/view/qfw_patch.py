from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QStackedWidget


def patchFluentLabelThemeChanged() -> None:
    from qfluentwidgets.components.widgets import label

    FluentLabelBase = label.FluentLabelBase

    def _init(self):
        label.FluentStyleSheet.LABEL.apply(self)
        self.setFont(self.getFont())
        self.setTextColor()
        label.qconfig.themeChanged.connect(self._applyThemeColor)
        self.customContextMenuRequested.connect(self._onContextMenuRequested)
        return self

    def _applyThemeColor(self, *_args) -> None:
        self.setTextColor(self.lightColor, self.darkColor)

    FluentLabelBase._init = _init
    FluentLabelBase._applyThemeColor = _applyThemeColor


def unregisterRouter(stacked: QStackedWidget) -> None:
    from qfluentwidgets.common.router import qrouter

    qrouter.history = [item for item in qrouter.history if item.stacked is not stacked]
    qrouter.stackHistories.pop(stacked, None)
    qrouter.emptyChanged.emit(not bool(qrouter.history))
