from __future__ import annotations

from enum import Enum

from qfluentwidgets import FluentIconBase, Theme, getIconColor

from . import icons_rc  # noqa: F401


class FFmpegIcon(FluentIconBase, Enum):
    FFMPEG = "FFmpeg"

    def path(self, theme: Theme = Theme.AUTO) -> str:
        return f":/ffmpeg_pack/{self.value}_{getIconColor(theme)}.svg"
