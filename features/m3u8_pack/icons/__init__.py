from __future__ import annotations

from enum import Enum

from qfluentwidgets import FluentIconBase, Theme, getIconColor

from . import icons_rc  # noqa: F401


class M3U8Icon(FluentIconBase, Enum):
    STREAM = "Stream"

    def path(self, theme: Theme = Theme.AUTO) -> str:
        return f":/m3u8_pack/{self.value}_{getIconColor(theme)}.svg"
