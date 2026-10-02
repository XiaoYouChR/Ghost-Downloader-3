import asyncio
from base64 import b64encode
from pathlib import Path

from bittorrent_pack import android
from bittorrent_pack import session as session_module
from bittorrent_pack.session import TorrentProgress
from bittorrent_pack.task import BTFile, BTTask, BTTaskStep, BTTorrentFileStep

from app.models.task import TaskStatus


class FakeSession:
    def __init__(self, onRun=None, progresses: tuple[TorrentProgress, ...] = ()):
        self.runPriorities: list[list[int]] = []
        self.onRun = onRun
        self.progresses = progresses

    async def run(self, taskId, params, onProgress=None) -> bytes:
        self.runPriorities.append(list(params.filePriorities))
        for progress in self.progresses:
            onProgress(progress)
        if self.onRun is not None:
            onRun, self.onRun = self.onRun, None
            onRun()
        return b"resume"

    def updatePriorities(self, taskId, priorities):
        pass

    def lastResumeData(self, taskId):
        return None


def makeTask(tmp_path: Path) -> BTTask:
    task = BTTask(
        name="pack", url="x.torrent", outputFolder=tmp_path,
        steps=[BTTaskStep(stepIndex=1)], torrentData=b64encode(b"x").decode(),
        files=[BTFile(index=0, relativePath="pack/a", size=1),
               BTFile(index=1, relativePath="pack/b", size=1, selected=False, priority=0)],
    )
    task.setStatus(TaskStatus.RUNNING)
    return task


def buildProgress(received: int) -> TorrentProgress:
    return TorrentProgress(
        stateText="downloading", peerCount=1, totalPeerCount=1, seedCount=1, isSeeding=False, isFinished=False,
        downloadRate=256, uploadRate=0, shareRatioPercent=0, seedingTimeSeconds=0, progress=0,
        receivedBytes=received, totalWanted=1234, fileProgress=[received],
    )


async def noLimit():
    pass


def test_speed_meter_gets_the_bytes_received_since_the_last_progress(monkeypatch, tmp_path):
    progresses = tuple(buildProgress(received) for received in (100, 300, 250, 1234))
    monkeypatch.setattr(session_module, "btSession", FakeSession(progresses=progresses))
    reported = []

    asyncio.run(makeTask(tmp_path).run(reported.append, noLimit))

    assert reported == [100, 200, 0, 984]


def test_file_added_while_download_finishes_is_downloaded(monkeypatch, tmp_path):
    task = makeTask(tmp_path)
    fake = FakeSession(onRun=lambda: task.setSelection({0, 1}))
    monkeypatch.setattr(session_module, "btSession", fake)

    asyncio.run(task.run(lambda _: None, noLimit))

    assert fake.runPriorities == [[4, 0], [4, 4]]
    assert task.status == TaskStatus.COMPLETED


def test_completed_task_that_is_not_seeding_has_no_state_text(tmp_path):
    task = makeTask(tmp_path)
    task.setStatus(TaskStatus.COMPLETED)
    task.stateText = "checking_resume_data"

    assert android.taskFields(task)["statusText"] == ""


def test_progress_follows_the_download_only(tmp_path):
    task = makeTask(tmp_path)
    task.addStep(BTTorrentFileStep(stepIndex=0))
    task.step.progress = 80

    assert task.currentSnapshot()[0] == 80


def test_magnet_torrent_file_is_named_after_whole_task_name(tmp_path):
    task = makeTask(tmp_path)
    task.name = "Ubuntu 22.04"
    task.addStep(BTTorrentFileStep(stepIndex=0))

    assert task.placeholderPaths == [tmp_path / "Ubuntu 22.04", tmp_path / "Ubuntu 22.04.torrent"]
