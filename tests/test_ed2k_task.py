import asyncio
import gc
import weakref
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from ed2k_pack import android
from ed2k_pack import config as configModule
from ed2k_pack import pack as packModule
from ed2k_pack.cards import toHeldText, toShortHeldText
from ed2k_pack.config import ed2kConfig, kelpieRuntime
from ed2k_pack.detail_cards import (
    toAichHash,
    toChannelText,
    toPartCount,
    toSourceStatusText,
)
from ed2k_pack.kelpie import Error, ErrorCode, Progress, Source
from ed2k_pack.lists import parseNodeList, parseServerList
from ed2k_pack.pack import ED2kPack, ED2kParser
from ed2k_pack.session import buildSettings, ed2kSession
from ed2k_pack.task import ED2kTask, ED2kTaskStep

from app.config.cfg import cfg
from app.models.task import TaskError, TaskOptions, TaskStatus

FILE_HASH = "D6E4FE0BA5FD8A2F22FC9C0326481791"
LINK = f"ed2k://|file|payload.bin|1234|{FILE_HASH}|h=TESTAICH|/"


def buildProgress(received: int = 0, uploaded: int = 0, heldSources: int = 0, heldUntil: int = 0) -> Progress:
    return Progress(
        hash=FILE_HASH, size=1234, received=received, downloadRate=256,
        uploadRate=512, uploaded=uploaded, peers=5, activePeers=2, heldSources=heldSources, heldUntil=heldUntil,
        sources=(),
    )


class FakeRun:
    def __init__(self, *progresses: Progress, error: Error | None = None, isEndless: bool = False,
                 isCancelled: bool = False):
        self.progresses = progresses
        self.error = error
        self.isEndless = isEndless
        self.isCancelled = isCancelled
        self.started = asyncio.Event()

    async def __aiter__(self):
        for progress in self.progresses:
            yield progress
        self.started.set()
        if self.error is not None:
            raise self.error
        if self.isCancelled:
            raise asyncio.CancelledError()
        if self.isEndless:
            await asyncio.Event().wait()


class FakeKelpie:
    def __init__(self, *runs: FakeRun):
        self.runs = list(runs)
        self.opened: list[tuple[str, str, Path]] = []
        self.active: set[str] = set()
        self.stopped: list[str] = []
        self.removed: list[str] = []
        self.updateCount = 0
        self.closeCount = 0
        self.onNetwork = lambda _: None
        self.startGate: asyncio.Event | None = None
        self.exitGate: asyncio.Event | None = None
        self.removeGate: asyncio.Event | None = None

    def runDownload(self, link, file):
        return self.run("download", link, file)

    def runSeed(self, link, file):
        return self.run("seed", link, file)

    @asynccontextmanager
    async def run(self, mode, link, file):
        if link.hash in self.active:
            raise Error(ErrorCode.TRANSFER_BUSY, "busy")
        self.active.add(link.hash)
        self.opened.append((mode, link.hash, file))
        try:
            if self.startGate is not None:
                await self.startGate.wait()
            yield self.runs.pop(0)
        finally:
            self.active.discard(link.hash)
            self.stopped.append(link.hash)

    def isActive(self, hash: str) -> bool:
        return hash in self.active

    async def remove(self, hash: str) -> None:
        if self.removeGate is not None:
            await self.removeGate.wait()
        self.removed.append(hash)

    def update(self) -> None:
        self.updateCount += 1

    async def close(self) -> None:
        self.closeCount += 1
        if self.exitGate is not None:
            await self.exitGate.wait()
        self.onNetwork(None)


class FakeRunner:
    def __init__(self):
        self.works: list[asyncio.Task] = []

    def submit(self, work, done=None, failed=None, *args, owner=None, **kwargs) -> str:
        self.works.append(asyncio.ensure_future(work))
        return ""

    def post(self, callback, *args) -> None:
        callback(*args)


@pytest.fixture
def runner() -> FakeRunner:
    return FakeRunner()


@pytest.fixture
async def usePack(monkeypatch, runner):
    monkeypatch.setattr(kelpieRuntime, "path", lambda: "/bin/kelpie")
    monkeypatch.setattr(ed2kConfig.shouldRefreshLists, "value", False)

    def use(*runs: FakeRun) -> tuple[ED2kPack, FakeKelpie]:
        kelpie = FakeKelpie(*runs)

        def createKelpie(onNetwork):
            kelpie.onNetwork = onNetwork
            return kelpie

        monkeypatch.setattr(packModule, "createKelpie", createKelpie)
        return ED2kPack(SimpleNamespace(coroutineRunner=runner)), kelpie

    yield use
    await ed2kSession.close()


@pytest.fixture
def useKelpie(usePack):
    return lambda *runs: usePack(*runs)[1]


