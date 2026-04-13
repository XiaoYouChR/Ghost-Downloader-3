"""Public declarative settings contract for Feature Pack V1."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field

from .form import FormChoice


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


__all__ = ["SettingItem", "SettingSection"]
