from pathlib import Path

import pytest

from app.models.task import TaskError, TaskOptions, TaskStatus
from ed2k_pack import session as session_module
from ed2k_pack.pack import ED2kParser
from ed2k_pack.python_ed2k import Snapshot, Transfer, TransferState
from ed2k_pack.python_ed2k.errors import Error, ErrorCode
from ed2k_pack.task import (
    ED2kTask,
    ED2kTaskStep,
    parseEd2kLink,
    withEd2kFilename,
)


FILE_HASH = "D6E4FE0BA5FD8A2F22FC9C0326481791"
LINK = f"ed2k://|file|payload.bin|1234|{FILE_HASH}|h=TESTAICH|/"


class FakeClient:
    isRunning = True

    def __init__(self):
        self.added: list[tuple[str, Path]] = []
        self.paused: list[str] = []
        self.removed: list[str] = []

    async def addLink(self, link: str, outputDir: Path) -> Transfer:
        self.added.append((link, outputDir))
        name, size, fileHash = parseEd2kLink(link)
        return Transfer(
            hash=fileHash,
            name=name,
            path=outputDir / name,
            size=size,
            state=TransferState.DOWNLOADING,
            done=0,
            received=0,
            downloadRate=0,
            uploadRate=0,
            activePeers=0,
            peers=0,
        )

    async def snapshots(self):
        link, outputDir = self.added[-1]
        name, size, fileHash = parseEd2kLink(link)
        yield Snapshot(transfers=(Transfer(
            hash=fileHash,
            name=name,
            path=outputDir / name,
            size=size,
            state=TransferState.FINISHED,
            done=size,
            received=size,
            downloadRate=0,
            uploadRate=0,
            activePeers=0,
            peers=1,
        ),))

    async def pause(self, fileHash: str) -> None:
        self.paused.append(fileHash)

    async def remove(self, fileHash: str, deleteFile: bool = False) -> None:
        self.removed.append(fileHash)


def makeTask(tmp_path: Path, name: str = "payload(1).bin") -> ED2kTask:
    task = ED2kTask(
        name=name,
        url=LINK,
        fileSize=1234,
        outputFolder=tmp_path,
    )
    task.addStep(ED2kTaskStep(stepIndex=1))
    task.setStatus(TaskStatus.RUNNING)
    return task


def test_with_ed2k_filename_preserves_content_identity():
    renamed = withEd2kFilename(LINK, "payload(1).bin")

    assert parseEd2kLink(renamed) == ("payload(1).bin", 1234, FILE_HASH)
    assert renamed.endswith("|h=TESTAICH|/")


def test_session_rejects_duplicate_hash_and_size():
    session = session_module.ED2kSession()
    identity = session.acquireTransfer(FILE_HASH.lower(), 1234)

    with pytest.raises(TaskError, match="该 eD2k 链接已在下载中"):
        session.acquireTransfer(FILE_HASH, 1234)

    differentSize = session.acquireTransfer(FILE_HASH, 4321)
    session.releaseTransfer(differentSize)
    session.releaseTransfer(identity)

    identity = session.acquireTransfer(FILE_HASH, 1234)
    session.releaseTransfer(identity)


async def test_step_submits_deduplicated_task_filename(monkeypatch, tmp_path):
    fakeClient = FakeClient()
    session = session_module.ED2kSession()
    session._client = fakeClient
    monkeypatch.setattr(session_module, "ed2kSession", session)
    task = makeTask(tmp_path)

    await task.steps[0].run(lambda _: None, None)

    submittedLink, submittedFolder = fakeClient.added[0]
    assert parseEd2kLink(submittedLink)[0] == "payload(1).bin"
    assert submittedFolder == tmp_path
    assert fakeClient.paused == [FILE_HASH]
    assert not session._activeTransfers


async def test_parser_rejects_active_duplicate_on_add_task_page(monkeypatch, tmp_path):
    session = session_module.ED2kSession()
    identity = session.acquireTransfer(FILE_HASH, 1234)
    monkeypatch.setattr(session_module, "ed2kSession", session)

    with pytest.raises(TaskError, match="该 eD2k 链接已在下载中"):
        await ED2kParser().parse(TaskOptions(url=LINK, outputFolder=tmp_path))

    session.releaseTransfer(identity)


async def test_active_duplicate_never_reaches_daemon(monkeypatch, tmp_path):
    fakeClient = FakeClient()
    session = session_module.ED2kSession()
    session._client = fakeClient
    identity = session.acquireTransfer(FILE_HASH, 1234)
    monkeypatch.setattr(session_module, "ed2kSession", session)
    task = makeTask(tmp_path)

    with pytest.raises(TaskError, match="该 eD2k 链接已在下载中"):
        await task.steps[0].run(lambda _: None, None)

    assert fakeClient.added == []
    session.releaseTransfer(identity)


async def test_transfer_exists_does_not_remove_first_download(monkeypatch, tmp_path):
    class DuplicateClient(FakeClient):
        async def addLink(self, link: str, outputDir: Path) -> Transfer:
            raise Error(ErrorCode.TRANSFER_EXISTS, "transfer already exists")

    fakeClient = DuplicateClient()
    session = session_module.ED2kSession()
    session._client = fakeClient
    monkeypatch.setattr(session_module, "ed2kSession", session)
    task = makeTask(tmp_path)

    with pytest.raises(TaskError, match="该 eD2k 链接已在下载中"):
        await task.steps[0].run(lambda _: None, None)

    assert fakeClient.removed == []
    assert not session._activeTransfers