async def noLimit():
    pass


def makeTask(tmp_path: Path, name: str = "payload(1).bin") -> ED2kTask:
    task = ED2kTask(name=name, url=LINK, fileSize=1234, outputFolder=tmp_path)
    task.addStep(ED2kTaskStep(stepIndex=1))
    task.setStatus(TaskStatus.RUNNING)
    return task


async def completeDownload(useKelpie, tmp_path, *runs: FakeRun) -> tuple[ED2kTask, FakeKelpie]:
    kelpie = useKelpie(FakeRun(buildProgress(received=1234)), *runs)
    task = makeTask(tmp_path)
    await task.run(lambda _: None, noLimit)
    kelpie.opened.clear()
    kelpie.stopped.clear()
    return task, kelpie


async def test_speed_meter_gets_the_bytes_received_since_the_last_progress(useKelpie, tmp_path):
    useKelpie(FakeRun(
        buildProgress(received=100),
        buildProgress(received=300),
        buildProgress(received=250),
        buildProgress(received=1234),
    ))
    reported = []

    await makeTask(tmp_path).run(reported.append, noLimit)

    assert reported == [100, 200, 0, 984]


async def test_download_runs_to_completion_at_the_task_name(useKelpie, tmp_path):
    kelpie = useKelpie(FakeRun(
        buildProgress(received=600, uploaded=10),
        buildProgress(received=1234, uploaded=40),
    ))
    task = makeTask(tmp_path)

    await task.run(lambda _: None, noLimit)

    assert task.status == TaskStatus.COMPLETED
    assert kelpie.opened == [("download", FILE_HASH, tmp_path / "payload(1).bin")]
    assert task.steps[0].receivedBytes == 1234
    assert task.uploadedBytes == 40
    assert kelpie.stopped == [FILE_HASH]
    assert ed2kSession.progressOf(task) is None


async def test_progress_is_shown_only_while_the_run_is_open(useKelpie, tmp_path):
    run = FakeRun(buildProgress(received=100), isEndless=True)
    useKelpie(run)
    task = makeTask(tmp_path)
    assert ed2kSession.progressOf(task) is None

    running = asyncio.create_task(task.run(lambda _: None, noLimit))
    await run.started.wait()
    progress = ed2kSession.progressOf(task)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    assert (progress.uploadRate, progress.activePeers, progress.peers) == (512, 2, 5)
    assert ed2kSession.progressOf(task) is None


HELD_UNTIL = 1_000_000_000


async def readWhileHeld(useKelpie, tmp_path, heldSources: int, read):
    run = FakeRun(buildProgress(received=100, heldSources=heldSources, heldUntil=HELD_UNTIL), isEndless=True)
    useKelpie(run)
    task = makeTask(tmp_path)
    running = asyncio.create_task(task.run(lambda _: None, noLimit))
    await run.started.wait()
    result = read(task)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    return result


def heldTextsAt(*nows: int):
    return lambda task: [toHeldText(ed2kSession.progressOf(task), now) for now in nows]


async def test_held_sources_show_minutes_left_rounded_up(useKelpie, tmp_path):
    texts = await readWhileHeld(useKelpie, tmp_path, 3, heldTextsAt(
        HELD_UNTIL - 10 * 60_000, HELD_UNTIL - 2 * 60_000 - 1, HELD_UNTIL - 60_000, HELD_UNTIL - 59_999, HELD_UNTIL - 1,
    ))

    assert texts == [
        "为免被对方判为请求过频而封禁，3 个来源约 10 分钟后再请求",
        "为免被对方判为请求过频而封禁，3 个来源约 3 分钟后再请求",
        "为免被对方判为请求过频而封禁，3 个来源约 1 分钟后再请求",
        "为免被对方判为请求过频而封禁，3 个来源不到 1 分钟后再请求",
        "为免被对方判为请求过频而封禁，3 个来源不到 1 分钟后再请求",
    ]


async def test_held_sources_hint_disappears_when_due(useKelpie, tmp_path):
    assert await readWhileHeld(useKelpie, tmp_path, 3, heldTextsAt(HELD_UNTIL, HELD_UNTIL + 1)) == [None, None]


async def test_no_held_sources_no_hint(useKelpie, tmp_path):
    assert await readWhileHeld(useKelpie, tmp_path, 0, heldTextsAt(HELD_UNTIL - 60_000)) == [None]


def test_task_card_shows_the_short_held_hint():
    progress = buildProgress(received=100, heldSources=3, heldUntil=HELD_UNTIL)

    assert toShortHeldText(progress, HELD_UNTIL - 10 * 60_000) == "3 个来源约 10 分钟后恢复"
    assert toShortHeldText(progress, HELD_UNTIL - 1) == "3 个来源不到 1 分钟后恢复"
    assert toShortHeldText(progress, HELD_UNTIL) is None


