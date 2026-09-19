from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Thread

import pytest

from app.models.task import Task, TaskStep
from app.services.coroutine_runner import CoroutineRunner
from app.services.task_draft import TaskDraft

FOLDER = "/sdcard/Download"
URL = "https://example.test/a.bin"


@dataclass(kw_only=True)
class StubStep(TaskStep):
    stepIndex: int = 0
    movedTo: list[str] = field(default_factory=list)

    async def run(self, reportSpeed, waitForSpeedLimit):
        pass

    @property
    def outputPath(self) -> str:
        return self.task.outputPath

    def moveFiles(self, oldFolder, newFolder):
        self.movedTo.append(str(newFolder))
        super().moveFiles(oldFolder, newFolder)


class StubFeatureService:
    def __init__(self):
        self.parsedOptions: list = []

    async def parse(self, options):
        self.parsedOptions.append(options)
        step = StubStep(stepIndex=0)
        return Task(name="a.bin", url=options.url, packId="http", steps=[step],
                    outputFolder=options.outputFolder)


class StubCategoryService:
    def outputFolderOf(self, task):
        return None, ""


class StubTaskService:
    def __init__(self, task=None):
        self._task = task
        self.edited: dict | None = None

    def taskById(self, taskId):
        return self._task if self._task and self._task.taskId == taskId else None

    def edit(self, task, options, newTask):
        self.edited = options
        task.setOptions(options)


@pytest.fixture
def engine(bridge):
    instance = bridge.Engine.__new__(bridge.Engine)
    instance._loop = asyncio.new_event_loop()
    thread = Thread(target=instance._loop.run_forever, daemon=True)
    thread.start()

    instance._coroutineRunner = CoroutineRunner(
        dispatcher=instance._loop.call_soon_threadsafe, isAlive=None, loop=instance._loop)
    instance._featureService = StubFeatureService()
    instance._categoryService = StubCategoryService()
    instance._packAdapters = {}
    instance._draftOptions = {}
    instance._taskDraft = TaskDraft(instance._coroutineRunner, instance._featureService)

    yield instance

    instance._loop.call_soon_threadsafe(instance._loop.stop)
    thread.join(timeout=2)
    instance._loop.close()


@pytest.fixture
def parsedEngine(engine):
    engine.setDraftOutputFolder(FOLDER)
    engine.parse(URL)
    waitForParsed(engine)
    return engine


def waitForParsed(engine, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        item = next(iter(engine._taskDraft.items()), None)
        if item is not None and not item.parseId:
            return item
        time.sleep(0.01)
    raise AssertionError("解析没有收敛")


def test_parse_receives_model_typed_output_folder(parsedEngine):
    assert parsedEngine._featureService.parsedOptions[0].outputFolder == Path(FOLDER)


def test_unchanged_folder_does_not_move_the_parsed_task(parsedEngine):
    task = parsedEngine._taskDraft.items()[0].task
    assert task is not None
    assert task.outputFolder == Path(FOLDER)
    assert task.steps[0].movedTo == []


def test_draft_projection_returns_the_folder_string(parsedEngine):
    projection = json.loads(parsedEngine.draft())
    assert projection["outputFolder"] == FOLDER
    assert projection["items"][0]["isParsing"] is False


def test_draft_edit_of_the_same_folder_does_not_move_the_task(parsedEngine):
    task = parsedEngine._taskDraft.items()[0].task
    parsedEngine.applyDraftEdit(URL, json.dumps({"outputFolder": FOLDER}))
    assert task.outputFolder == Path(FOLDER)
    assert task.steps[0].movedTo == []


def test_task_edit_hands_the_service_model_types(engine, tmp_path):
    step = StubStep(stepIndex=0)
    task = Task(name="a.bin", url=URL, packId="http", steps=[step], outputFolder=tmp_path / "old")
    engine._taskService = StubTaskService(task)

    engine.applyTaskEdit(task.taskId, json.dumps({"outputFolder": str(tmp_path / "new")}))

    assert engine._taskService.edited == {"outputFolder": tmp_path / "new"}
    assert task.outputFolder == tmp_path / "new"
    assert step.movedTo == [str(tmp_path / "new")]


def test_task_edit_of_the_same_folder_edits_nothing(engine, tmp_path):
    step = StubStep(stepIndex=0)
    task = Task(name="a.bin", url=URL, packId="http", steps=[step], outputFolder=tmp_path / "old")
    engine._taskService = StubTaskService(task)

    engine.applyTaskEdit(task.taskId, json.dumps({"outputFolder": str(tmp_path / "old")}))

    assert engine._taskService.edited is None
    assert step.movedTo == []
