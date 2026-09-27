"""bridge 推给 Kotlin 的任务状态：同一次操作里的多次任务变化只推一次。"""
from tests.test_android_request import engine  # noqa: F401


def stubPushes(engine):
    engine._isTasksPending = False
    engine.tasks = lambda: "[]"
    engine.taskProgress = lambda: "{}"
    engine.keepAlive = lambda: ""


def waitForLoop(engine):
    engine.request("keepAlive")


def test_burst_of_task_changes_pushes_once(engine):
    stubPushes(engine)
    engine.changeTenTimes = lambda: [engine._onTasksChanged() for _ in range(10)]

    engine.request("changeTenTimes")
    waitForLoop(engine)

    assert engine._flows.history == ["tasks", "taskProgress", "keepAlive"]


def test_changes_after_a_push_push_again(engine):
    stubPushes(engine)

    engine.request("_onTasksChanged")
    waitForLoop(engine)
    engine.request("_onTasksChanged")
    waitForLoop(engine)

    assert engine._flows.history.count("tasks") == 2
