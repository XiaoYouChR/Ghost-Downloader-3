"""bridge 只把 NameConflictQueue 的询问投影给 Kotlin，并把回复转回队列。"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.name_conflict_queue import NameConflict
from app.services.task_service import NameConflictChoice
from tests.helpers import StubFlows


class StubQueue:
    def __init__(self):
        self.replies: list[tuple] = []

    def setChoice(self, taskId, choice, isAppliedToRest):
        self.replies.append(("setChoice", taskId, choice, isAppliedToRest))

    def cancel(self, taskId):
        self.replies.append(("cancel", taskId))


@pytest.fixture
def engine(bridge):
    engine = bridge.Bridge.__new__(bridge.Bridge)
    engine._nameConflictQueue = StubQueue()
    engine._flows = StubFlows()
    return engine


def shownConflict(engine):
    return json.loads(engine._flows.states["nameConflict"])


def test_conflict_is_shown_as_json(engine):
    task = SimpleNamespace(taskId="a", fileSize=-1)
    engine._onNameConflictChanged(NameConflict(task, Path("/d/a.zip"), False, 4, 100, 2))

    assert shownConflict(engine) == {
        "taskId": "a", "name": "a.zip", "isFolder": False, "existingSize": 4,
        "modifiedAt": 100, "newSize": 0, "restCount": 2,
    }


def test_no_conflict_clears_the_dialog(engine):
    engine._onNameConflictChanged(None)

    assert shownConflict(engine) is None


def test_reply_goes_back_to_the_queue(engine):
    engine.setNameConflictChoice("a", "overwrite", True)
    engine.setNameConflictChoice("b", "", False)

    assert engine._nameConflictQueue.replies == [
        ("setChoice", "a", NameConflictChoice.OVERWRITE, True),
        ("cancel", "b"),
    ]