def test_no_hint_without_a_run():
    assert toHeldText(None, 0) is None
    assert toShortHeldText(None, 0) is None


def buildSource(status: str, rank: int = 0) -> Source:
    return Source(address="1.2.3.4:4662", software="eMule 0.70b", status=status, rank=rank, downloadRate=0,
                  channel="server")


@pytest.mark.parametrize(("status", "rank", "text"), [
    ("transferring", 0, "传输中"),
    ("queued", 12, "排队 #12"),
    ("queued", 0, "排队"),
    ("connecting", 0, "连接中"),
    ("held", 0, "暂缓"),
    ("asking", 0, "asking"),
])
def test_source_status_text(status, rank, text):
    assert toSourceStatusText(buildSource(status, rank)) == text


@pytest.mark.parametrize(("channel", "text"), [
    ("link", "链接"),
    ("server", "服务器"),
    ("kad", "KAD"),
    ("exchange", "来源交换"),
    ("incoming", "对方连入"),
    ("dht", "dht"),
])
def test_source_channel_text(channel, text):
    assert toChannelText(channel) == text


@pytest.mark.parametrize(("size", "count"), [(1, 1), (9728000, 1), (9728001, 2), (3 * 9728000, 3)])
def test_part_count(size, count):
    assert toPartCount(size) == count


def test_aich_hash_comes_from_the_link():
    assert toAichHash(LINK) == "TESTAICH"
    assert toAichHash(f"ed2k://|file|payload.bin|1234|{FILE_HASH}|/") == ""


async def test_android_projects_held_sources_with_minutes_left(useKelpie, tmp_path, monkeypatch):
    monkeypatch.setattr("time.time", lambda: (HELD_UNTIL - 90_000) / 1000)

    held = await readWhileHeld(useKelpie, tmp_path, 3, lambda task: android.taskFields(task)["packFields"]["held"])

    assert held == {"sources": 3, "minutes": 2}


async def test_cancel_stops_the_download_run(useKelpie, tmp_path):
    run = FakeRun(buildProgress(received=100), isEndless=True)
    kelpie = useKelpie(run)
    task = makeTask(tmp_path)

    running = asyncio.create_task(task.run(lambda _: None, noLimit))
    await run.started.wait()
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    assert kelpie.stopped == [FILE_HASH]
    assert not kelpie.isActive(FILE_HASH)
    assert task.steps[0].status != TaskStatus.COMPLETED


async def test_download_closed_before_completion_is_not_completed(useKelpie, tmp_path):
    useKelpie(FakeRun(buildProgress(received=100), isCancelled=True))
    task = makeTask(tmp_path)

    with pytest.raises(asyncio.CancelledError):
        await task.run(lambda _: None, noLimit)

    assert task.steps[0].status != TaskStatus.COMPLETED


@pytest.mark.parametrize("code, message", [
    (ErrorCode.INVALID_LINK, "不是有效的 eD2k 链接"),
    (ErrorCode.OUTPUT_EXISTS, "目标文件已被占用"),
    (ErrorCode.TRANSFER_BUSY, "该 eD2k 链接已在下载中"),
    (ErrorCode.DISK_FULL, "磁盘空间不足"),
    (ErrorCode.FILE_ERROR, "无法读写文件：{detail}"),
    (ErrorCode.OUTDATED, "{name} 版本过旧，请在设置中更新"),
    (ErrorCode.START_FAILED, "{name} 启动失败：{detail}"),
    (ErrorCode.ENGINE_EXITED, "{name} 意外退出：{detail}"),
    (ErrorCode.INTERNAL, "ED2k 错误：{detail}"),
])
async def test_run_error_becomes_a_task_error(useKelpie, tmp_path, code, message):
    useKelpie(FakeRun(error=Error(code, "boom")))
    task = makeTask(tmp_path)

    with pytest.raises(TaskError) as raised:
        await task.run(lambda _: None, noLimit)

    assert raised.value.message == message
    assert task.steps[0].error.message == message
    assert ed2kSession.progressOf(task) is None


async def test_missing_runtime_never_opens_a_run(useKelpie, monkeypatch, tmp_path):
    kelpie = useKelpie()
    monkeypatch.setattr(kelpieRuntime, "path", lambda: "")
    task = makeTask(tmp_path)

    with pytest.raises(TaskError, match="未安装"):
        await task.run(lambda _: None, noLimit)

    assert kelpie.opened == []


