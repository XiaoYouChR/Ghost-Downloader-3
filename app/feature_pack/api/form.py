"""Public declarative task form contract for Feature Pack V1."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Literal


EditMode = Literal["before", "running"]
FieldKind = Literal["text", "folder", "headers", "proxy", "int", "choice", "files"]

_DEFAULT_EDIT_MODES: tuple[EditMode, EditMode] = ("before", "running")


def _defaultEditModes() -> frozenset[EditMode]:
    return frozenset(_DEFAULT_EDIT_MODES)


@dataclass(frozen=True, slots=True, kw_only=True)
class FormChoice:
    """One selectable value for a declarative choice field."""

    value: str
    label: str


@dataclass(frozen=True, slots=True, kw_only=True)
class FormField:
    """Describe one editable field in the default task editor."""

    key: str
    label: str
    kind: FieldKind
    choices: tuple[FormChoice, ...] = ()
    placeholder: str = ""
    note: str = ""
    min: int | None = None
    max: int | None = None
    step: int = 1
    modes: frozenset[EditMode] = field(default_factory=_defaultEditModes)


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskForm:
    """Declarative task edit form consumed by the default host dialog."""

    title: str = "编辑任务"
    fields: tuple[FormField, ...] = ()


__all__ = ["EditMode", "FieldKind", "FormChoice", "FormField", "TaskForm"]
