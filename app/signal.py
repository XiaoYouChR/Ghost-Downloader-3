from __future__ import annotations

import weakref
from collections.abc import Callable
from typing import Any


class Signal:
    def __init__(self, *_types: type) -> None:
        pass

    def __set_name__(self, owner: type, name: str) -> None:
        self._attr = f"_sig_{name}"

    def __get__(self, obj: Any, objtype: type | None = None) -> Signal | BoundSignal:
        if obj is None:
            return self
        bound = obj.__dict__.get(self._attr)
        if bound is None:
            bound = BoundSignal()
            obj.__dict__[self._attr] = bound
        return bound


class BoundSignal:
    __slots__ = ("_slots",)

    def __init__(self) -> None:
        self._slots: list[Callable | weakref.WeakMethod] = []

    def connect(self, slot: Callable) -> None:
        if hasattr(slot, "__self__") and hasattr(slot, "__func__"):
            try:
                self._slots.append(weakref.WeakMethod(slot, self._remove))
                return
            except TypeError:
                pass
        self._slots.append(slot)

    def disconnect(self, slot: Callable | None = None) -> None:
        if slot is None:
            self._slots.clear()
            return
        if hasattr(slot, "__self__"):
            for i, s in enumerate(self._slots):
                if isinstance(s, weakref.WeakMethod) and s() == slot:
                    del self._slots[i]
                    return
        else:
            try:
                self._slots.remove(slot)
            except ValueError:
                pass

    def emit(self, *args: Any) -> None:
        for slot in self._slots[:]:
            if isinstance(slot, weakref.WeakMethod):
                cb = slot()
                if cb is not None:
                    cb(*args)
            else:
                slot(*args)

    def _remove(self, ref: weakref.WeakMethod) -> None:
        try:
            self._slots.remove(ref)
        except ValueError:
            pass
