"""文件选择过滤的逐分支测试（历史重构 4 次的重灾区）。

Seam S3: Task.pendingSteps()     — 选择过滤 + 排序 + COMPLETED 跳过
Seam S4: Task.currentSnapshot()  — 跨 step 的 progress/speed/receivedBytes 聚合
Seam S6: Task.setSelection()     — 标志翻转 → 过滤联动
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.models.task import Task, TaskStep, TaskFile, TaskStatus


@dataclass(kw_only=True)
class StubStep(TaskStep):
    stepIndex: int = 0
    fileIndex: int | None = None

    async def run(self, reportSpeed, waitForSpeedLimit):
        pass


def makeMultiFileTask(fileCount: int, stepsPerFile: int = 1) -> Task:
    files = [TaskFile(index=i, relativePath=f"file_{i}.dat", size=1000) for i in range(fileCount)]
    steps = []
    for fi in range(fileCount):
        for si in range(stepsPerFile):
            steps.append(StubStep(stepIndex=fi * stepsPerFile + si, fileIndex=fi))
    task = Task(name="test", url="http://test", packId="test", steps=steps, files=files)
    for step in steps:
        step._bindTask(task)
    return task


# ── S6: setSelection ──


class TestSetSelection:

    def test_toggle_deselects_file(self):
        task = makeMultiFileTask(3)
        task.setSelection([0, 2])
        assert task.files[0].selected is True
        assert task.files[1].selected is False
        assert task.files[2].selected is True

    def test_filesize_recalculated(self):
        task = makeMultiFileTask(3)
        task.setSelection([0])
        assert task.fileSize == 1000

    def test_select_all(self):
        task = makeMultiFileTask(3)
        task.setSelection([0])
        task.setSelection([0, 1, 2])
        assert all(f.selected for f in task.files)
        assert task.fileSize == 3000

    def test_empty_selection(self):
        task = makeMultiFileTask(3)
        task.setSelection([])
        assert not any(f.selected for f in task.files)
        assert task.fileSize == 0


# ── S3: _isStepSelected + pendingSteps ──


class TestStepSelection:

    def test_no_files_means_all_selected(self):
        task = Task(name="test", url="http://test", packId="test",
                    steps=[StubStep(stepIndex=0)])
        task.steps[0]._bindTask(task)
        assert task._isStepSelected(task.steps[0]) is True

    def test_step_without_fileindex_always_selected(self):
        task = makeMultiFileTask(2)
        noFileStep = StubStep(stepIndex=99)
        noFileStep._bindTask(task)
        task.steps.append(noFileStep)
        task.setSelection([])
        assert task._isStepSelected(noFileStep) is True

    def test_deselected_file_excludes_step(self):
        task = makeMultiFileTask(2)
        task.setSelection([0])
        assert task._isStepSelected(task.steps[0]) is True
        assert task._isStepSelected(task.steps[1]) is False

    def test_pending_skips_deselected(self):
        task = makeMultiFileTask(3)
        task.setStatus(TaskStatus.RUNNING)
        task.setSelection([0, 2])
        pending = list(task.pendingSteps())
        fileIndexes = [s.fileIndex for s in pending]
        assert 1 not in fileIndexes
        assert 0 in fileIndexes
        assert 2 in fileIndexes

    def test_pending_skips_completed(self):
        task = makeMultiFileTask(3)
        task.setStatus(TaskStatus.RUNNING)
        task.steps[0].status = TaskStatus.COMPLETED
        pending = list(task.pendingSteps())
        assert task.steps[0] not in pending
        assert task.steps[1] in pending

    def test_pending_sorted_by_index(self):
        task = Task(name="test", url="http://test", packId="test", steps=[
            StubStep(stepIndex=2),
            StubStep(stepIndex=0),
            StubStep(stepIndex=1),
        ])
        for s in task.steps:
            s._bindTask(task)
        task.setStatus(TaskStatus.RUNNING)
        pending = list(task.pendingSteps())
        assert [s.stepIndex for s in pending] == [0, 1, 2]

    def test_pending_stops_when_not_running(self):
        task = makeMultiFileTask(3)
        task.status = TaskStatus.PAUSED
        pending = list(task.pendingSteps())
        assert pending == []

    def test_pending_does_not_mutate_steps_order(self):
        task = Task(name="test", url="http://test", packId="test", steps=[
            StubStep(stepIndex=2),
            StubStep(stepIndex=0),
        ])
        for s in task.steps:
            s._bindTask(task)
        task.setStatus(TaskStatus.RUNNING)
        original_order = [s.stepIndex for s in task.steps]
        list(task.pendingSteps())
        assert [s.stepIndex for s in task.steps] == original_order


# ── S4: currentSnapshot ──


class TestCurrentSnapshot:

    def test_single_step(self):
        task = Task(name="test", url="http://test", packId="test", steps=[
            StubStep(stepIndex=0),
        ])
        task.steps[0]._bindTask(task)
        task.steps[0].progress = 50
        task.steps[0].speed = 1000
        task.steps[0].receivedBytes = 500
        progress, speed, received = task.currentSnapshot()
        assert progress == 50
        assert speed == 1000
        assert received == 500

    def test_multiple_steps_averages_progress(self):
        task = Task(name="test", url="http://test", packId="test", steps=[
            StubStep(stepIndex=0),
            StubStep(stepIndex=1),
        ])
        for s in task.steps:
            s._bindTask(task)
        task.steps[0].progress = 100
        task.steps[1].progress = 0
        progress, _, _ = task.currentSnapshot()
        assert progress == 50

    def test_multiple_steps_sums_speed(self):
        task = Task(name="test", url="http://test", packId="test", steps=[
            StubStep(stepIndex=0),
            StubStep(stepIndex=1),
        ])
        for s in task.steps:
            s._bindTask(task)
        task.steps[0].speed = 1000
        task.steps[1].speed = 2000
        _, speed, _ = task.currentSnapshot()
        assert speed == 3000

    def test_deselected_steps_excluded(self):
        task = makeMultiFileTask(2)
        task.steps[0].progress = 100
        task.steps[0].speed = 1000
        task.steps[0].receivedBytes = 1000
        task.steps[1].progress = 0
        task.steps[1].speed = 500
        task.steps[1].receivedBytes = 0
        task.setSelection([0])
        progress, speed, received = task.currentSnapshot()
        assert progress == 100
        assert speed == 1000
        assert received == 1000

    def test_no_selected_steps_returns_zero(self):
        task = makeMultiFileTask(2)
        task.setSelection([])
        progress, speed, received = task.currentSnapshot()
        assert progress == 0
        assert speed == 0
        assert received == 0

    def test_status_derivation_respects_selection(self):
        task = makeMultiFileTask(2)
        task.steps[0].status = TaskStatus.COMPLETED
        task.steps[1].status = TaskStatus.FAILED
        task.setSelection([0])
        task.updateStatus()
        assert task.status == TaskStatus.COMPLETED


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
