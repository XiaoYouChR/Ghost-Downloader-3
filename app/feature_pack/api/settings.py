"""Public declarative settings contract for Feature Pack V1."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field

from PySide6.QtCore import QCoreApplication
from qfluentwidgets import ConfigItem

from app.supports.config import cfg

from .form import FormChoice


class FeaturePackSettings:
    """
    Base class for pack-owned persistent settings.

    Subclasses declare ``qfluentwidgets.ConfigItem`` fields. The host registers
    those fields on the global config object so each pack keeps its own storage
    keys while settings UI is contributed through ``SettingSection``.
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)

        for attrName, attrValue in cls.__dict__.items():
            if isinstance(attrValue, ConfigItem):
                setattr(cfg.__class__, f"pack_{cls.__name__}_{attrName}", attrValue)

        cfg.load()

    def tr(self, text: str) -> str:
        return QCoreApplication.translate(self.__class__.__name__, text)


@dataclass(frozen=True, slots=True, kw_only=True)
class SettingItem:
    """Describe one simple settings contribution rendered by the host."""

    key: str
    label: str
    kind: str
    note: str = ""
    options: tuple[FormChoice, ...] = ()
    extra: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True, kw_only=True)
class SettingSection:
    """Group setting items contributed by one feature pack."""

    id: str
    title: str
    items: tuple[SettingItem, ...] = ()


__all__ = ["FeaturePackSettings", "SettingItem", "SettingSection"]
