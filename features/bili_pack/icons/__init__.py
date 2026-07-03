from __future__ import annotations

from enum import Enum

from qfluentwidgets import FluentIconBase, Theme, getIconColor

from . import icons_rc  # noqa: F401


class BiliIcon(FluentIconBase, Enum):
    BILIBILI = "Bilibili"

    def path(self, theme: Theme = Theme.AUTO) -> str:
        return f":/bili_pack/{self.value}_{getIconColor(theme)}.svg"
