import sys

if sys.platform == "darwin":
    from qfluentwidgets import ScrollArea
else:
    from qfluentwidgets import SmoothScrollArea

    class ScrollArea(SmoothScrollArea):
        def enableTransparentBackground(self):
            self.setStyleSheet("QScrollArea{border: none; background: transparent}")
            self.viewport().setStyleSheet("background: transparent")

__all__ = ["ScrollArea"]
