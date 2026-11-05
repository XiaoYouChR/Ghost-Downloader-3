from __future__ import annotations

import pytest
from aiohttp import web

from app.models.pack import PackServices
from app.models.task import ResourceTaskOptions, TaskOptions
from http_pack.pack import HttpPack
from http_pack.task import HttpTask
from tests.helpers import buildFileContent, buildRangeHandler

CONTENT = buildFileContent(1000)


@pytest.fixture(params=["desktop", "android"])
def engine(startEngine, request):
    return startEngine(request.param)


@pytest.fixture
def http(engine):
    services = PackServices(coroutineRunner=engine.coroutineRunner, speedMeter=engine.speedMeter)
    engine.featureService.register(HttpPack(services))
    return engine.featureService


def buildNamedHandler(name: str, requests: list[web.Request] | None = None):
    rangeHandler = buildRangeHandler(CONTENT)

    async def handler(request: web.Request) -> web.Response:
        if requests is not None:
            requests.append(request)
        response = await rangeHandler(request)
        response.headers["Content-Disposition"] = f'attachment; filename="{name}"'
        return response
    return handler


async def test_parse_unclaimed_link_adds_plain_file(http, startServer):
    url = await startServer(buildNamedHandler("report.bin"))

    task = await http.parse(TaskOptions(url=f"{url}?id=1"))

    assert isinstance(task, HttpTask)
    assert task.name == "report.bin"
    assert task.fileSize == len(CONTENT)
    assert task.url == f"{url}?id=1"


async def test_parse_resource_with_size_sends_no_request(http, startServer):
    requests = []
    url = await startServer(buildNamedHandler("a.zip", requests))

    task = await http.parse(ResourceTaskOptions(url=url, name="a.zip", size=len(CONTENT), canUseRangeRequests=True))

    assert task.name == "a.zip"
    assert requests == []
