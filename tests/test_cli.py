from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass, field

import pytest
from PySide6.QtCore import QObject, Signal

from app.cli import Cli
from app.config.constants import VERSION
from app.platform import instance
from app.platform.instance import Invocation
from app.models.task import Task, TaskStatus
from tests.conftest import FakeStep


def buildTask(outcome: str = "hang", name: str = "a.zip") -> Task:
    return Task(name=name, url=f"http://test/{name}", packId="test", steps=[FakeStep(stepIndex=0, outcome=outcome)])


@dataclass
class FakeWindow:
    openedUris: list[list[str]] = field(default_factory=list)
    activations: int = 0

    def open(self, uris: list[str]) -> None:
        self.openedUris.append(uris)

    def activate(self) -> None:
        self.activations += 1


@pytest.fixture
def window():
    return FakeWindow()


@pytest.fixture
def cli(engine, window):
    return Cli(engine.taskService, engine.featureService.parse, engine.coroutineRunner.submit,
                       window.open, window.activate)


async def run(cli, *argv, cwd=".") -> tuple[dict, int]:
    replied = asyncio.get_running_loop().create_future()
    cli.run(Invocation(["ghd", *argv], str(cwd), replied.set_result))
    reply = await asyncio.wait_for(replied, 5)
    return json.loads(reply.output), reply.exitCode


async def test_add_returns_task_id_of_added_task(cli, engine):
    output, exitCode = await run(cli, "add", "http://test/a.zip")

    assert exitCode == 0
    [item] = output["result"]
    assert engine.taskService.taskById(item["taskId"]).name == "a.zip"


async def test_add_with_one_failing_url_adds_the_rest(cli, engine):
    engine.featureService.packById("test").failingUrls.add("http://test/b.zip")

    output, exitCode = await run(cli, "add", "http://test/a.zip", "http://test/b.zip")

    assert exitCode == 1
    added, failed = output["result"]
    assert engine.taskService.taskById(added["taskId"]).name == "a.zip"
    assert failed["url"] == "http://test/b.zip" and failed["error"]["code"] == "parseFailed"
    assert [task.name for task in engine.taskService.tasks] == ["a.zip"]


async def test_pause_unknown_task_reports_task_not_found(cli, engine):
    task = buildTask()
    engine.taskService.add(task)

    output, exitCode = await run(cli, "pause", task.taskId, "tsk_missing")

    assert exitCode == 1
    assert output["error"]["code"] == "taskNotFound"
    assert task.status == TaskStatus.RUNNING


async def test_add_without_url_reports_usage(cli):
    output, exitCode = await run(cli, "add")

    assert exitCode == 2
    assert output["error"]["code"] == "usage"


def test_help_lists_commands(cli):
    replies = []

    cli.run(Invocation(["ghd", "--help"], ".", replies.append))

    [reply] = replies
    assert reply.exitCode == 0
    assert "add" in reply.output and "wait" in reply.output
    assert not reply.output.endswith("\n")



def test_version_replies_running_version(cli):
    replies = []

    cli.run(Invocation(["ghd", "--version"], ".", replies.append))

    [reply] = replies
    assert reply.exitCode == 0
    assert reply.output == f"ghd {VERSION}"

async def test_wait_returns_when_task_completes(cli, engine):
    task = buildTask("complete")
    engine.taskService.add(task, autoStart=False)
    waiting = asyncio.ensure_future(run(cli, "wait", task.taskId))
    await asyncio.sleep(0.05)
    assert not waiting.done()

    engine.taskService.start(task)

    output, exitCode = await waiting
    assert exitCode == 0
    assert output["result"][0]["status"] == "completed"


async def test_wait_on_failing_task_exits_with_error(cli, engine):
    task = buildTask("fail")
    engine.taskService.add(task)

    output, exitCode = await run(cli, "wait", task.taskId)

    assert exitCode == 1
    assert output["result"][0]["status"] == "failed"


def test_run_with_file_path_opens_it_relative_to_cwd(cli, window, tmp_path):
    (tmp_path / "a.torrent").write_bytes(b"d4:infoe")
    replies = []

    cli.run(Invocation(["a.torrent"], str(tmp_path), replies.append))

    assert window.openedUris == [[(tmp_path / "a.torrent").resolve().as_uri()]]
    assert replies[0].exitCode == 0


@pytest.mark.parametrize("argv", [["--silence"], ["ghostdownloader://wake"]])
def test_run_silent_launch_does_not_activate(cli, window, argv):
    cli.run(Invocation(argv, "."))

    assert window.activations == 0 and window.openedUris == []


async def test_mistyped_command_reports_usage_without_activating(cli, window):
    output, exitCode = await run(cli, "ad", "http://test/a.zip")

    assert exitCode == 2
    assert output["error"]["code"] == "usage"
    assert window.activations == 0


class FakeApplication(QObject):
    openRequested = Signal(str)
    activated = Signal()


def test_open_after_crash_takes_over_stale_lock(qapp, monkeypatch):
    name = "GhostDownloader-test-stale-lock"
    monkeypatch.setattr(instance, "INSTANCE_NAME", name)
    holder = subprocess.Popen([sys.executable, "-c", f"""
import time
from PySide6.QtCore import QSharedMemory
memory = QSharedMemory({name!r})
print(memory.create(1), flush=True)
time.sleep(60)
"""], stdout=subprocess.PIPE, text=True)
    assert holder.stdout.readline().strip() == "True"
    holder.kill()
    holder.wait()

    application = FakeApplication()
    primaryInstance = instance.open(application, ["ghd"], ".")

    assert primaryInstance is not None
    primaryInstance.close()
