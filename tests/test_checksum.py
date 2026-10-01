"""Checksum 的计算与 TaskService 生命周期。

Seam: toChecksum（真实临时文件）；TaskService.startChecksum/cancelChecksum（S7 stub runner）
"""
from __future__ import annotations

import asyncio
import hashlib

import pytest

from app.models.checksum import toAlgorithms, toChecksum
from app.models.task import Task, TaskStatus
from tests.test_task_service import makeTask, service, platform, speedMeter  # noqa: F401


@pytest.mark.parametrize("algorithm", toAlgorithms())
def test_every_listed_algorithm_matches_hashlib(tmp_path, algorithm):
    path = tmp_path / "blob.bin"
    path.write_bytes(bytes(range(256)) * 64)
    hasher = hashlib.new(algorithm, path.read_bytes())
    expected = hasher.hexdigest({"shake_128": 32, "shake_256": 64}[algorithm]) \
        if algorithm.startswith("shake_") else hasher.hexdigest()

    assert asyncio.run(toChecksum(path, algorithm, lambda _: None)) == expected


def test_progress_reaches_100_for_multi_chunk_file(tmp_path, monkeypatch):
    monkeypatch.setattr("app.models.checksum.CHUNK_SIZE", 1000)
    path = tmp_path / "blob.bin"
    path.write_bytes(b"x" * 2500)
    progress: list[int] = []

    asyncio.run(toChecksum(path, "sha256", progress.append))

    assert progress == [40, 80, 100]


def test_empty_file_has_checksum(tmp_path):
    path = tmp_path / "empty"
    path.write_bytes(b"")

    assert asyncio.run(toChecksum(path, "md5", lambda _: None)) == hashlib.md5().hexdigest()


def test_checksums_survive_save_and_load():
    task = makeTask()
    task.checksums["sha256"] = "abc"

    assert Task.fromDict(task.toDict()).checksums == {"sha256": "abc"}


class TestChecksumLifecycle:

    def startOn(self, service, taskId="c1"):
        svc, runner = service
        task = makeTask(taskId)
        svc.add(task)
        task.setStatus(TaskStatus.COMPLETED)
        svc.startChecksum(task, "sha256")
        workId, done, failed = runner.submitted[-1]
        return svc, runner, task, workId, done, failed

    def test_running_checksum_reports_progress(self, service):
        svc, _, task, *_ = self.startOn(service)

        assert svc.checksumProgress(task) == 0

    def test_completed_checksum_is_saved_on_task(self, service, qtbot):
        svc, _, task, _, done, _ = self.startOn(service)

        with qtbot.waitSignal(svc.checksumCompleted, timeout=1000) as blocker:
            done("abc")

        assert blocker.args == [task, "sha256"]
        assert task.checksums == {"sha256": "abc"}
        assert svc.checksumProgress(task) is None

    def test_failed_checksum_reports_error_and_saves_nothing(self, service, qtbot):
        svc, _, task, _, _, failed = self.startOn(service)

        with qtbot.waitSignal(svc.checksumStopped, timeout=1000) as blocker:
            failed(OSError("gone"))

        assert blocker.args[0] is task
        assert "gone" in str(blocker.args[1])
        assert task.checksums == {}
        assert svc.checksumProgress(task) is None

    def test_cancel_stops_work_without_error(self, service, qtbot):
        svc, runner, task, workId, *_ = self.startOn(service)

        with qtbot.waitSignal(svc.checksumStopped, timeout=1000) as blocker:
            svc.cancelChecksum(task)

        assert blocker.args == [task, None]
        assert workId in runner.cancelled
        assert svc.checksumProgress(task) is None

    def test_delete_cancels_running_checksum(self, service):
        svc, runner, task, workId, *_ = self.startOn(service)

        svc.delete(task, shouldDeleteFiles=False)

        assert workId in runner.cancelled

    def test_redownload_cancels_checksum_and_clears_saved_ones(self, service):
        svc, runner, task, workId, *_ = self.startOn(service)
        task.checksums["md5"] = "old"

        svc.redownload(task)

        assert workId in runner.cancelled
        assert task.checksums == {}


class TestMatchChecksum:

    def test_match_ignores_case_and_surrounding_spaces(self, qapp):
        from app.view.dialogs.task_drawer import matchChecksum
        task = makeTask()
        task.checksums = {"md5": "aa11", "sha256": "bb22"}

        assert matchChecksum(task, "  BB22\n") == "sha256"

    def test_mismatch_gives_none(self, qapp):
        from app.view.dialogs.task_drawer import matchChecksum
        task = makeTask()
        task.checksums = {"md5": "aa11"}

        assert matchChecksum(task, "cc33") is None
