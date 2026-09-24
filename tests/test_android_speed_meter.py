"""engine.py 何时让 SpeedMeter 走表：它驱动 taskProgress 推送，做种时也要走。"""
from tests.test_task_service import finishRun, makeSeedTask, makeTask, service  # noqa: F401


class SpyMeter:
    def __init__(self):
        self.isRunning = False

    def start(self):
        self.isRunning = True

    def stop(self):
        self.isRunning = False


def bindEngine(bridge, taskService) -> SpyMeter:
    engine = bridge.Engine.__new__(bridge.Engine)
    engine._taskService = taskService
    engine._speedMeter = SpyMeter()
    engine._bindSpeedMeter()
    return engine._speedMeter


def test_meter_keeps_running_while_seeding(bridge, service, tmp_path):
    svc, runner = service
    meter = bindEngine(bridge, svc)
    task = makeSeedTask("sm1", tmp_path)
    svc.add(task)
    finishRun(runner, task)
    assert task.isSeeding
    assert meter.isRunning


def test_meter_stops_when_seeding_stops_and_nothing_runs(bridge, service, tmp_path):
    svc, runner = service
    meter = bindEngine(bridge, svc)
    task = makeSeedTask("sm2", tmp_path)
    svc.add(task)
    finishRun(runner, task)
    svc.stopSeeding(task)
    assert not meter.isRunning


def test_meter_keeps_running_when_seeding_stops_but_a_download_runs(bridge, service, tmp_path):
    svc, runner = service
    meter = bindEngine(bridge, svc)
    seed = makeSeedTask("sm3", tmp_path)
    svc.add(seed)
    finishRun(runner, seed)
    svc.add(makeTask("sm3-other"))
    svc.stopSeeding(seed)
    assert meter.isRunning


def test_meter_starts_for_seeding_restored_at_launch(bridge, service, tmp_path):
    from app.models.task import TaskStatus
    svc, runner = service
    meter = bindEngine(bridge, svc)
    task = makeSeedTask("sm4", tmp_path)
    task.shouldSeed = True
    task.setStatus(TaskStatus.COMPLETED)
    (tmp_path / task.name).touch()
    svc._store.loadSaved = lambda: [task]
    svc.resumeSaved()
    assert meter.isRunning
