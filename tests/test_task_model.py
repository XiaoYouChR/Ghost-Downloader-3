from app.bases.models import Task, TaskStage, TaskStatus


def _task(*statuses: TaskStatus) -> Task:
    # 造一个带若干 stage 的 Task，并把各 stage 直接置成给定状态。
    stages = [TaskStage(stageIndex=i) for i in range(len(statuses))]
    task = Task(title="movie", url="https://example.com/movie.mp4", packId="http", stages=stages)
    for stage, status in zip(stages, statuses):
        stage.status = status
    return task


def test_status_allCompletedBecomesCompleted():
    task = _task(TaskStatus.COMPLETED, TaskStatus.COMPLETED)
    assert task.updateStatus() == TaskStatus.COMPLETED


def test_status_anyFailedBecomesFailed():
    task = _task(TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.RUNNING)
    assert task.updateStatus() == TaskStatus.FAILED


def test_status_anyRunningBecomesRunning():
    task = _task(TaskStatus.COMPLETED, TaskStatus.RUNNING, TaskStatus.WAITING)
    assert task.updateStatus() == TaskStatus.RUNNING


def test_status_allPausedBecomesPaused():
    task = _task(TaskStatus.PAUSED, TaskStatus.PAUSED)
    assert task.updateStatus() == TaskStatus.PAUSED


def test_status_mixedWaitingAndPausedBecomesWaiting():
    task = _task(TaskStatus.WAITING, TaskStatus.PAUSED)
    assert task.updateStatus() == TaskStatus.WAITING


def test_serialize_roundTripPreservesStagesAndStatus():
    task = _task(TaskStatus.COMPLETED, TaskStatus.COMPLETED)

    back = Task.deserialize(task.serialize())

    assert back.taskId == task.taskId
    assert back.title == task.title
    assert back.status == TaskStatus.COMPLETED
    assert len(back.stages) == 2
