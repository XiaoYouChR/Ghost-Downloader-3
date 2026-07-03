from __future__ import annotations

from enum import Enum

from qfluentwidgets import FluentIconBase, Theme, getIconColor

from . import icons_rc  # noqa: F401


class YTIcon(FluentIconBase, Enum):
    YOUTUBE = "YouTube"

    def path(self, theme: Theme = Theme.AUTO) -> str:
        return f":/yt_dlp_pack/{self.value}_{getIconColor(theme)}.svg"
