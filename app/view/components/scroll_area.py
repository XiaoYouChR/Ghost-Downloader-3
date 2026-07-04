import sys

if sys.platform == "darwin":
    from PySide6.QtWidgets import QScrollArea

    class ScrollArea(QScrollArea):
        def enableTransparentBackground(self):
            self.setStyleSheet("QScrollArea{background:transparent;border:none}")
            self.viewport().setStyleSheet("background:transparent")
else:
    from qfluentwidgets import SmoothScrollArea

    class ScrollArea(SmoothScrollArea):
        def enableTransparentBackground(self):
            self.setStyleSheet("QScrollArea{border: none; background: transparent}")
            self.viewport().setStyleSheet("background: transparent")

__all__ = ["ScrollArea"]