async def test_seeding_runs_until_cancelled(useKelpie, tmp_path):
    run = FakeRun(buildProgress(received=1234, uploaded=50), isEndless=True)
    task, kelpie = await completeDownload(useKelpie, tmp_path, run)

    seeding = asyncio.create_task(task.runSeeding(isManual=False))
    await run.started.wait()

    assert kelpie.opened == [("seed", FILE_HASH, tmp_path / "payload(1).bin")]
    assert ed2kSession.progressOf(task).uploadRate == 512

    seeding.cancel()
    with pytest.raises(asyncio.CancelledError):
        await seeding

    assert kelpie.stopped == [FILE_HASH]
    assert ed2kSession.progressOf(task) is None


async def test_seeding_ends_at_time_limit(useKelpie, monkeypatch, tmp_path):
    monkeypatch.setattr(ed2kConfig.seedingTimeLimit, "value", 1)
    task, kelpie = await completeDownload(useKelpie, tmp_path, FakeRun(buildProgress(received=1234), isEndless=True))
    task.seedingTimeSeconds = 120

    await task.runSeeding(isManual=False)

    assert kelpie.stopped == [FILE_HASH]
    assert task.seedingTimeSeconds >= 120
    assert ed2kSession.progressOf(task) is None


async def test_seeding_ends_at_share_ratio_limit(useKelpie, monkeypatch, tmp_path):
    monkeypatch.setattr(ed2kConfig.seedingRatioLimit, "value", 100)
    task, kelpie = await completeDownload(useKelpie, tmp_path, FakeRun(
        buildProgress(received=1234, uploaded=1200),
        buildProgress(received=1234, uploaded=1240),
        isEndless=True,
    ))

    await task.runSeeding(isManual=False)

    assert task.uploadedBytes == 1240
    assert task.shareRatioPercent >= 100
    assert kelpie.stopped == [FILE_HASH]


async def test_manual_seeding_ignores_limit(useKelpie, monkeypatch, tmp_path):
    monkeypatch.setattr(ed2kConfig.seedingTimeLimit, "value", 1)
    run = FakeRun(buildProgress(received=1234), isEndless=True)
    task, _ = await completeDownload(useKelpie, tmp_path, run)
    task.seedingTimeSeconds = 120

    seeding = asyncio.create_task(task.runSeeding(isManual=True))
    await run.started.wait()

    assert not seeding.done()
    seeding.cancel()
    with pytest.raises(asyncio.CancelledError):
        await seeding


async def test_seeding_closed_by_kelpie_is_not_a_finished_seeding(useKelpie, tmp_path):
    task, _ = await completeDownload(useKelpie, tmp_path, FakeRun(buildProgress(received=1234), isCancelled=True))

    with pytest.raises(asyncio.CancelledError):
        await task.runSeeding(isManual=False)


async def test_seeding_failure_is_a_task_error(useKelpie, tmp_path):
    task, _ = await completeDownload(useKelpie, tmp_path, FakeRun(error=Error(ErrorCode.FILE_ERROR, "changed")))

    with pytest.raises(TaskError, match="无法读写文件"):
        await task.runSeeding(isManual=False)

    assert ed2kSession.progressOf(task) is None


def buildParser(pack: ED2kPack) -> ED2kParser:
    parser = ED2kParser()
    parser.pack = pack
    return parser


async def test_parser_rejects_an_active_link(usePack, tmp_path):
    pack, kelpie = usePack()
    kelpie.active.add(FILE_HASH)

    with pytest.raises(TaskError, match="该 eD2k 链接已在下载中"):
        await buildParser(pack).parse(TaskOptions(url=LINK, outputFolder=tmp_path))


async def test_parser_names_the_task_after_the_link(usePack, tmp_path):
    pack, _ = usePack()

    task = await buildParser(pack).parse(TaskOptions(url=f"  {LINK} ", outputFolder=tmp_path))

    assert task.name == "payload.bin"
    assert task.fileSize == 1234
    assert task.url == LINK


async def test_parser_rejects_an_invalid_link(usePack, tmp_path):
    pack, _ = usePack()

    with pytest.raises(TaskError, match="不是有效的 eD2k 链接"):
        await buildParser(pack).parse(TaskOptions(url="ed2k://|server|1.2.3.4|4661|/", outputFolder=tmp_path))


@pytest.mark.parametrize("delete", [ED2kTask.reset, ED2kTask.deletePlaceholders])
async def test_delete_and_redownload_remove_the_transfer(useKelpie, runner, tmp_path, delete):
    task, kelpie = await completeDownload(useKelpie, tmp_path)

    delete(task)
    await asyncio.gather(*runner.works)

    assert kelpie.removed == [FILE_HASH]


async def test_deleting_task_and_files_removes_the_transfer_once(useKelpie, runner, tmp_path):
    task, kelpie = await completeDownload(useKelpie, tmp_path)

    task.deleteFiles()
    task.deletePlaceholders()
    await asyncio.gather(*runner.works)

    assert kelpie.removed == [FILE_HASH]


