"""TaskDraft parse→review→confirm 流程的逐分支测试。

Seam S9: TaskDraft — 批量解析、确认、取消的生命周期。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

import pytest
from PySide6.QtWidgets import QApplication

from app.models.task import Task, TaskStep, TaskStatus


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# ── Stubs ──


@dataclass(kw_only=True)
class StubStep(TaskStep):
    stepIndex: int = 0

    async def run(self, reportSpeed, waitForSpeedLimit):
        pass


def stubTask(url: str = "http://example.com/file.zip") -> Task:
    step = StubStep(stepIndex=0)
    task = Task(name="file.zip", url=url, packId="http", steps=[step])
    step._bindTask(task)
    return task


class StubCoroutineRunner:
    def __init__(self):
        self._pending: dict[str, dict] = {}
        self._cancelled: list[str] = []

    def submit(self, coro, *, done=None, failed=None, **kwargs):
        workId = f"work_{uuid4().hex[:8]}"
        self._pending[workId] = {"coro": coro, "done": done, "failed": failed, "kwargs": kwargs}
        return workId

    def cancel(self, workId, finished=None):
        self._cancelled.append(workId)
        self._pending.pop(workId, None)
        if finished:
            finished()

    def resolve(self, workId, result):
        entry = self._pending.pop(workId)
        if entry["done"]:
            entry["done"](result, **entry["kwargs"])

    def reject(self, workId, error: str):
        entry = self._pending.pop(workId)
        if entry["failed"]:
            entry["failed"](error, **entry["kwargs"])


class StubFeatureService:
    async def parse(self, options):
        return stubTask(url=options.url)


@pytest.fixture
def runner():
    return StubCoroutineRunner()


@pytest.fixture
def draft(qapp, runner):
    from app.services.task_draft import TaskDraft
    return TaskDraft(runner, StubFeatureService())


# ── Tests ──


class TestSetUrls:

    def test_submits_parse_for_each_url(self, draft, runner):
        draft.setUrls(["http://a.com/1", "http://b.com/2"])
        assert len(runner._pending) == 2

    def test_removes_old_urls_cancels_parse(self, draft, runner):
        draft.setUrls(["http://a.com/1", "http://b.com/2"])
        oldIds = list(runner._pending.keys())
        draft.setUrls(["http://c.com/3"])
        assert all(wid in runner._cancelled for wid in oldIds)
        assert len(runner._pending) == 1

    def test_keeps_equal_urls(self, draft, runner):
        draft.setUrls(["http://a.com/1", "http://b.com/2"])
        firstIds = set(runner._pending.keys())
        draft.setUrls(["http://a.com/1", "http://b.com/2"])
        assert set(runner._pending.keys()) == firstIds

    def test_parsingBusyChanged_emitted(self, draft, runner):
        signals = []
        draft.parsingBusyChanged.connect(signals.append)
        draft.setUrls(["http://a.com/1"])
        assert True in signals


class TestParseCallbacks:

    def test_success_emits_parseSucceeded(self, draft, runner):
        received = []
        draft.parseSucceeded.connect(lambda url, task: received.append((url, task)))
        draft.setUrls(["http://a.com/file.zip"])
        workId = list(runner._pending.keys())[0]
        task = stubTask("http://a.com/file.zip")
        runner.resolve(workId, task)
        assert len(received) == 1
        assert received[0][0] == "http://a.com/file.zip"
        assert received[0][1] is task

    def test_failure_emits_parseFailed(self, draft, runner):
        errors = []
        draft.parseFailed.connect(lambda url, err: errors.append((url, err)))
        draft.setUrls(["http://a.com/file.zip"])
        workId = list(runner._pending.keys())[0]
        runner.reject(workId, "network error")
        assert len(errors) == 1
        assert errors[0][0] == "http://a.com/file.zip"
        assert "network error" in errors[0][1]

    def test_success_clears_parsing_busy(self, draft, runner):
        states = []
        draft.parsingBusyChanged.connect(states.append)
        draft.setUrls(["http://a.com/1"])
        workId = list(runner._pending.keys())[0]
        runner.resolve(workId, stubTask("http://a.com/1"))
        assert states[-1] is False


class TestConfirm:

    def test_emits_taskConfirmed_for_completed(self, draft, runner):
        confirmed = []
        draft.taskConfirmed.connect(confirmed.append)
        draft.setUrls(["http://a.com/1"])
        workId = list(runner._pending.keys())[0]
        task = stubTask("http://a.com/1")
        runner.resolve(workId, task)
        draft.confirm()
        assert len(confirmed) == 1
        assert confirmed[0] is task

    def test_pending_parse_auto_confirms_on_completion(self, draft, runner):
        confirmed = []
        draft.taskConfirmed.connect(confirmed.append)
        draft.setUrls(["http://a.com/1"])
        workId = list(runner._pending.keys())[0]
        draft.confirm()
        assert len(confirmed) == 0
        task = stubTask("http://a.com/1")
        runner.resolve(workId, task)
        assert len(confirmed) == 1
        assert confirmed[0] is task

    def test_confirm_skips_items_without_task_or_parse(self, draft, runner):
        confirmed = []
        draft.taskConfirmed.connect(confirmed.append)
        draft.confirm()
        assert len(confirmed) == 0

    def test_confirm_applies_base_options(self, draft, runner):
        confirmed = []
        draft.taskConfirmed.connect(confirmed.append)
        draft.setBaseOptions({"subworkerCount": 8})
        draft.setUrls(["http://a.com/1"])
        workId = list(runner._pending.keys())[0]
        task = stubTask("http://a.com/1")
        runner.resolve(workId, task)
        draft.confirm()
        assert len(confirmed) == 1

    def test_confirm_applies_category_override(self, draft, runner):
        confirmed = []
        draft.taskConfirmed.connect(confirmed.append)
        draft.setUrls(["http://a.com/1"])
        workId = list(runner._pending.keys())[0]
        task = stubTask("http://a.com/1")
        runner.resolve(workId, task)
        draft.setUrlCategory("http://a.com/1", "video")
        draft.confirm()
        assert confirmed[0].category == "video"


class TestClear:

    def test_cancels_all_in_flight(self, draft, runner):
        draft.setUrls(["http://a.com/1", "http://b.com/2"])
        workIds = list(runner._pending.keys())
        draft.clear()
        assert all(wid in runner._cancelled for wid in workIds)

    def test_emits_itemsCleared(self, draft, runner):
        cleared = []
        draft.itemsCleared.connect(lambda: cleared.append(True))
        draft.setUrls(["http://a.com/1"])
        draft.clear()
        assert len(cleared) == 1

    def test_urls_empty_after_clear(self, draft, runner):
        draft.setUrls(["http://a.com/1"])
        draft.clear()
        assert draft.urls() == []


class TestCanConfirm:

    def test_false_when_empty(self, draft):
        assert draft.canConfirm() is False

    def test_true_when_parsing(self, draft, runner):
        draft.setUrls(["http://a.com/1"])
        assert draft.canConfirm() is True

    def test_true_when_task_parsed(self, draft, runner):
        draft.setUrls(["http://a.com/1"])
        workId = list(runner._pending.keys())[0]
        runner.resolve(workId, stubTask("http://a.com/1"))
        assert draft.canConfirm() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
