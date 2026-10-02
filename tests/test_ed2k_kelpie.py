import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from dataclasses import dataclass

from app.models.task import TaskStatus
from ed2k_pack.config import ed2kConfig, kelpieRuntime
from ed2k_pack.kelpie import Kelpie, Settings
from ed2k_pack import pack as packModule
from ed2k_pack.pack import ED2kPack
from ed2k_pack.session import ed2kSession
from ed2k_pack.task import ED2kTask, ED2kTaskStep

EXECUTABLE = os.environ.get("KELPIE_EXECUTABLE", "")
FILE_HASH = "2D2A61A79C0E0B4B4B7E6F7A4B9F1C55"
SIZE = 1_000_000
KELPIE_BLOCK = 180 * 1024

pytestmark = pytest.mark.skipif(not EXECUTABLE, reason="设置 KELPIE_EXECUTABLE 指向本地构建的 kelpie")


class Runner:
    def __init__(self):
        self.works: list[asyncio.Task] = []

    def submit(self, work, done=None, failed=None, *args, owner=None, **kwargs) -> str:
        self.works.append(asyncio.ensure_future(work))
        return ""

    def post(self, callback, *args) -> None:
        callback(*args)


@pytest.fixture
async def engine(tmp_path, monkeypatch):
    executable = tmp_path / "bin" / "kelpie"
    executable.parent.mkdir()
    shutil.copy2(EXECUTABLE, executable)
    dataFolder = tmp_path / "ed2k_data"
    dataFolder.mkdir()
    monkeypatch.setattr(ed2kConfig.enableKad, "value", False)
    monkeypatch.setattr(ed2kConfig.shouldRefreshLists, "value", False)
    monkeypatch.setattr(kelpieRuntime, "path", lambda: str(executable))
    kelpies: list[Kelpie] = []

    def createKelpie(onNetwork):
        kelpies.append(Kelpie(
            lambda: executable, dataFolder,
            lambda: Settings(enableKad=ed2kConfig.enableKad.value, enableUpnp=False), onNetwork,
        ))
        return kelpies[-1]

    monkeypatch.setattr(packModule, "createKelpie", createKelpie)
    runner = Runner()
    engine = Engine(tmp_path, kelpies, ED2kPack(SimpleNamespace(coroutineRunner=runner)), runner)
    await engine.pack.activate()
    yield engine
    await engine.pack.deactivate()
    await asyncio.gather(*runner.works)


@dataclass
class Engine:
    folder: Path
    kelpies: list[Kelpie]
    pack: ED2kPack
    runner: Runner

    @property
    def kelpie(self) -> Kelpie:
        return self.kelpies[-1]


def writeGoed2kdState(dataFolder: Path, file: Path) -> None:
    state = {
        "version": 3,
        "user_agent": "FD3887E9230E53F744E5CA8FAF1A6F31",
        "transfers": [{
            "hash": FILE_HASH,
            "size": SIZE,
            "create_time": 1787328879185,
            "target_path": str(file),
            "paused": True,
            "resume_data": {
                "hashes": [],
                "pieces": [False],
                "downloaded_blocks": [{"PieceIndex": 0, "PieceBlock": index} for index in range(3)],
            },
        }],
    }
    (dataFolder / "state.json").write_text(json.dumps(state))


def buildTask(folder: Path) -> ED2kTask:
    task = ED2kTask(
        name="payload.bin", url=f"ed2k://|file|payload.bin|{SIZE}|{FILE_HASH}|/",
        fileSize=SIZE, outputFolder=folder,
    )
    task.addStep(ED2kTaskStep(stepIndex=1))
    task.setStatus(TaskStatus.RUNNING)
    return task


async def runUntilProgress(task: ED2kTask) -> None:
    running = asyncio.create_task(task.run(lambda _: None, lambda: asyncio.sleep(0)))
    async with asyncio.timeout(10):
        while ed2kSession.progressOf(task) is None:
            await asyncio.sleep(0.05)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running


def readStateHashes(dataFolder: Path) -> set[str]:
    return {transfer["hash"] for transfer in json.loads((dataFolder / "state.json").read_text())["transfers"]}


def isEngineAlive(executable: Path) -> bool:
    return subprocess.run(["pgrep", "-f", str(executable)], capture_output=True).returncode == 0


async def test_download_resumes_from_goed2kd_state(engine):
    file = engine.folder / "payload.bin"
    file.write_bytes(bytes(SIZE))
    writeGoed2kdState(engine.folder / "ed2k_data", file)
    task = buildTask(engine.folder)

    await runUntilProgress(task)
    await engine.kelpie.close()

    assert task.steps[0].receivedBytes == 3 * KELPIE_BLOCK