async def test_delete_before_any_progress_removes_the_transfer(useKelpie, runner, tmp_path):
    kelpie = useKelpie()

    makeTask(tmp_path).deletePlaceholders()
    await asyncio.gather(*runner.works)

    assert kelpie.removed == [FILE_HASH]


def test_delete_without_runtime_leaves_kelpie_alone(useKelpie, runner, monkeypatch, tmp_path):
    useKelpie()
    monkeypatch.setattr(kelpieRuntime, "path", lambda: "")

    makeTask(tmp_path).deletePlaceholders()

    assert runner.works == []


async def test_close_waits_for_a_delete_in_progress(usePack, runner, tmp_path):
    pack, kelpie = usePack()
    kelpie.removeGate = asyncio.Event()
    makeTask(tmp_path).deletePlaceholders()
    await asyncio.sleep(0)

    closing = asyncio.create_task(pack.deactivate())
    for _ in range(10):
        await asyncio.sleep(0)
    closedDuringDelete = kelpie.closeCount
    kelpie.removeGate.set()
    await closing

    assert closedDuringDelete == 0
    assert kelpie.removed == [FILE_HASH]
    assert kelpie.closeCount == 1


async def test_close_is_idempotent(usePack):
    pack, kelpie = usePack()

    await pack.deactivate()
    await pack.deactivate()

    assert kelpie.closeCount == 1


async def test_run_before_open_never_starts_a_process(monkeypatch, tmp_path):
    monkeypatch.setattr(kelpieRuntime, "path", lambda: "/bin/kelpie")

    with pytest.raises(asyncio.CancelledError):
        await makeTask(tmp_path).run(lambda _: None, noLimit)


def test_no_task_is_active_before_open(tmp_path):
    assert not ed2kSession.isActive(makeTask(tmp_path))


async def test_run_after_deactivate_never_starts_the_engine(usePack, tmp_path):
    pack, kelpie = usePack(FakeRun(buildProgress(received=1234)))
    await pack.deactivate()

    with pytest.raises(asyncio.CancelledError):
        await makeTask(tmp_path).run(lambda _: None, noLimit)

    assert kelpie.opened == []


async def test_session_reopened_after_deactivate_runs_again(usePack, tmp_path):
    pack, _ = usePack()
    await pack.deactivate()
    _, kelpie = usePack(FakeRun(buildProgress(received=1234)))

    task = makeTask(tmp_path)
    await task.run(lambda _: None, noLimit)

    assert task.status == TaskStatus.COMPLETED
    assert [hash for _, hash, _ in kelpie.opened] == [FILE_HASH]


async def test_session_lifecycle_from_open_to_reopen(monkeypatch, runner, tmp_path):
    monkeypatch.setattr(kelpieRuntime, "path", lambda: "/bin/kelpie")
    monkeypatch.setattr(ed2kConfig.shouldRefreshLists, "value", False)
    held = FakeRun(buildProgress(received=100), isEndless=True)
    first = FakeKelpie(held, FakeRun(buildProgress(received=1234)))
    second = FakeKelpie(FakeRun(buildProgress(received=1234)))
    kelpies = [first, second]

    def createKelpie(onNetwork):
        kelpie = kelpies.pop(0)
        kelpie.onNetwork = onNetwork
        return kelpie

    monkeypatch.setattr(packModule, "createKelpie", createKelpie)
    pack = ED2kPack(SimpleNamespace(coroutineRunner=runner))
    await pack.activate()

    running = asyncio.create_task(makeTask(tmp_path).run(lambda _: None, noLimit))
    await held.started.wait()
    await ed2kSession.stop()
    assert first.closeCount == 0
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert ed2kSession.isIdle

    await ed2kSession.stop()
    assert first.closeCount == 1

    reconnected = makeTask(tmp_path)
    await reconnected.run(lambda _: None, noLimit)
    assert reconnected.status == TaskStatus.COMPLETED
    assert len(first.opened) == 2

    await pack.deactivate()
    assert first.closeCount == 2

    pack = ED2kPack(SimpleNamespace(coroutineRunner=runner))
    reactivated = makeTask(tmp_path)
    await reactivated.run(lambda _: None, noLimit)
    await pack.deactivate()

    assert reactivated.status == TaskStatus.COMPLETED
    assert [hash for _, hash, _ in second.opened] == [FILE_HASH]
    assert second.closeCount == 1


async def test_live_settings_reach_kelpie_once_after_reopening(usePack, watch):
    for _ in range(3):
        pack, _ = usePack()
        await pack.deactivate()
    pack, kelpie = usePack()
    changes = watch(ed2kSession.networkChanged, lambda: ed2kSession.network)

    ed2kConfig.enableKad.valueChanged.emit(ed2kConfig.enableKad.value)
    await asyncio.sleep(0)

    assert kelpie.updateCount == 1
    assert changes == [None]


