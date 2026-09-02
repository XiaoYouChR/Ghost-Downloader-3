"""Task 状态推导与转换的逐分支测试。

Seam S1: Task.updateStatus() — step 状态组合 → task 状态推导
Seam S2: Task.setStatus()   — 批量状态转换行为
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.models.task import Task, TaskStep, TaskStatus, StepError


@dataclass(kw_only=True)
class StubStep(TaskStep):
    stepIndex: int = 0

    async def run(self, reportSpeed, waitForSpeedLimit):
        pass


def makeTask(*statuses: TaskStatus) -> Task:
    steps = [StubStep(stepIndex=i, status=s) for i, s in enumerate(statuses)]
    task = Task(name="test", url="http://test", packId="test", steps=steps)
    for step in steps:
        step._bindTask(task)
    return task


# ── S1: updateStatus ──


class TestUpdateStatus:

    def test_single_completed(self):
        task = makeTask(TaskStatus.COMPLETED)
        assert task.updateStatus() == TaskStatus.COMPLETED

    def test_single_failed(self):
        task = makeTask(TaskStatus.FAILED)
        assert task.updateStatus() == TaskStatus.FAILED

    def test_any_failed_means_task_failed(self):
        task = makeTask(TaskStatus.COMPLETED, TaskStatus.RUNNING, TaskStatus.FAILED)
        assert task.updateStatus() == TaskStatus.FAILED

    def test_all_completed_means_completed(self):
        task = makeTask(TaskStatus.COMPLETED, TaskStatus.COMPLETED, TaskStatus.COMPLETED)
        assert task.updateStatus() == TaskStatus.COMPLETED

    def test_completed_and_running_means_running(self):
        task = makeTask(TaskStatus.COMPLETED, TaskStatus.RUNNING)
        assert task.updateStatus() == TaskStatus.RUNNING

    def test_all_paused_means_paused(self):
        task = makeTask(TaskStatus.PAUSED, TaskStatus.PAUSED)
        assert task.updateStatus() == TaskStatus.PAUSED

    def test_all_waiting_means_waiting(self):
        task = makeTask(TaskStatus.WAITING, TaskStatus.WAITING)
        assert task.updateStatus() == TaskStatus.WAITING

    def test_paused_and_waiting_means_waiting(self):
        task = makeTask(TaskStatus.PAUSED, TaskStatus.WAITING)
        assert task.updateStatus() == TaskStatus.WAITING

    def test_no_steps_preserves_current(self):
        task = Task(name="test", url="http://test", packId="test")
        task.status = TaskStatus.RUNNING
        assert task.updateStatus() == TaskStatus.RUNNING

    def test_completed_sets_completed_at(self):
        task = makeTask(TaskStatus.COMPLETED)
        task.completedAt = 0
        task.updateStatus()
        assert task.completedAt > 0

    def test_failed_takes_priority_over_running(self):
        task = makeTask(TaskStatus.RUNNING, TaskStatus.FAILED)
        assert task.updateStatus() == TaskStatus.FAILED


# ── S2: setStatus ──


class TestSetStatus:

    def test_running_resets_failed_steps(self):
        task = makeTask(TaskStatus.COMPLETED, TaskStatus.FAILED)
        task.setStatus(TaskStatus.RUNNING)
        assert task.steps[1].status == TaskStatus.RUNNING
        assert task.steps[1].error is None

    def test_running_skips_completed_steps(self):
        task = makeTask(TaskStatus.COMPLETED, TaskStatus.WAITING)
        task.setStatus(TaskStatus.RUNNING)
        assert task.steps[0].status == TaskStatus.COMPLETED

    def test_paused_sets_speed_zero(self):
        task = makeTask(TaskStatus.RUNNING, TaskStatus.RUNNING)
        task.steps[0].speed = 1000
        task.steps[1].speed = 2000
        task.setStatus(TaskStatus.PAUSED)
        assert task.steps[0].speed == 0
        assert task.steps[1].speed == 0

    def test_no_steps_sets_directly(self):
        task = Task(name="test", url="http://test", packId="test")
        task.setStatus(TaskStatus.RUNNING)
        assert task.status == TaskStatus.RUNNING

    def test_running_resets_failed_step_progress(self):
        task = makeTask(TaskStatus.FAILED)
        task.steps[0].progress = 50
        task.steps[0].receivedBytes = 1024
        task.steps[0].error = StepError("test error")
        task.setStatus(TaskStatus.RUNNING)
        assert task.steps[0].progress == 0
        assert task.steps[0].receivedBytes == 0
        assert task.steps[0].error is None


# ── S5: 错误冒泡（Task.run 的异常处理）──


class TestErrorBubble:

    @pytest.mark.asyncio
    async def test_task_error_sets_step_error(self):
        from app.models.task import TaskError

        @dataclass(kw_only=True)
        class FailStep(TaskStep):
            stepIndex: int = 0
            async def run(self, reportSpeed, waitForSpeedLimit):
                raise TaskError("下载失败")

        task = makeTask()
        task.steps = [FailStep(stepIndex=0)]
        task.steps[0]._bindTask(task)
        task.setStatus(TaskStatus.RUNNING)

        with pytest.raises(TaskError):
            await task.run(lambda n: None, lambda: None)

        assert task.steps[0].status == TaskStatus.FAILED
        assert task.steps[0].error is not None
        assert task.status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_generic_exception_sets_step_error(self):
        @dataclass(kw_only=True)
        class CrashStep(TaskStep):
            stepIndex: int = 0
            async def run(self, reportSpeed, waitForSpeedLimit):
                raise RuntimeError("unexpected")

        task = makeTask()
        task.steps = [CrashStep(stepIndex=0)]
        task.steps[0]._bindTask(task)
        task.setStatus(TaskStatus.RUNNING)

        with pytest.raises(RuntimeError):
            await task.run(lambda n: None, lambda: None)

        assert task.steps[0].status == TaskStatus.FAILED
        assert task.steps[0].error.params["detail"] == "unexpected"

    async def test_cancelled_error_keeps_step_paused(self):
        import asyncio

        @dataclass(kw_only=True)
        class SlowStep(TaskStep):
            stepIndex: int = 0
            async def run(self, reportSpeed, waitForSpeedLimit):
                self.setStatus(TaskStatus.RUNNING)
                try:
                    await asyncio.sleep(999)
                except asyncio.CancelledError:
                    self.setStatus(TaskStatus.PAUSED)
                    raise

        task = makeTask()
        task.steps = [SlowStep(stepIndex=0)]
        task.steps[0]._bindTask(task)
        task.setStatus(TaskStatus.RUNNING)

        coro = task.run(lambda n: None, lambda: None)
        t = asyncio.ensure_future(coro)
        await asyncio.sleep(0)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t

        assert task.steps[0].status == TaskStatus.PAUSED
        assert task.status == TaskStatus.PAUSED


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
