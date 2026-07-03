from __future__ import annotations

from enum import Enum

from qfluentwidgets import FluentIconBase, Theme, getIconColor

from . import icons_rc  # noqa: F401


class HFIcon(FluentIconBase, Enum):
    HUGGINGFACE = "HuggingFace"

    def path(self, theme: Theme = Theme.AUTO) -> str:
        return f":/huggingface_pack/{self.value}_{getIconColor(theme)}.svg"