async def test_closed_session_releases_kelpie(monkeypatch, runner):
    created: list[weakref.ref] = []

    def createKelpie(onNetwork):
        kelpie = FakeKelpie()
        created.append(weakref.ref(kelpie))
        return kelpie

    monkeypatch.setattr(packModule, "createKelpie", createKelpie)
    pack = ED2kPack(SimpleNamespace(coroutineRunner=runner))
    await pack.deactivate()
    gc.collect()

    assert created[0]() is None




def useInstallFolder(monkeypatch, folder: Path, payload: bytes | Exception):
    async def fetchReleaseAsset(repo, tag, asset, outputPath, onProgress):
        assert asset == configModule.buildAssetName()
        if isinstance(payload, Exception):
            outputPath.write_bytes(b"partial")
            raise payload
        outputPath.write_bytes(payload)
        onProgress(100.0)

    monkeypatch.setattr(ed2kConfig.installFolder, "value", str(folder))
    monkeypatch.setattr(configModule, "fetchReleaseAsset", fetchReleaseAsset)
    return configModule.kelpieRuntime


async def test_install_replaces_a_running_binary_with_a_new_file(monkeypatch, tmp_path):
    runtime = useInstallFolder(monkeypatch, tmp_path, b"new")
    binary = runtime.installedPaths()[0]
    binary.write_bytes(b"old")
    (tmp_path / "notes.txt").write_bytes(b"user")
    runningInode = binary.stat().st_ino
    progresses = []

    with binary.open("rb") as running:
        await runtime.install("v0.1.0", progresses.append)
        assert running.read() == b"old"

    assert binary.read_bytes() == b"new"
    assert binary.stat().st_ino != runningInode
    assert runtime.path() == str(binary)
    assert runtime.isAppManaged()
    assert progresses == [100.0]
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([binary.name, "notes.txt"])


async def test_failed_install_keeps_the_old_binary(monkeypatch, tmp_path):
    runtime = useInstallFolder(monkeypatch, tmp_path, ConnectionError("reset"))
    binary = runtime.installedPaths()[0]
    binary.write_bytes(b"old")

    with pytest.raises(ConnectionError):
        await runtime.install("v0.1.0", lambda _: None)

    assert binary.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == [binary.name]


def test_uninstall_deletes_only_the_binary(monkeypatch, tmp_path):
    runtime = useInstallFolder(monkeypatch, tmp_path, b"")
    runtime.installedPaths()[0].write_bytes(b"bin")
    (tmp_path / "goed2kd").write_bytes(b"old engine")

    runtime.delete()

    assert runtime.path() == ""
    assert [p.name for p in tmp_path.iterdir()] == ["goed2kd"]


async def test_install_clears_binaries_left_by_earlier_installs(monkeypatch, tmp_path):
    runtime = useInstallFolder(monkeypatch, tmp_path, b"new")
    binary = runtime.installedPaths()[0]
    binary.with_name(f"{binary.name}.1234abcd.old").write_bytes(b"older")

    await runtime.install("v0.1.0", lambda _: None)

    assert [p.name for p in tmp_path.iterdir()] == [binary.name]


async def test_activate_refreshes_only_stale_lists(runner, monkeypatch):
    class FakeList:
        def __init__(self, isStale: bool):
            self.isStale = lambda: isStale
            self.refreshCount = 0

        async def refresh(self):
            self.refreshCount += 1

    serverList, nodeList = FakeList(True), FakeList(False)
    monkeypatch.setattr(packModule, "serverList", serverList)
    monkeypatch.setattr(packModule, "nodeList", nodeList)
    monkeypatch.setattr(ed2kConfig.shouldRefreshLists, "value", True)
    monkeypatch.setattr(packModule, "createKelpie", lambda onNetwork: FakeKelpie())
    pack = ED2kPack(SimpleNamespace(coroutineRunner=runner))

    await pack.activate()
    await asyncio.sleep(0)
    await pack.deactivate()

    assert (serverList.refreshCount, nodeList.refreshCount) == (1, 0)


@pytest.mark.parametrize(("isEnabled", "expected"), [(True, 2048), (False, 0)])
def test_settings_follow_the_global_speed_limit(monkeypatch, isEnabled, expected):
    monkeypatch.setattr(cfg.isSpeedLimitEnabled, "value", isEnabled)
    monkeypatch.setattr(cfg.speedLimitation, "value", 2048)
    monkeypatch.setattr(ed2kConfig.uploadRateLimit, "value", 1024)

    settings = buildSettings()

    assert (settings.downloadRateLimit, settings.uploadRateLimit) == (expected, 1024)


