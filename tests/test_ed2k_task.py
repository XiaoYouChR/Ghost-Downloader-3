import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from app.models.pack import VersionInfo
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
            upload=0,
            activePeers=0,
            peers=0,
        )
        return self.transfer

    async def resume(self, fileHash: str) -> Transfer:
        self.resumed.append(fileHash)
        return self.transfer

    async def snapshots(self):
        self.snapshotStarted.set()
        yield Snapshot(transfers=(self.transfer,), serverConnected=True, kadNodes=0)
        await asyncio.Event().wait()

    async def pause(self, fileHash: str) -> None:
        self.paused.append(fileHash)

    async def remove(self, fileHash: str, deleteFile: bool = False) -> None:
        self.removed.append(fileHash)


class DuplicateClient(FakeClient):
    async def addLink(self, link: str, outputDir: Path) -> Transfer:
        name, size, fileHash = parseEd2kLink(link)
        self.transfer = Transfer(
            hash=fileHash,
            name="payload.bin",
            path=outputDir / "payload.bin",
            size=size,
            state=TransferState.PAUSED,
            done=0,
            received=0,
            downloadRate=0,
            uploadRate=0,
            upload=0,
            activePeers=0,
            peers=0,
        )
        raise Error(ErrorCode.TRANSFER_EXISTS, "transfer already exists")


async def noLimit():
    pass


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


async def test_resume_uses_saved_hash(monkeypatch, tmp_path):
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

    fakeClient.snapshotStarted.clear()
    running = asyncio.create_task(task.steps[0].run(lambda _: None, None))
    await fakeClient.snapshotStarted.wait()
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    assert len(fakeClient.added) == 1
    assert fakeClient.resumed == [FILE_HASH]


async def test_cancel_during_addlink_preserves_identity(monkeypatch, tmp_path):
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


async def test_transfer_exists_resumes_existing(monkeypatch, tmp_path):
    fakeClient = DuplicateClient()
    session = session_module.ED2kSession()
    session._client = fakeClient
    monkeypatch.setattr(session_module, "ed2kSession", session)
    task = makeTask(tmp_path, name="payload.bin")

    running = asyncio.create_task(task.steps[0].run(lambda _: None, None))
    await fakeClient.snapshotStarted.wait()
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    assert task.fileHash == FILE_HASH
    assert fakeClient.resumed == [FILE_HASH]
    assert fakeClient.removed == []


class FinishedClient(FakeClient):
    async def addLink(self, link: str, outputDir: Path) -> Transfer:
        transfer = await super().addLink(link, outputDir)
        self.transfer = replace(
            transfer,
            state=TransferState.FINISHED,
            done=transfer.size,
            received=transfer.size,
            uploadRate=512,
        )
        return self.transfer


async def test_download_completes_when_finished(monkeypatch, tmp_path):
    fakeClient = FinishedClient()
    session = session_module.ED2kSession()
    session._client = fakeClient
    monkeypatch.setattr(session_module, "ed2kSession", session)
    task = makeTask(tmp_path)

    await task.run(lambda _: None, noLimit)

    assert task.status == TaskStatus.COMPLETED
    assert task.steps[0].receivedBytes == 1234
    assert fakeClient.paused == [FILE_HASH]
    assert not session._activeTransfers


async def completeDownload(monkeypatch, tmp_path) -> tuple[ED2kTask, FakeClient]:
    fakeClient = FinishedClient()
    session = session_module.ED2kSession()
    session._client = fakeClient
    monkeypatch.setattr(session_module, "ed2kSession", session)
    task = makeTask(tmp_path)
    await task.run(lambda _: None, noLimit)
    fakeClient.paused.clear()
    fakeClient.snapshotStarted.clear()
    return task, fakeClient


async def test_seeding_resumes_transfer_until_stopped(monkeypatch, tmp_path):
    task, fakeClient = await completeDownload(monkeypatch, tmp_path)

    seeding = asyncio.create_task(task.runSeeding(isManual=False))
    await fakeClient.snapshotStarted.wait()
    await asyncio.sleep(0)

    assert fakeClient.resumed == [FILE_HASH]
    assert task.uploadRate == 512

    seeding.cancel()
    with pytest.raises(asyncio.CancelledError):
        await seeding

    assert fakeClient.paused == [FILE_HASH]
    assert task.uploadRate == 0
    assert not session_module.ed2kSession._activeTransfers


async def test_seeding_ends_at_limit(monkeypatch, tmp_path):
    from ed2k_pack.config import ed2kConfig
    monkeypatch.setattr(ed2kConfig.seedingTimeLimit, "value", 1)
    task, fakeClient = await completeDownload(monkeypatch, tmp_path)
    task.seedingTimeSeconds = 120

    await task.runSeeding(isManual=False)

    assert fakeClient.paused == [FILE_HASH]
    assert task.seedingTimeSeconds >= 120


