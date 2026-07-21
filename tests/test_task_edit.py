"""LiveEditDialog 的 6 分支决策逻辑测试。

Seam S8: LiveEditDialog.accept() 的分支覆盖
  1. URL 不变 → taskService.edit(task, options) 直接调用
  2. URL 变 + parse 成功 + canReuseProgress → edit 不丢数据
  3. URL 变 + parse 成功 + 不可复用 + 无已下载数据 → 直接 edit
  4. URL 变 + parse 成功 + 不可复用 + 有已下载数据 → 弹确认框
  5. URL 变 + parse 失败 → 显示错误，task 不变
  6. reject 时取消进行中的 parse
"""
from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QWidget

from app.models.task import Task, TaskStep, TaskStatus


@dataclass(kw_only=True)
class StubStep(TaskStep):
    stepIndex: int = 0

    async def run(self, reportSpeed, waitForSpeedLimit):
        pass


def makeTask(url="http://example.com/file.zip", receivedBytes=0) -> Task:
    step = StubStep(stepIndex=0, receivedBytes=receivedBytes)
    task = Task(name="file.zip", url=url, packId="http", steps=[step])
    step._bindTask(task)
    return task


class RecordingTaskService:
    def __init__(self):
        self.editCalls: list[tuple] = []

    def edit(self, task, options, newTask=None):
        self.editCalls.append((task, options, newTask))


class RecordingCoroutineRunner:
    def __init__(self):
        self._counter = 0
        self._pending: dict[str, tuple] = {}

    def submit(self, work, done=None, failed=None, **kwargs) -> str:
        self._counter += 1
        workId = f"wrk_{self._counter}"
        self._pending[workId] = (work, done, failed, kwargs)
        return workId

    def cancel(self, workId, finished=None):
        self._pending.pop(workId, None)

    def resolveLast(self, result):
        workId = f"wrk_{self._counter}"
        _, done, _, kwargs = self._pending.pop(workId)
        if done:
            done(result, **{k: v for k, v in kwargs.items() if k not in ("owner",)})

    def failLast(self, error: str):
        workId = f"wrk_{self._counter}"
        _, _, failed, kwargs = self._pending.pop(workId)
        if failed:
            failed(error, **{k: v for k, v in kwargs.items() if k not in ("owner",)})


class StubFeatureService:
    async def parse(self, options):
        return makeTask(url=options.url)

    def editCards(self, task, parent=None):
        return []


class StubOptionCard(QWidget):
    def __init__(self, opts: dict, parent=None):
        super().__init__(parent)
        self._opts = opts

    def options(self):
        return dict(self._opts)


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def parentWindow(qapp):
    from PySide6.QtWidgets import QWidget
    w = QWidget()
    w.resize(800, 600)
    yield w
    w.deleteLater()


@pytest.fixture()
def env(parentWindow):
    ts = RecordingTaskService()
    cr = RecordingCoroutineRunner()
    fs = StubFeatureService()
    return ts, cr, fs, parentWindow


def makeDialog(task, cards, ts, cr, fs, parent):
    from app.view.dialogs.edit_task import LiveEditDialog
    return LiveEditDialog(task, cards, cr, fs, ts, parent)


class TestEditNoUrlChange:

    def test_direct_edit(self, env):
        ts, cr, fs, parent = env
        task = makeTask()
        card = StubOptionCard({"subworkerCount": 8})
        dialog = makeDialog(task, [card], ts, cr, fs, parent)

        dialog.accept()

        assert len(ts.editCalls) == 1
        called_task, called_opts, called_new = ts.editCalls[0]
        assert called_task is task
        assert called_opts == {"subworkerCount": 8}
        assert called_new is None

    def test_empty_url_treated_as_no_change(self, env):
        ts, cr, fs, parent = env
        task = makeTask()
        card = StubOptionCard({"url": "", "subworkerCount": 4})
        dialog = makeDialog(task, [card], ts, cr, fs, parent)

        dialog.accept()

        assert len(ts.editCalls) == 1
        _, opts, newTask = ts.editCalls[0]
        assert newTask is None

    def test_same_url_treated_as_no_change(self, env):
        ts, cr, fs, parent = env
        task = makeTask(url="http://example.com/file.zip")
        card = StubOptionCard({"url": "http://example.com/file.zip"})
        dialog = makeDialog(task, [card], ts, cr, fs, parent)

        dialog.accept()

        assert len(ts.editCalls) == 1
        _, _, newTask = ts.editCalls[0]
        assert newTask is None


