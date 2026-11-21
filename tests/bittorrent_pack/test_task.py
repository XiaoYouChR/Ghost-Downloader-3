import asyncio
from base64 import b64encode
from pathlib import Path

from bittorrent_pack import session as session_module
from bittorrent_pack.session import TorrentProgress
from bittorrent_pack.task import BTFile, BTTask, BTTaskStep, BTTorrentFileStep

from app.models.task import TaskStatus


class FakeSession:
    def __init__(self, onRun=None, progresses: tuple[TorrentProgress, ...] = ()):
        self.runSelections: list[set[int]] = []
        self.onRun = onRun
        self.progresses = progresses

    async def run(self, taskId, params, onProgress=None) -> bytes:
        self.runSelections.append(set(params.selectedIndexes))
        for progress in self.progresses:
            onProgress(progress)
        if self.onRun is not None:
            onRun, self.onRun = self.onRun, None
            onRun()
        return b"resume"

    def setSelection(self, taskId, selectedIndexes):
        pass

    def lastResumeData(self, taskId):
        return None


def buildTask(tmp_path: Path) -> BTTask:
    task = BTTask(
        name="pack", url="x.torrent", outputFolder=tmp_path,
        steps=[BTTaskStep(stepIndex=1)], torrentData=b64encode(b"x").decode(),
        files=[BTFile(index=0, relativePath="pack/a", size=1),
               BTFile(index=1, relativePath="pack/b", size=1, selected=False)],
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


def test_run_reports_bytes_since_last_progress(monkeypatch, tmp_path):
    progresses = tuple(buildProgress(received) for received in (100, 300, 250, 1234))
    monkeypatch.setattr(session_module, "btSession", FakeSession(progresses=progresses))
    reported = []

    asyncio.run(buildTask(tmp_path).run(reported.append, noLimit))

    assert reported == [100, 200, 0, 984]


def test_run_downloads_file_selected_near_the_end(monkeypatch, tmp_path):
    task = buildTask(tmp_path)
    fake = FakeSession(onRun=lambda: task.setSelection({0, 1}))
    monkeypatch.setattr(session_module, "btSession", fake)

    asyncio.run(task.run(lambda _: None, noLimit))

    assert fake.runSelections == [{0}, {0, 1}]
    assert task.status == TaskStatus.COMPLETED


def test_set_selection_keeps_completed_with_empty_file(monkeypatch, tmp_path):
    task = BTTask(
        name="pack", url="x.torrent", outputFolder=tmp_path,
        steps=[BTTaskStep(stepIndex=1)], torrentData=b64encode(b"x").decode(),
        files=[BTFile(index=0, relativePath="pack/a", size=10),
               BTFile(index=1, relativePath="pack/empty", size=0)],
    )
    task.setStatus(TaskStatus.RUNNING)
    progress = TorrentProgress(
        stateText="finished", peerCount=1, totalPeerCount=1, seedCount=1, isSeeding=False, isFinished=True,
        downloadRate=0, uploadRate=0, shareRatioPercent=0, seedingTimeSeconds=0, progress=100,
        receivedBytes=10, totalWanted=10, fileProgress=[10, 0],
    )
    monkeypatch.setattr(session_module, "btSession", FakeSession(progresses=(progress,)))

    asyncio.run(task.run(lambda _: None, noLimit))
    task.setSelection({1})

    assert task.status == TaskStatus.COMPLETED


def test_update_progress_from_download_step_only(tmp_path):
    task = buildTask(tmp_path)
    task.addStep(BTTorrentFileStep(stepIndex=0))
    task.step.progress = 80

    assert task.currentSnapshot()[0] == 80


def test_add_torrent_file_keeps_whole_name(tmp_path):
    task = buildTask(tmp_path)
    task.name = "Ubuntu 22.04"
    task.addStep(BTTorrentFileStep(stepIndex=0))

    assert task.placeholderPaths == [tmp_path / "Ubuntu 22.04", tmp_path / "Ubuntu 22.04.torrent"]