async def test_manual_seeding_ignores_limit(monkeypatch, tmp_path):
    from ed2k_pack.config import ed2kConfig
    monkeypatch.setattr(ed2kConfig.seedingTimeLimit, "value", 1)
    task, fakeClient = await completeDownload(monkeypatch, tmp_path)
    task.seedingTimeSeconds = 120

    seeding = asyncio.create_task(task.runSeeding(isManual=True))
    await fakeClient.snapshotStarted.wait()
    await asyncio.sleep(0)

    assert not seeding.done()
    seeding.cancel()
    with pytest.raises(asyncio.CancelledError):
        await seeding


class UploadingClient(FakeClient):
    def __init__(self, states: list[tuple[TransferState, int]]):
        super().__init__()
        self.states = states

    async def snapshots(self):
        self.snapshotStarted.set()
        for state, upload in self.states:
            self.transfer = replace(self.transfer, state=state, upload=upload)
            yield Snapshot(transfers=(self.transfer,), serverConnected=True, kadNodes=0)
        await asyncio.Event().wait()


async def test_download_adds_its_upload_to_the_task_total(monkeypatch, tmp_path):
    fakeClient = UploadingClient([
        (TransferState.DOWNLOADING, 10),
        (TransferState.FINISHED, 50),
    ])
    session = session_module.ED2kSession()
    session._client = fakeClient
    monkeypatch.setattr(session_module, "ed2kSession", session)
    task = makeTask(tmp_path)
    task.uploadedBytes = 100

    await task.run(lambda _: None, noLimit)

    assert task.uploadedBytes == 140


async def test_seeding_ends_at_share_ratio_limit(monkeypatch, tmp_path):
    from ed2k_pack.config import ed2kConfig
    monkeypatch.setattr(ed2kConfig.seedingRatioLimit, "value", 100)
    task, _ = await completeDownload(monkeypatch, tmp_path)
    fakeClient = UploadingClient([
        (TransferState.FINISHED, 0),
        (TransferState.FINISHED, 40),
    ])
    fakeClient.transfer = session_module.ed2kSession._client.transfer
    session_module.ed2kSession._client = fakeClient
    task.uploadedBytes = 1200

    await task.runSeeding(isManual=False)

    assert task.uploadedBytes == 1240
    assert task.shareRatioPercent >= 100
    assert fakeClient.paused == [FILE_HASH]


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
        await task.run(lambda _: None, noLimit)

    assert fakeClient.added == []
    session._activeTransfers.discard(identity)


class StartedClient:
    isRunning = True

    def __init__(self, executable, dataDir):
        pass

    async def start(self, settings):
        return Snapshot(transfers=(), serverConnected=False, kadNodes=0)


@pytest.mark.parametrize("version, isAccepted", [
    ("v0.2.3", False),
    ("v0.2.4", True),
    ("dev", True),
])
async def test_open_rejects_an_outdated_goed2kd(monkeypatch, version, isAccepted):
    async def probeVersion():
        return VersionInfo(version)

    monkeypatch.setattr(session_module.ed2kRuntime, "path", lambda: "/bin/goed2kd")
    monkeypatch.setattr(session_module.ed2kRuntime, "probeVersion", probeVersion)
    monkeypatch.setattr(session_module, "Client", StartedClient)
    session = session_module.ED2kSession()

    if isAccepted:
        await session._open()
        assert session._client is not None
    else:
        with pytest.raises(TaskError):
            await session._open()
        assert session._client is None


def u32(value: int) -> bytes:
    return value.to_bytes(4, "little")


@pytest.mark.parametrize("data, count", [
    (u32(2) + bytes(2 * 25), 2),
    (u32(0) + u32(2) + u32(3) + bytes(3 * 34), 3),
    (u32(0) + u32(3) + u32(1) + u32(4) + bytes(4 * 25), 4),
])
def test_count_nodes_reads_every_nodes_dat_version(data, count):
    from ed2k_pack.lists import countNodes

    assert countNodes(data) == count


@pytest.mark.parametrize("data", [b"", u32(5) + bytes(25), u32(0) + u32(2) + u32(0)])
def test_count_nodes_rejects_broken_files(data):
    from ed2k_pack.lists import countNodes

    with pytest.raises(ValueError):
        countNodes(data)


def test_count_servers_reads_the_header():
    from ed2k_pack.lists import countServers

    assert countServers(b"\xe0" + u32(13)) == 13
    with pytest.raises(ValueError):
        countServers(b"<html>")
