from __future__ import annotations

from enum import Enum

from qfluentwidgets import FluentIconBase, Theme, getIconColor

from . import icons_rc  # noqa: F401


class BTIcon(FluentIconBase, Enum):
    BITTORRENT = "BitTorrent"

    def path(self, theme: Theme = Theme.AUTO) -> str:
        return f":/bittorrent_pack/{self.value}_{getIconColor(theme)}.svg"
