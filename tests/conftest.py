from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from typing import ClassVar
from pathlib import Path

import pytest
from aiohttp import web
from PySide6.QtCore import QStandardPaths

QStandardPaths.setTestModeEnabled(True)

from app.config.cfg import cfg
from app.config.paths import APP_DATA_DIR
from app.engine import Engine
from app.models.pack import BinaryRuntime, FeaturePack, PackServices, TaskParser, VersionInfo
from app.models.task import Task, TaskError, TaskOptions, TaskStep
from app.platform.filesystem import deletePath
from app.services.coroutine_runner import CoroutineRunner
from app.services.task_draft import TaskDraft
from app.signal import Signal
from qfluentwidgets import ConfigItem

ANDROID_FOLDER = Path(__file__).parents[1] / "android"
collect_ignore_glob = [] if ANDROID_FOLDER.exists() else ["test_android.py"]
CRX_PATH = Path(__file__).parents[1] / "app/assets/chrome_extension.crx"

if sys.platform == "win32":
    from winloop import new_event_loop as newDesktopLoop
else:
    from uvloop import new_event_loop as newDesktopLoop

NEW_LOOP_BY_PLATFORM = {"desktop": newDesktopLoop, "android": asyncio.new_event_loop}


@dataclass(kw_only=True)
class FakeStep(TaskStep):
    sideSuffix: str = ""
    isInPartFolder: bool = False
    content: str = "downloaded"
    outcome: str = "complete"
    options: dict = field(default_factory=dict, init=False, repr=False)

    @property
    def outputPath(self) -> str:
        if self.isInPartFolder:
            return str(self.task.partPath / f"step{self.stepIndex}")
        if self.sideSuffix:
            return str(self.task.toSidePath(self.fileIndex, self.sideSuffix))
        return str(self.task.toFilePath(self.fileIndex))

    def setOptions(self, options: dict) -> None:
        self.options = options
        self.sideSuffix = options.get("sideSuffix", self.sideSuffix)

    async def run(self, reportSpeed, waitForSpeedLimit):
        if self.outcome == "complete":
            Path(self.outputPath).write_text(self.content)
            return
        Path(self.outputPath).write_bytes(b"half")
        if self.outcome == "fail":
            raise OSError("server gone")
        await asyncio.Event().wait()


@dataclass(kw_only=True, eq=False)
class FakeSeedingTask(Task):
    canSeed: ClassVar[bool] = True
    seedingOutcome: str = "hang"
    seedingRuns: list[bool] = field(default_factory=list, init=False, repr=False)

    async def runSeeding(self, isManual: bool) -> None:
        self.seedingRuns.append(isManual)
        if self.seedingOutcome == "fail":
            raise OSError("tracker gone")
        if self.seedingOutcome == "hang":
            await asyncio.Event().wait()


class FakeRuntime(BinaryRuntime):
    name = "fake"

    def __init__(self, folder: Path, progresses: list[float] = (), error: Exception | None = None,
                 isMissingAfterInstall: bool = False):
        self.folder = folder
        self.progresses = progresses
        self.error = error
        self.isMissingAfterInstall = isMissingAfterInstall

    def installFolder(self) -> Path:
        return self.folder

    def path(self) -> str:
        binary = self.folder / "fake"
        return str(binary) if binary.is_file() else ""

    async def probeVersion(self) -> VersionInfo:
        return VersionInfo("")

    def installedPaths(self) -> list[Path]:
        return [self.folder / "fake", self.folder / "lib"]

    async def install(self, version: str, onProgress) -> None:
        for progress in self.progresses:
            onProgress(progress)
            await asyncio.sleep(0)
        if self.error:
            raise self.error
        if not self.isMissingAfterInstall:
            (self.folder / "fake").write_bytes(b"bin")


class FakeParser(TaskParser):
    def match(self, options: TaskOptions) -> bool:
        return options.url.startswith("http://test/")

    async def parse(self, options: TaskOptions) -> Task:
        self.pack.parsedOptions.append(options)
        while options.url in self.pack.heldUrls:
            await asyncio.sleep(0.01)
        if options.url in self.pack.failingUrls:
            raise TaskError("network error")
        name = options.url.rsplit("/", 1)[-1]
        return Task(name=name, url=options.url, packId=self.pack.packId, steps=[FakeStep(stepIndex=0)],
                    outputFolder=options.outputFolder)