async def test_delete_removes_kelpie_state(engine):
    dataFolder = engine.folder / "ed2k_data"
    file = engine.folder / "payload.bin"
    file.write_bytes(bytes(SIZE))
    writeGoed2kdState(dataFolder, file)
    task = buildTask(engine.folder)
    await runUntilProgress(task)
    await engine.kelpie.close()
    assert FILE_HASH in readStateHashes(dataFolder)

    task.deletePlaceholders()
    await asyncio.gather(*engine.runner.works)
    await engine.kelpie.close()

    assert FILE_HASH not in readStateHashes(dataFolder)


async def test_delete_in_progress_finishes_before_deactivate_and_leaves_no_engine_process(engine):
    executable = engine.folder / "bin" / "kelpie"
    dataFolder = engine.folder / "ed2k_data"
    file = engine.folder / "payload.bin"
    file.write_bytes(bytes(SIZE))
    writeGoed2kdState(dataFolder, file)

    buildTask(engine.folder).deletePlaceholders()
    await asyncio.sleep(0)
    await engine.pack.deactivate()

    assert FILE_HASH not in readStateHashes(dataFolder)
    assert not isEngineAlive(executable)


async def waitForKadFirewalled(engine: Engine, isFirewalled: bool) -> None:
    async with asyncio.timeout(10):
        while (network := ed2kSession.network) is None or network.isKadFirewalled != isFirewalled:
            await asyncio.sleep(0.05)


async def test_kad_switch_applies_to_the_running_engine(engine, monkeypatch):
    task = buildTask(engine.folder)
    running = asyncio.create_task(task.run(lambda _: None, lambda: asyncio.sleep(0)))
    try:
        await waitForKadFirewalled(engine, False)

        monkeypatch.setattr(ed2kConfig.enableKad, "value", True)
        ed2kConfig.enableKad.valueChanged.emit(True)
        await waitForKadFirewalled(engine, True)

        monkeypatch.setattr(ed2kConfig.enableKad, "value", False)
        ed2kConfig.enableKad.valueChanged.emit(False)
        await waitForKadFirewalled(engine, False)

        assert not running.done()
    finally:
        await engine.pack.deactivate()
    with pytest.raises(asyncio.CancelledError):
        await running


async def test_deactivate_leaves_no_engine_process(engine):
    executable = engine.folder / "bin" / "kelpie"
    task = buildTask(engine.folder)
    running = asyncio.create_task(task.run(lambda _: None, lambda: asyncio.sleep(0)))
    try:
        async with asyncio.timeout(10):
            while ed2kSession.progressOf(task) is None:
                await asyncio.sleep(0.05)
        assert isEngineAlive(executable)
    finally:
        await engine.pack.deactivate()

    with pytest.raises(asyncio.CancelledError):
        await running
    assert not isEngineAlive(executable)
    assert ed2kSession.network is None


async def test_stop_leaves_no_engine_process_and_the_next_run_starts_one(engine):
    executable = engine.folder / "bin" / "kelpie"
    await runUntilProgress(buildTask(engine.folder))
    assert isEngineAlive(executable)

    await ed2kSession.stop()

    assert not isEngineAlive(executable)
    assert ed2kSession.network is None
    await runUntilProgress(buildTask(engine.folder))
    assert isEngineAlive(executable)


async def test_stop_with_an_open_run_leaves_the_engine_running(engine):
    executable = engine.folder / "bin" / "kelpie"
    task = buildTask(engine.folder)
    running = asyncio.create_task(task.run(lambda _: None, lambda: asyncio.sleep(0)))
    try:
        async with asyncio.timeout(10):
            while ed2kSession.progressOf(task) is None:
                await asyncio.sleep(0.05)

        await ed2kSession.stop()

        assert isEngineAlive(executable)
        assert not running.done()
    finally:
        running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running


async def startRun(task: ED2kTask) -> asyncio.Task:
    running = asyncio.create_task(task.run(lambda _: None, lambda: asyncio.sleep(0)))
    async with asyncio.timeout(10):
        while ed2kSession.progressOf(task) is None:
            await asyncio.sleep(0.05)
    return running


async def test_session_lifecycle_round_trip_leaves_no_engine_process(engine):
    executable = engine.folder / "bin" / "kelpie"
    running = await startRun(buildTask(engine.folder))

    await ed2kSession.stop()
    assert isEngineAlive(executable)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    await ed2kSession.stop()
    assert not isEngineAlive(executable)

    running = await startRun(buildTask(engine.folder))
    assert isEngineAlive(executable)
    await engine.pack.deactivate()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert not isEngineAlive(executable)

    await engine.pack.activate()
    running = await startRun(buildTask(engine.folder))
    assert isEngineAlive(executable)
    await engine.pack.deactivate()
    with pytest.raises(asyncio.CancelledError):
        await running

    assert not isEngineAlive(executable)
    assert len(engine.kelpies) == 2
