"""QFluentWidgets 字符串的翻译回退。

QFluentWidgets 用 self.tr() 声明 OK / Cancel / On / Off 这些字符串，Qt 取
运行时类名当 context。GD 到处继承它的类（十几个 MessageBoxBase 子类），
每个子类都是一个新 context，逐个补进 ts 不现实，所以这里声明一次基类
context，再让翻译按基类 context 回退。
"""
from __future__ import annotations

from PySide6.QtCore import QTranslator, QT_TRANSLATE_NOOP as N

FLUENT_STRINGS = (
    N("MessageBoxBase", "OK"),
    N("MessageBoxBase", "Cancel"),
    N("SwitchButton", "On"),
    N("SwitchButton", "Off"),
    N("EditMenu", "Cut"),
    N("EditMenu", "Copy"),
    N("EditMenu", "Paste"),
    N("EditMenu", "Cancel"),
    N("EditMenu", "Select all"),
)

FLUENT_CONTEXTS = ("MessageBoxBase", "SwitchButton", "EditMenu")


class FallbackTranslator(QTranslator):

    def translate(self, context: str, source: str, disambiguation: str | None = None, n: int = -1) -> str:
        translated = super().translate(context, source, disambiguation, n)
        if translated:
            return translated
        for fallback in FLUENT_CONTEXTS:
            translated = super().translate(fallback, source, disambiguation, n)
            if translated:
                return translated
        return ""
