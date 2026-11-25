from __future__ import annotations

import pytest
from PySide6 import QtWidgets

from app.platform import desktop
from app.services.plan import Plan, PlanAction


@pytest.fixture
def calls(monkeypatch):
    calls = []
    realApplication = QtWidgets.QApplication

    class FakeApplication:
        """Keeps QUIT observable while the Qt plugin still finds the real application."""

        instance = staticmethod(realApplication.instance)

        @staticmethod
        def quit() -> None:
            calls.append("quit")

    monkeypatch.setattr(QtWidgets, "QApplication", FakeApplication)
    monkeypatch.setattr(desktop, "shutdown", lambda: calls.append("shutdown"))
    monkeypatch.setattr(desktop, "restart", lambda: calls.append("restart"))
    monkeypatch.setattr(desktop, "sleep", lambda: calls.append("sleep"))
    monkeypatch.setattr(desktop, "openFile", lambda path: calls.append(("openFile", path)))
    return calls


def buildPlan(isAllCompleted: bool = True) -> Plan:
    return Plan(allCompleted=lambda: isAllCompleted)


@pytest.mark.parametrize("action, expected", [
    pytest.param(PlanAction.SHUTDOWN, "shutdown", id="shutdown"),
    pytest.param(PlanAction.RESTART, "restart", id="restart"),
    pytest.param(PlanAction.SLEEP, "sleep", id="sleep"),
    pytest.param(PlanAction.QUIT, "quit", id="quit"),
])
def test_trigger_after_all_tasks_completed_runs_the_chosen_action(calls, action, expected):
    plan = buildPlan()
    plan.set(action)

    plan.trigger()

    assert calls == [expected]
    assert plan.action is None


def test_trigger_after_all_tasks_completed_opens_the_chosen_file(calls, tmp_path):
    path = str(tmp_path / "a.bin")
    plan = buildPlan()
    plan.set(PlanAction.OPEN_FILE, path)

    plan.trigger()

    assert calls == [("openFile", path)]
    assert plan.filePath == ""


def test_trigger_without_a_file_opens_nothing(calls):
    plan = buildPlan()
    plan.set(PlanAction.OPEN_FILE)

    plan.trigger()

    assert calls == []
    assert plan.action is None


def test_trigger_while_a_task_runs_keeps_waiting(calls):
    plan = buildPlan(isAllCompleted=False)
    plan.set(PlanAction.QUIT)

    plan.trigger()

    assert calls == []
    assert plan.action == PlanAction.QUIT


def test_trigger_runs_the_action_only_once(calls):
    plan = buildPlan()
    plan.set(PlanAction.QUIT)

    plan.trigger()
    plan.trigger()

    assert calls == ["quit"]


def test_clear_cancels_the_planned_action(calls):
    plan = buildPlan()
    plan.set(PlanAction.QUIT)

    plan.clear()
    plan.trigger()

    assert calls == []
    assert plan.action is None


def test_set_and_clear_notify_observers(calls):
    notified = []
    plan = buildPlan()
    plan.changed.connect(lambda: notified.append(True))

    plan.set(PlanAction.QUIT)
    plan.clear()

    assert notified == [True, True]
    assert plan.filePath == ""