@pytest.mark.parametrize("item", [
    cfg.isSpeedLimitEnabled, cfg.speedLimitation,
    ed2kConfig.uploadRateLimit, ed2kConfig.enableKad, ed2kConfig.enableUpnp,
])
async def test_live_setting_change_updates_kelpie(useKelpie, item):
    kelpie = useKelpie()

    item.valueChanged.emit(item.value)
    await asyncio.sleep(0)

    assert kelpie.updateCount == 1


@pytest.mark.parametrize("item", [ed2kConfig.listenPort, ed2kConfig.serverListSources, ed2kConfig.nodeListSources])
async def test_restart_setting_change_leaves_kelpie_alone(useKelpie, item):
    kelpie = useKelpie()

    item.valueChanged.emit(item.value)
    await asyncio.sleep(0)

    assert kelpie.updateCount == 0


async def test_deactivated_pack_stops_updating_kelpie(usePack):
    pack, kelpie = usePack()
    await pack.deactivate()

    ed2kConfig.enableKad.valueChanged.emit(ed2kConfig.enableKad.value)
    await asyncio.sleep(0)

    assert kelpie.closeCount == 1
    assert kelpie.updateCount == 0


@pytest.fixture
def watch():
    connections = []

    def connect(signal, read) -> list:
        changes = []
        connections.append((signal, lambda: changes.append(read())))
        signal.connect(connections[-1][1])
        return changes

    yield connect
    for signal, slot in connections:
        signal.disconnect(slot)


async def test_network_pushed_by_kelpie_is_announced_without_a_run(usePack, watch):
    network = FakeNetwork(isHighId=True)
    pack, kelpie = usePack()
    changes = watch(ed2kSession.networkChanged, lambda: ed2kSession.network)

    kelpie.onNetwork(network)
    kelpie.onNetwork(None)

    assert changes == [network, None]


@pytest.mark.parametrize("item", [ed2kConfig.enableKad, ed2kConfig.enableUpnp])
async def test_live_setting_change_announces_the_network(usePack, watch, item):
    pack, _ = usePack()
    changes = watch(ed2kSession.networkChanged, lambda: ed2kSession.network)

    item.valueChanged.emit(item.value)

    assert changes == [None]


async def test_open_and_ended_runs_are_announced(usePack, watch, tmp_path):
    pack, _ = usePack(FakeRun(buildProgress(received=1234)))
    changes = watch(ed2kSession.runsChanged, lambda: ed2kSession.isIdle)

    await makeTask(tmp_path).run(lambda _: None, noLimit)

    assert changes == [False, True]


async def test_stop_closes_an_idle_engine_and_the_next_run_still_opens(usePack, tmp_path):
    pack, kelpie = usePack(FakeRun(buildProgress(received=1234)))
    kelpie.onNetwork(FakeNetwork())

    await ed2kSession.stop()
    task = makeTask(tmp_path)
    await task.run(lambda _: None, noLimit)

    assert kelpie.closeCount == 1
    assert task.status == TaskStatus.COMPLETED


async def test_stop_leaves_an_open_run_alone(usePack, tmp_path):
    run = FakeRun(buildProgress(received=100), isEndless=True)
    pack, kelpie = usePack(run)
    running = asyncio.create_task(makeTask(tmp_path).run(lambda _: None, noLimit))
    await run.started.wait()

    await ed2kSession.stop()

    assert kelpie.closeCount == 0
    assert not running.done()
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running


async def test_stop_leaves_a_run_that_is_still_starting_alone(usePack, tmp_path):
    pack, kelpie = usePack(FakeRun(buildProgress(received=1234)))
    kelpie.startGate = asyncio.Event()
    task = makeTask(tmp_path)
    running = asyncio.create_task(task.run(lambda _: None, noLimit))
    while not kelpie.opened:
        await asyncio.sleep(0)

    await ed2kSession.stop()
    kelpie.startGate.set()
    await running

    assert kelpie.closeCount == 0
    assert task.status == TaskStatus.COMPLETED


async def test_run_during_stop_waits_for_the_old_engine_to_exit(usePack, tmp_path):
    pack, kelpie = usePack(FakeRun(buildProgress(received=1234)))
    kelpie.exitGate = asyncio.Event()
    stopping = asyncio.create_task(ed2kSession.stop())
    while kelpie.closeCount == 0:
        await asyncio.sleep(0)
    task = makeTask(tmp_path)
    running = asyncio.create_task(task.run(lambda _: None, noLimit))
    for _ in range(10):
        await asyncio.sleep(0)
    openedDuringStop = list(kelpie.opened)
    kelpie.exitGate.set()
    await stopping
    await running

    assert openedDuringStop == []
    assert task.status == TaskStatus.COMPLETED


