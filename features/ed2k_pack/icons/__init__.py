from __future__ import annotations

from enum import Enum

from qfluentwidgets import FluentIconBase, Theme, getIconColor

from . import icons_rc  # noqa: F401


class ED2kIcon(FluentIconBase, Enum):
    P2P = "P2P"

    def path(self, theme: Theme = Theme.AUTO) -> str:
        return f":/ed2k_pack/{self.value}_{getIconColor(theme)}.svg"
