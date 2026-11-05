from __future__ import annotations

import pytest

from app.models.pack import PackServices
from app.models.task import TaskOptions, TaskStatus
from http_pack.pack import HttpPack
from tests.helpers import buildFileContent, buildRangeHandler, waitUntil

CONTENT = buildFileContent(1000)


@pytest.fixture(params=["desktop", "android"])
def engine(startEngine, request):
    return startEngine(request.param)


@pytest.fixture
def http(engine):
    services = PackServices(coroutineRunner=engine.coroutineRunner, speedMeter=engine.speedMeter)
    engine.featureService.register(HttpPack(services))
    return engine.featureService


async def test_relink_same_file_downloads_from_new_link(engine, http, startServer, downloadFolder):
    oldUrl = await startServer(buildRangeHandler(CONTENT))
    newUrl = await startServer(buildRangeHandler(CONTENT))
    task = await http.parse(TaskOptions(url=oldUrl))
    engine.taskService.add(task, autoStart=False)

    probed = await http.probe(TaskOptions(url=newUrl))
    assert task.canReuseProgress(probed)
    engine.taskService.edit(task, {}, probed)
    engine.taskService.start(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)

    assert task.url == newUrl
    assert (downloadFolder / task.name).read_bytes() == CONTENT


async def test_relink_other_file_cannot_reuse_progress(engine, http, startServer):
    task = await http.parse(TaskOptions(url=await startServer(buildRangeHandler(CONTENT))))

    probed = await http.probe(TaskOptions(url=await startServer(buildRangeHandler(CONTENT[:500]))))

    assert not task.canReuseProgress(probed)