async def test_delete_during_stop_waits_for_the_old_engine_to_exit(usePack, runner, tmp_path):
    pack, kelpie = usePack()
    kelpie.exitGate = asyncio.Event()
    stopping = asyncio.create_task(ed2kSession.stop())
    while kelpie.closeCount == 0:
        await asyncio.sleep(0)
    makeTask(tmp_path).deletePlaceholders()
    for _ in range(10):
        await asyncio.sleep(0)
    removedDuringStop = list(kelpie.removed)
    kelpie.exitGate.set()
    await stopping
    await asyncio.gather(*runner.works)

    assert removedDuringStop == []
    assert kelpie.removed == [FILE_HASH]


def u32(value: int) -> bytes:
    return value.to_bytes(4, "little")


def u16(value: int) -> bytes:
    return value.to_bytes(2, "little")


def buildContact(nodeId: int, size: int) -> bytes:
    return nodeId.to_bytes(16, "little") + bytes(size - 16)


@pytest.mark.parametrize("data, count", [
    (u32(2) + buildContact(1, 25) + buildContact(2, 25), 2),
    (u32(0) + u32(2) + u32(3) + b"".join(buildContact(i, 34) for i in range(3)), 3),
    (u32(0) + u32(3) + u32(1) + u32(4) + b"".join(buildContact(i, 25) for i in range(4)), 4),
    (u32(0) + u32(3) + u32(0) + u32(2) + b"".join(buildContact(i, 34) for i in range(2)), 2),
])
def test_parse_node_list_reads_every_nodes_dat_version(data, count):
    assert len(set(parseNodeList(data))) == count


@pytest.mark.parametrize("data", [b"", u32(5) + bytes(25), u32(0) + u32(2) + u32(0), u32(0) + u32(2) + u32(1) + bytes(25)])
def test_parse_node_list_rejects_broken_files(data):
    with pytest.raises(ValueError):
        parseNodeList(data)


def buildServer(ip: bytes, port: int) -> bytes:
    tags = [
        b"\x02" + u16(1) + b"\x01" + u16(4) + b"name",
        b"\x83\x0c" + u32(50),
        b"\x03" + u16(5) + b"users" + u32(1000),
        b"\x89\x0e\x01",
        b"\x94\x0b" + b"desc",
        b"\x87\x99" + u32(2) + b"..",
    ]
    return ip + u16(port) + u32(len(tags)) + b"".join(tags)


def test_parse_server_list_reads_every_endpoint_past_the_tags():
    servers = [buildServer(b"\x01\x02\x03\x04", 4661), buildServer(b"\x05\x06\x07\x08", 4242)]
    data = b"\x0e" + u32(2) + b"".join(servers)

    assert parseServerList(data) == [b"\x01\x02\x03\x04" + u16(4661), b"\x05\x06\x07\x08" + u16(4242)]


@pytest.mark.parametrize("data", [
    b"<html>",
    b"\xe0" + u32(0),
    b"\xe0" + u32(2) + buildServer(b"\x01\x02\x03\x04", 4661),
    b"\xe0" + u32(1) + buildServer(b"\x01\x02\x03\x04", 4661)[:-1],
])
def test_parse_server_list_rejects_broken_files(data):
    with pytest.raises(ValueError):
        parseServerList(data)


@dataclass(frozen=True)
class FakeNetwork:
    isServerConnected: bool = True
    isHighId: bool = False
    isKadFirewalled: bool = False
    kadNodes: int = 0
    isBehindCarrierNat: bool = False


@pytest.mark.parametrize("network, text", [
    (FakeNetwork(isHighId=True), "已连接服务器（HighID）"),
    (FakeNetwork(), "已连接服务器（LowID，开启 UPnP 或在路由器转发监听端口可获得 HighID）"),
    (FakeNetwork(isBehindCarrierNat=True), "已连接服务器（LowID，运营商 NAT，无法获得 HighID）"),
    (None, "未运行"),
])
async def test_server_text_explains_how_to_get_a_high_id(useKelpie, network, text):
    useKelpie().onNetwork(network)

    template, params = await ed2kConfig._probeServerText()
    assert template.format_map(params) == text


@pytest.mark.parametrize("isKadEnabled, network, text", [
    (False, FakeNetwork(kadNodes=0), "KAD 已关闭"),
    (False, None, "KAD 已关闭"),
    (True, FakeNetwork(kadNodes=12), "KAD 节点 12"),
    (True, FakeNetwork(kadNodes=12, isKadFirewalled=True), "KAD 节点 12（处于防火墙后）"),
    (True, None, "未运行"),
])
async def test_kad_text_says_when_kad_is_off(useKelpie, monkeypatch, isKadEnabled, network, text):
    monkeypatch.setattr(ed2kConfig.enableKad, "value", isKadEnabled)
    useKelpie().onNetwork(network)

    template, params = await ed2kConfig._probeKadText()
    assert template.format_map(params) == text
