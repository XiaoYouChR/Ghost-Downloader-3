"""Verify the unified error propagation chain: step.run() → Task.run() → StepError."""
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.task import (
    Task, TaskStep, TaskStatus, TaskError, StepError, TaskOptions,
)


# -- Test helpers --

@dataclass(kw_only=True)
class FakeStep(TaskStep):
    raiseWith: Exception | None = None

    async def run(self) -> None:
        if self.raiseWith is not None:
            raise self.raiseWith
        self.setStatus(TaskStatus.COMPLETED)


@dataclass(kw_only=True)
class ExceptionGroupStep(TaskStep):
    innerError: Exception | None = None

    async def run(self) -> None:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._failChild())

    async def _failChild(self):
        raise self.innerError


@dataclass(kw_only=True, eq=False)
class FakeTask(Task):
    packId: str = "test"


def makeTask(*steps: TaskStep) -> FakeTask:
    t = FakeTask(name="test", url="http://example.com", steps=list(steps))
    t.status = TaskStatus.RUNNING
    return t


# -- Tests --

def test_task_error_propagation():
    """TaskError → StepError with message + params."""
    step = FakeStep(stepIndex=0, raiseWith=TaskError("Error ({code})", code=403))
    task = makeTask(step)
    try:
        asyncio.run(task.run())
        assert False, "Should have raised"
    except TaskError:
        pass
    assert step.error is not None
    assert isinstance(step.error, StepError)
    assert step.error.message == "Error ({code})"
    assert step.error.params == {"code": 403}
    assert str(step.error) == "Error (403)"
    assert step.status == TaskStatus.FAILED
    print("✓ TaskError → StepError with message + params")


def test_unexpected_exception_propagation():
    """Raw Exception → StepError with generic template + detail."""
    step = FakeStep(stepIndex=0, raiseWith=RuntimeError("disk full"))
    task = makeTask(step)
    try:
        asyncio.run(task.run())
        assert False, "Should have raised"
    except RuntimeError:
        pass
    assert step.error is not None
    assert isinstance(step.error, StepError)
    assert step.error.message == "Unexpected error: {detail}"
    assert step.error.params == {"detail": "disk full"}
    assert str(step.error) == "Unexpected error: disk full"
    assert step.status == TaskStatus.FAILED
    print("✓ RuntimeError → StepError with generic template + detail")


def test_cancelled_error_no_step_error():
    """CancelledError passes through, no StepError set."""
    async def run_and_cancel():
        step = FakeStep(stepIndex=0)
        step.raiseWith = asyncio.CancelledError()
        task = makeTask(step)
        try:
            await task.run()
            assert False
        except asyncio.CancelledError:
            pass
        assert step.error is None
        assert step.status != TaskStatus.FAILED
        print("✓ CancelledError → no StepError, no FAILED status")

    asyncio.run(run_and_cancel())


def test_last_error_returns_step_error():
    """Task.lastError returns StepError from the failed step."""
    step1 = FakeStep(stepIndex=0, raiseWith=TaskError("Step 1 failed"))
    step2 = FakeStep(stepIndex=1, raiseWith=None)
    task = makeTask(step1, step2)
    try:
        asyncio.run(task.run())
    except TaskError:
        pass
    error = task.lastError
    assert error is not None
    assert isinstance(error, StepError)
    assert error.message == "Step 1 failed"
    assert step2.error is None
    print("✓ Task.lastError returns StepError from failed step, later steps untouched")


def test_step_error_str_formatting():
    """StepError.__str__ formats message with params."""
    e = StepError("Server error ({status})", {"status": 500})
    assert str(e) == "Server error (500)"

    e2 = StepError("Simple error")
    assert str(e2) == "Simple error"

    e3 = StepError("")
    assert not e3
    assert bool(StepError("non-empty"))
    print("✓ StepError str/bool behavior correct")


def test_exception_group_unwrap():
    """ExceptionGroup from TaskGroup → step handles it, TaskError reaches Task.run()."""
    step = ExceptionGroupStep(stepIndex=0, innerError=TaskError("Inner fail"))
    task = makeTask(step)
    try:
        asyncio.run(task.run())
        assert False
    except (TaskError, ExceptionGroup):
        pass
    # The ExceptionGroup wraps TaskError. Since ExceptionGroupStep doesn't
    # catch it, Task.run()'s except Exception catches the ExceptionGroup.
    # step.error should be set (with repr of ExceptionGroup).
    assert step.error is not None
    assert step.status == TaskStatus.FAILED
    print("✓ ExceptionGroup from TaskGroup → StepError set (repr fallback)")


def test_task_error_not_serialized():
    """step.error (repr=False) is excluded from toDict."""
    step = FakeStep(stepIndex=0, raiseWith=TaskError("test error"))
    task = makeTask(step)
    try:
        asyncio.run(task.run())
    except TaskError:
        pass
    d = step.toDict()
    assert "error" not in d, f"error should not be serialized, got: {d}"
    print("✓ StepError not in serialized output")


def test_reset_clears_error():
    """step.reset() clears error to None."""
    step = FakeStep(stepIndex=0, raiseWith=TaskError("fail"))
    task = makeTask(step)
    try:
        asyncio.run(task.run())
    except TaskError:
        pass
    assert step.error is not None
    step.reset()
    assert step.error is None
    assert step.status == TaskStatus.WAITING
    print("✓ reset() clears error to None")


if __name__ == "__main__":
    test_step_error_str_formatting()
    test_task_error_propagation()
    test_unexpected_exception_propagation()
    test_cancelled_error_no_step_error()
    test_last_error_returns_step_error()
    test_exception_group_unwrap()
    test_task_error_not_serialized()
    test_reset_clears_error()
    print("\nAll tests passed.")
