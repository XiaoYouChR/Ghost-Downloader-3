"""逐个询问 Name Conflict：同一轮加入的冲突收齐后再问，询问内容是不会变的快照。"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.name_conflict_queue import NameConflictQueue
from app.services.task_service import NameConflictChoice


class StubTaskService:
    def __init__(self):
        self.takenPaths: dict[str, Path | None] = {}
        self.probedIds: list[str] = []
        self.added: list[tuple[str, str]] = []

    def probeConflict(self, task):
        self.probedIds.append(task.taskId)
        return self.takenPaths[task.taskId]

    def add(self, task, choice=None):
        self.added.append((task.taskId, choice.value))
        return True


class StubLoop:
    def __init__(self):
        self.callbacks = []

    def post(self, callback, *args, **kwargs):
        self.callbacks.append(lambda: callback(*args, **kwargs))

    def runOnce(self):
        callbacks, self.callbacks = self.callbacks, []
        for callback in callbacks:
            callback()


@pytest.fixture
def taskService():
    return StubTaskService()


@pytest.fixture
def loop():
    return StubLoop()


@pytest.fixture
def queue(taskService, loop):
    queue = NameConflictQueue(taskService.probeConflict, taskService.add, loop.post)
    queue.conflicts = []
    queue.conflictChanged.connect(queue.conflicts.append)
    return queue


def makeTask(taskId: str):
    return SimpleNamespace(taskId=taskId, fileSize=4)


def takeAll(taskService, tmp_path, taskIds):
    (tmp_path / "a.zip").write_bytes(b"mine")
    taskService.takenPaths = {taskId: tmp_path / "a.zip" for taskId in taskIds}


def test_asks_after_collecting_conflicts_of_the_same_round(queue, taskService, loop, tmp_path):
    takeAll(taskService, tmp_path, "abc")

    for taskId in "abc":
        queue.add(makeTask(taskId))
    assert queue.conflicts == []
    loop.runOnce()

    conflict = queue.conflicts[-1]
    assert conflict.task.taskId == "a"
    assert conflict.takenPath == tmp_path / "a.zip"
    assert (conflict.isFolder, conflict.existingSize, conflict.restCount) == (False, 4, 2)
    assert taskService.probedIds == ["a"]


def test_conflict_added_while_asking_waits_without_changing_the_question(queue, taskService, loop, tmp_path):
    takeAll(taskService, tmp_path, "ab")
    queue.add(makeTask("a"))
    loop.runOnce()

    queue.add(makeTask("b"))
    loop.runOnce()

    assert [c.task.taskId for c in queue.conflicts] == ["a"]
    assert taskService.probedIds == ["a"]


def test_conflict_gone_by_its_turn_keeps_both_without_asking(queue, taskService, loop, tmp_path):
    takeAll(taskService, tmp_path, "a")
    taskService.takenPaths["b"] = None
    queue.add(makeTask("a"))
    queue.add(makeTask("b"))
    loop.runOnce()

    queue.setChoice("a", NameConflictChoice.OVERWRITE, False)

    assert taskService.added == [("a", "overwrite"), ("b", "keepBoth")]
    assert queue.conflicts[-1] is None


def test_choice_applied_to_rest_answers_only_the_conflicts_shown(queue, taskService, loop, tmp_path):
    takeAll(taskService, tmp_path, "abcd")
    for taskId in "abc":
        queue.add(makeTask(taskId))
    loop.runOnce()
    queue.add(makeTask("d"))

    queue.setChoice("a", NameConflictChoice.KEEP_BOTH, True)

    assert taskService.added == [("a", "keepBoth"), ("b", "keepBoth"), ("c", "keepBoth")]
    assert queue.conflicts[-1].task.taskId == "d"
    assert queue.conflicts[-1].restCount == 0


def test_cancel_skips_only_the_asked_task(queue, taskService, loop, tmp_path):
    takeAll(taskService, tmp_path, "ab")
    queue.add(makeTask("a"))
    queue.add(makeTask("b"))
    loop.runOnce()

    queue.cancel("a")

    assert taskService.added == []
    assert queue.conflicts[-1].task.taskId == "b"


def test_reply_to_a_conflict_no_longer_asked_is_ignored(queue, taskService, loop, tmp_path):
    takeAll(taskService, tmp_path, "ab")
    queue.add(makeTask("a"))
    queue.add(makeTask("b"))
    loop.runOnce()
    queue.setChoice("a", NameConflictChoice.KEEP_BOTH, False)

    queue.setChoice("a", NameConflictChoice.OVERWRITE, False)
    queue.cancel("a")

    assert taskService.added == [("a", "keepBoth")]
    assert queue.conflicts[-1].task.taskId == "b"