class FakePack(FeaturePack):
    packId = "test"
    parsers = [FakeParser]

    def __init__(self, services: PackServices):
        super().__init__(services)
        self.heldUrls: set[str] = set()
        self.failingUrls: set[str] = set()
        self.parsedOptions: list[TaskOptions] = []


class FakeFileWatcher:
    fileChanged = Signal(str)

    def __init__(self):
        self.paths: set[str] = set()

    def addPath(self, path: str) -> None:
        self.paths.add(path)

    def removePath(self, path: str) -> None:
        self.paths.discard(path)


class FakeRecycleBin:
    def __init__(self):
        self.isAvailable = True
        self.paths: list[Path] = []

    def delete(self, path: Path) -> bool:
        if not self.isAvailable:
            return False
        self.paths.append(path)
        deletePath(path)
        return True


@pytest.fixture
def fileWatcher():
    return FakeFileWatcher()


@pytest.fixture
def recycleBin():
    return FakeRecycleBin()


@pytest.fixture
def downloadFolder(tmp_path):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    return folder


@pytest.fixture
def blockedFolder(downloadFolder):
    (downloadFolder / "file").write_bytes(b"")
    return downloadFolder / "file" / "sub"


@pytest.fixture
def config(downloadFolder):
    for item in vars(type(cfg)).values():
        if isinstance(item, ConfigItem):
            item.value = item.defaultValue
    shutil.rmtree(APP_DATA_DIR, ignore_errors=True)
    configFile = APP_DATA_DIR / "UserConfig.json"
    configFile.parent.mkdir(parents=True)
    configFile.write_text(json.dumps({
        "GeneralDownload": {"DownloadFolder": str(downloadFolder), "ProxyServer": "Off"},
        "Browser": {"EnableBrowserExtension": False},
    }), encoding="utf-8")
    cfg.load(configFile)


@pytest.fixture
async def startEngine(config, fileWatcher, recycleBin):
    uiLoop = asyncio.get_running_loop()
    running = []

    def stop() -> None:
        for engine, hasQuit in running:
            engine.stop()
            engine.coroutineRunner.stop()
            hasQuit.set()
        running.clear()

    def start(platform: str = "desktop") -> Engine:
        stop()
        hasQuit = threading.Event()
        coroutineRunner = CoroutineRunner(
            lambda callback: uiLoop.call_soon_threadsafe(lambda: hasQuit.is_set() or callback()),
            loop=NEW_LOOP_BY_PLATFORM[platform](),
        )
        coroutineRunner.start()
        engine = Engine(coroutineRunner, fileWatcher, CRX_PATH.read_bytes, APP_DATA_DIR / "browser_extension",
                        recycleBin.delete)
        engine.featureService.register(FakePack(PackServices(coroutineRunner=coroutineRunner,
                                                             speedMeter=engine.speedMeter)))
        engine.start()
        running.append((engine, hasQuit))
        return engine

    yield start

    stop()


@pytest.fixture
def engine(startEngine):
    return startEngine()


@pytest.fixture
def draft(engine):
    return TaskDraft(engine.coroutineRunner, engine.featureService, engine.taskService.add)


@pytest.fixture
async def startServer():
    runners = []

    async def start(handler):
        app = web.Application()
        app.router.add_get("/{path:.*}", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        runners.append(runner)
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = runner.addresses[0][1]
        return f"http://127.0.0.1:{port}/file"

    yield start

    for runner in runners:
        await runner.cleanup()


@pytest.fixture
def startProgram():
    processes = []

    def start(path: Path) -> subprocess.Popen:
        if sys.platform == "win32":
            shutil.copy(Path(os.environ["SystemRoot"]) / "System32" / "PING.EXE", path)
            args = [path, "-n", "60", "127.0.0.1"]
        else:
            path.write_text("#!/bin/sh\nexec sleep 60\n")
            path.chmod(0o755)
            args = [path]
        process = subprocess.Popen(args, stdout=subprocess.DEVNULL)
        processes.append(process)
        return process

    yield start

    for process in processes:
        process.kill()
        process.wait()


def pytest_asyncio_loop_factories(config, item):
    marker = item.get_closest_marker("asyncio")
    if marker is None or "loop_factories" not in marker.kwargs:
        return {"asyncio": asyncio.new_event_loop}
    if sys.platform == "win32":
        from winloop import new_event_loop
    else:
        from uvloop import new_event_loop
    return {"asyncio": asyncio.new_event_loop, "uvloop": new_event_loop}
