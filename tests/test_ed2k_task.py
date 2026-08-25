import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from app.models.task import TaskError, TaskOptions, TaskStatus
from ed2k_pack import session as session_module
from ed2k_pack.pack import ED2kParser
from ed2k_pack.python_ed2k import Snapshot, Transfer, TransferState
from ed2k_pack.python_ed2k.errors import Error, ErrorCode
from ed2k_pack.session import buildEd2kLink, parseEd2kLink, toTransferKey
from ed2k_pack.task import ED2kTask, ED2kTaskStep


FILE_HASH = "D6E4FE0BA5FD8A2F22FC9C0326481791"
LINK = f"ed2k://|file|payload.bin|1234|{FILE_HASH}|h=TESTAICH|/"


class FakeClient:
    isRunning = True

    def __init__(self):
        self.added: list[tuple[str, Path]] = []
        self.paused: list[str] = []
        self.removed: list[str] = []
        self.resumed: list[str] = []
        self.snapshotStarted = asyncio.Event()
        self.transfer: Transfer | None = None

    async def addLink(self, link: str, outputDir: Path) -> Transfer:
        self.added.append((link, outputDir))
        name, size, fileHash = parseEd2kLink(link)
        self.transfer = Transfer(
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
        return self.transfer

    async def snapshots(self):
        self.snapshotStarted.set()
        yield Snapshot(transfers=(self.transfer,))
        await asyncio.Event().wait()

    async def pause(self, fileHash: str) -> None:
        self.paused.append(fileHash)

    async def remove(self, fileHash: str, deleteFile: bool = False) -> None:
        self.removed.append(fileHash)

    async def resume(self, fileHash: str) -> Transfer:
        self.resumed.append(fileHash)
        return self.transfer


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


def test_build_ed2k_link_preserves_content_identity():
    renamed = buildEd2kLink(LINK, "payload(1).bin")

    assert parseEd2kLink(renamed) == ("payload(1).bin", 1234, FILE_HASH)
    assert renamed.endswith("|h=TESTAICH|/")


def test_session_rejects_duplicate_hash_and_size():
    session = session_module.ED2kSession()
    identity = toTransferKey(FILE_HASH.lower(), 1234)
    session._activeTransfers.add(identity)

    assert session.hasActiveTransfer(FILE_HASH, 1234)
    assert not session.hasActiveTransfer(FILE_HASH, 4321)

    session._activeTransfers.discard(identity)
    assert not session.hasActiveTransfer(FILE_HASH, 1234)


async def test_step_submits_deduplicated_task_filename(monkeypatch, tmp_path):
    fakeClient = FakeClient()
    session = session_module.ED2kSession()
    session._client = fakeClient
    monkeypatch.setattr(session_module, "ed2kSession", session)
    task = makeTask(tmp_path)

    running = asyncio.create_task(task.steps[0].run(lambda _: None, None))
    await fakeClient.snapshotStarted.wait()
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    submittedLink, submittedFolder = fakeClient.added[0]
    assert parseEd2kLink(submittedLink)[0] == "payload(1).bin"
    assert submittedFolder == tmp_path
    assert task.fileHash == FILE_HASH
    assert fakeClient.paused == [FILE_HASH]
    assert not session._activeTransfers


async def test_resume_uses_saved_hash_after_output_is_created(monkeypatch, tmp_path):
    fakeClient = FakeClient()
    session = session_module.ED2kSession()
    session._client = fakeClient
    monkeypatch.setattr(session_module, "ed2kSession", session)
    task = makeTask(tmp_path)

    firstRun = asyncio.create_task(task.steps[0].run(lambda _: None, None))
    await fakeClient.snapshotStarted.wait()
    firstRun.cancel()
    with pytest.raises(asyncio.CancelledError):
        await firstRun

    (tmp_path / task.name).touch()
    fakeClient.snapshotStarted.clear()
    secondRun = asyncio.create_task(task.steps[0].run(lambda _: None, None))
    await fakeClient.snapshotStarted.wait()
    secondRun.cancel()
    with pytest.raises(asyncio.CancelledError):
        await secondRun

    assert len(fakeClient.added) == 1
    assert fakeClient.resumed == [FILE_HASH]


async def test_pause_waits_for_transfer_identity_during_add(monkeypatch, tmp_path):
    class SlowAddClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.addStarted = asyncio.Event()
            self.addReady = asyncio.Event()

        async def addLink(self, link: str, outputDir: Path) -> Transfer:
            self.addStarted.set()
            await self.addReady.wait()
            return await super().addLink(link, outputDir)

    fakeClient = SlowAddClient()
    session = session_module.ED2kSession()
    session._client = fakeClient
    monkeypatch.setattr(session_module, "ed2kSession", session)
    task = makeTask(tmp_path)

    running = asyncio.create_task(task.steps[0].run(lambda _: None, None))
    await fakeClient.addStarted.wait()
    running.cancel()
    await asyncio.sleep(0)

    assert not running.done()

    fakeClient.addReady.set()
    with pytest.raises(asyncio.CancelledError):
        await running

    assert task.fileHash == FILE_HASH
    assert fakeClient.paused == [FILE_HASH]


async def test_finished_transfer_enters_sharing_immediately(monkeypatch, tmp_path):
    class FinishedClient(FakeClient):
        async def addLink(self, link: str, outputDir: Path) -> Transfer:
            transfer = await super().addLink(link, outputDir)
            self.transfer = replace(transfer, state=TransferState.FINISHED)
            return self.transfer

    fakeClient = FinishedClient()
    session = session_module.ED2kSession()
    session._client = fakeClient
    monkeypatch.setattr(session_module, "ed2kSession", session)
    task = makeTask(tmp_path)

    running = asyncio.create_task(task.steps[0].run(lambda _: None, None))
    await fakeClient.snapshotStarted.wait()

    assert task.isSharing
    assert task.sharingTimeSeconds == 0

    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running


async def test_parser_rejects_active_duplicate_on_add_task_page(monkeypatch, tmp_path):
    session = session_module.ED2kSession()
    identity = toTransferKey(FILE_HASH, 1234)
    session._activeTransfers.add(identity)
    monkeypatch.setattr(session_module, "ed2kSession", session)

    with pytest.raises(TaskError, match="该 eD2k 链接已在下载中"):
        await ED2kParser().parse(TaskOptions(url=LINK, outputFolder=tmp_path))

    session._activeTransfers.discard(identity)


async def test_active_duplicate_never_reaches_daemon(monkeypatch, tmp_path):
    fakeClient = FakeClient()
    session = session_module.ED2kSession()
    session._client = fakeClient
    identity = toTransferKey(FILE_HASH, 1234)
    session._activeTransfers.add(identity)
    monkeypatch.setattr(session_module, "ed2kSession", session)
    task = makeTask(tmp_path)

    with pytest.raises(TaskError, match="该 eD2k 链接已在下载中"):
        await task.steps[0].run(lambda _: None, None)

    assert fakeClient.added == []
    session._activeTransfers.discard(identity)


async def test_transfer_exists_does_not_remove_paused_transfer(monkeypatch, tmp_path):
    class DuplicateClient(FakeClient):
        async def addLink(self, link: str, outputDir: Path) -> Transfer:
            raise Error(ErrorCode.TRANSFER_EXISTS, "transfer already exists")

    fakeClient = DuplicateClient()
    session = session_module.ED2kSession()
    session._client = fakeClient
    monkeypatch.setattr(session_module, "ed2kSession", session)
    task = makeTask(tmp_path)

    with pytest.raises(TaskError, match="该 eD2k 传输已存在于 daemon 中"):
        await task.steps[0].run(lambda _: None, None)

    assert fakeClient.removed == []
    assert not session._activeTransfers
