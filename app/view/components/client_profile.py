from typing import Callable

from PySide6.QtCore import Qt
from qfluentwidgets import (
    Action,
    DropDownPushButton,
    FluentIcon,
    RoundMenu,
    SettingCard,
)

from app.supports.config import cfg
from app.supports.utils import EMULATION_FAMILIES, familyProfileNames

_FOLLOW_GLOBAL = ""
_AUTO = "auto"
_RAW = "raw"
_FAMILY_LABELS = {"chrome": "Chrome", "edge": "Edge", "firefox": "Firefox", "safari": "Safari", "okhttp": "OkHttp"}
_FAMILY_SUBTITLES = {"okhttp": "OkHttp（安卓 App）"}


def profileLabel(value: str, *, followGlobal: bool = False) -> str:
    if value == _FOLLOW_GLOBAL and followGlobal:
        return "跟随全局"
    if value in (_FOLLOW_GLOBAL, _AUTO):
        return "自动（匹配来源）"
    if value == _RAW:
        return "不模拟（原样发送）"
    if value in _FAMILY_LABELS:
        return f"{_FAMILY_LABELS[value]}（最新）"
    head = value.rstrip("0123456789_")
    version = value[len(head):].replace("_", ".")
    return f"{head} {version}" if version else value


def buildProfileMenu(parent, onPick: Callable[[str], None], *, includeFollowGlobal: bool) -> RoundMenu:
    def item(menu: RoundMenu, value: str, icon=None) -> None:
        label = profileLabel(value, followGlobal=True)
        action = Action(icon, label, parent) if icon else Action(label, parent)
        action.triggered.connect(lambda checked=False, v=value: onPick(v))
        menu.addAction(action)

    menu = RoundMenu(parent=parent)
    if includeFollowGlobal:
        item(menu, _FOLLOW_GLOBAL, FluentIcon.LINK)
    item(menu, _AUTO, FluentIcon.ROBOT)
    for family in EMULATION_FAMILIES:
        submenu = RoundMenu(_FAMILY_SUBTITLES.get(family, _FAMILY_LABELS[family]), parent)
        item(submenu, family)
        submenu.addSeparator()
        for name in familyProfileNames(family):
            item(submenu, name)
        menu.addMenu(submenu)
    menu.addSeparator()
    item(menu, _RAW, FluentIcon.CANCEL)
    return menu


class ClientProfileSettingCard(SettingCard):
    def __init__(self, parent=None) -> None:
        super().__init__(
            FluentIcon.ROBOT,
            self.tr("模拟身份"),
            self.tr("浏览器 TLS 指纹与 User-Agent"),
            parent,
        )
        # instant widget
        self.button = DropDownPushButton(profileLabel(cfg.clientProfile.value), self)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.button.setMinimumWidth(200)
        self.button.setMenu(buildProfileMenu(self, self._onPick, includeFollowGlobal=False))

    def _initLayout(self) -> None:
        self.hBoxLayout.addWidget(self.button, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def _bind(self) -> None:
        cfg.clientProfile.valueChanged.connect(lambda value: self.button.setText(profileLabel(value)))

    def _onPick(self, value: str) -> None:
        cfg.set(cfg.clientProfile, value)