class TestEditWithUrlChange:

    def test_reusable_progress(self, env):
        ts, cr, fs, parent = env
        task = makeTask()
        task.canReuseProgress = lambda newTask: True
        card = StubOptionCard({"url": "http://example.com/new.zip"})
        dialog = makeDialog(task, [card], ts, cr, fs, parent)

        dialog.accept()
        newTask = makeTask(url="http://example.com/new.zip")
        cr.resolveLast(newTask)

        assert len(ts.editCalls) == 1
        _, _, editNewTask = ts.editCalls[0]
        assert editNewTask is newTask

    def test_not_reusable_no_data(self, env):
        ts, cr, fs, parent = env
        task = makeTask(receivedBytes=0)
        card = StubOptionCard({"url": "http://example.com/new.zip"})
        dialog = makeDialog(task, [card], ts, cr, fs, parent)

        dialog.accept()
        newTask = makeTask(url="http://example.com/new.zip")
        cr.resolveLast(newTask)

        assert len(ts.editCalls) == 1
        _, _, editNewTask = ts.editCalls[0]
        assert editNewTask is newTask

    def test_not_reusable_with_data_confirm(self, env):
        ts, cr, fs, parent = env
        task = makeTask(receivedBytes=1024)
        card = StubOptionCard({"url": "http://example.com/new.zip"})
        dialog = makeDialog(task, [card], ts, cr, fs, parent)

        dialog.accept()
        newTask = makeTask(url="http://example.com/new.zip")

        with patch("app.view.dialogs.edit_task.MessageBox") as MockBox:
            MockBox.return_value.exec.return_value = True
            cr.resolveLast(newTask)

        assert len(ts.editCalls) == 1
        _, _, editNewTask = ts.editCalls[0]
        assert editNewTask is newTask

    def test_not_reusable_with_data_cancel(self, env):
        ts, cr, fs, parent = env
        task = makeTask(receivedBytes=1024)
        card = StubOptionCard({"url": "http://example.com/new.zip"})
        dialog = makeDialog(task, [card], ts, cr, fs, parent)

        dialog.accept()
        newTask = makeTask(url="http://example.com/new.zip")

        with patch("app.view.dialogs.edit_task.MessageBox") as MockBox:
            MockBox.return_value.exec.return_value = False
            cr.resolveLast(newTask)

        assert len(ts.editCalls) == 0


class TestEditParseFail:

    def test_parse_failure_shows_error(self, env):
        ts, cr, fs, parent = env
        task = makeTask()
        card = StubOptionCard({"url": "http://example.com/new.zip"})
        dialog = makeDialog(task, [card], ts, cr, fs, parent)

        dialog.accept()

        with patch("app.view.dialogs.edit_task.InfoBar") as MockInfoBar:
            cr.failLast("解析失败")

        assert len(ts.editCalls) == 0
        assert dialog.yesButton.isEnabled()


class TestEditReject:

    def test_reject_cancels_pending_parse(self, env):
        ts, cr, fs, parent = env
        task = makeTask()
        card = StubOptionCard({"url": "http://example.com/new.zip"})
        dialog = makeDialog(task, [card], ts, cr, fs, parent)

        dialog.accept()
        assert len(cr._pending) == 1

        dialog.reject()
        assert len(cr._pending) == 0
        assert len(ts.editCalls) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
