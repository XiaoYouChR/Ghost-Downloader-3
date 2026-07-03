from __future__ import annotations

from enum import Enum

from qfluentwidgets import FluentIconBase, Theme, getIconColor

from app.assets.icons import icons_rc  # noqa: F401


class AppIcon(FluentIconBase, Enum):
    DOWNLOAD = "Download"
    CATEGORY = "Category"
    BROWSER = "Browser"
    CONNECT = "Connect"
    CUSTOMIZE = "Customize"
    APPLICATION = "Application"
    ABOUT = "About"

    def path(self, theme: Theme = Theme.AUTO) -> str:
        return f":/app_icons/{self.value}_{getIconColor(theme)}.svg"
