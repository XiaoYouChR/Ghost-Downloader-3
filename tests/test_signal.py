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


def remove(obj: QObject) -> None:
    obj.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_remove_owner_disconnects_slot(qapp):
    source, receiver = Source(), Receiver()
    source.changed.connect(receiver.onChanged, owner=receiver)
    source.changed.emit(1)

    remove(receiver)
    source.changed.emit(2)

    assert receiver.received == [1]


def test_remove_owner_disconnects_function_slot(qapp):
    source, owner, received = Source(), QObject(), []
    source.changed.connect(received.append, owner=owner)

    remove(owner)
    source.changed.emit(1)

    assert received == []


def test_remove_last_reference_frees_owner(qapp):
    source, receiver = Source(), Receiver()
    source.changed.connect(receiver.onChanged, owner=receiver)
    ref = weakref.ref(receiver)

    del receiver
    gc.collect()

    assert ref() is None
