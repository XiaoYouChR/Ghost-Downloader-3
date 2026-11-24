from __future__ import annotations

import pytest

from app.platform import desktop
from app.services.plan import Plan, PlanAction


@pytest.fixture
def calls(monkeypatch):
    calls = []
    monkeypatch.setattr(desktop, "shutdown", lambda: calls.append("shutdown"))
    monkeypatch.setattr(desktop, "restart", lambda: calls.append("restart"))
    monkeypatch.setattr(desktop, "sleep", lambda: calls.append("sleep"))
    monkeypatch.setattr(desktop, "openFile", lambda path: calls.append(("openFile", path)))
    return calls


def buildPlan(calls, isAllCompleted: bool = True) -> Plan:
    return Plan(allCompleted=lambda: isAllCompleted, quitApp=lambda: calls.append("quit"))


@pytest.mark.parametrize("action, expected", [
    pytest.param(PlanAction.SHUTDOWN, "shutdown", id="shutdown"),
    pytest.param(PlanAction.RESTART, "restart", id="restart"),
    pytest.param(PlanAction.SLEEP, "sleep", id="sleep"),
    pytest.param(PlanAction.QUIT, "quit", id="quit"),
])
def test_trigger_runs_action_after_all_tasks_completed(calls, action, expected):
    plan = buildPlan(calls)
    plan.set(action)

    plan.trigger()

    assert calls == [expected]
    assert plan.action is None


def test_trigger_runs_open_file_with_the_chosen_path(calls, tmp_path):
    path = str(tmp_path / "a.bin")
    plan = buildPlan(calls)
    plan.set(PlanAction.OPEN_FILE, path)

    plan.trigger()

    assert calls == [("openFile", path)]


def test_trigger_waits_while_a_task_runs(calls):
    plan = buildPlan(calls, isAllCompleted=False)
    plan.set(PlanAction.QUIT)

    plan.trigger()

    assert calls == []
    assert plan.action == PlanAction.QUIT


def test_trigger_runs_action_only_once(calls):
    plan = buildPlan(calls)
    plan.set(PlanAction.QUIT)

    plan.trigger()
    plan.trigger()

    assert calls == ["quit"]


def test_clear_prevents_later_trigger_from_running_action(calls):
    cleared = []
    plan = buildPlan(calls)
    plan.set(PlanAction.QUIT, onCleared=lambda: cleared.append(True))

    plan.clear()
    plan.trigger()

    assert calls == []
    assert plan.action is None
    assert cleared == [True]
