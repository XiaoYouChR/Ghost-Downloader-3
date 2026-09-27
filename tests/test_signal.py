from __future__ import annotations

import gc
import weakref

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication

from app.signal import Signal


class Source:
    changed = Signal(int)


class Receiver(QObject):
    def __init__(self):
        super().__init__()
        self.received = []

    def onChanged(self, value):
        self.received.append(value)


def destroy(obj: QObject) -> None:
    obj.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_slot_is_disconnected_when_owner_is_destroyed(qapp):
    source, receiver = Source(), Receiver()
    source.changed.connect(receiver.onChanged, owner=receiver)
    source.changed.emit(1)

    destroy(receiver)
    source.changed.emit(2)

    assert receiver.received == [1]


def test_function_slot_is_disconnected_with_its_owner(qapp):
    source, owner, received = Source(), QObject(), []
    source.changed.connect(received.append, owner=owner)

    destroy(owner)
    source.changed.emit(1)

    assert received == []


def test_owner_is_not_kept_alive_by_the_connection(qapp):
    source, receiver = Source(), Receiver()
    source.changed.connect(receiver.onChanged, owner=receiver)
    ref = weakref.ref(receiver)

    del receiver
    gc.collect()

    assert ref() is None
