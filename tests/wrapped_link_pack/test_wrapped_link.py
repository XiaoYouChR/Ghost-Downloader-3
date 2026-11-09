from __future__ import annotations

import base64

import pytest

from app.models.pack import PackServices
from app.models.task import TaskError, TaskOptions
from http_pack.pack import HttpPack
from http_pack.task import HttpTask
from tests.helpers import buildFileContent, buildRangeHandler
from wrapped_link_pack.pack import WrappedLinkPack, toInnerUrl

INNER = "https://example.com/files/a.zip?sign=1&expires=2"
ED2K = "ed2k://|file|[SubGroup] Show 01.mkv|1024|0123456789ABCDEF0123456789ABCDEF|/"


def wrap(scheme: str, text: bytes) -> str:
    return f"{scheme}://{base64.b64encode(text).decode()}"


@pytest.fixture(params=["desktop", "android"])
def engine(startEngine, request):
    return startEngine(request.param)


@pytest.fixture
def features(engine):
    services = PackServices(coroutineRunner=engine.coroutineRunner, speedMeter=engine.speedMeter)
    for pack in (HttpPack(services), WrappedLinkPack(services)):
        engine.featureService.register(pack)
    return engine.featureService


@pytest.mark.parametrize("link", [
    pytest.param(wrap("thunder", f"AA{INNER}ZZ".encode()), id="thunder"),
    pytest.param(wrap("Thunder", f"AA{INNER}ZZ".encode()).rstrip("=") + "/", id="thunder-unpadded"),
    pytest.param(wrap("flashget", f"[FLASHGET]{INNER}[FLASHGET]".encode()) + "&abc", id="flashget"),
    pytest.param(wrap("qqdl", INNER.encode()), id="qqdl"),
])
def test_to_inner_url_unwraps_link(link):
    assert toInnerUrl(link) == INNER


def test_to_inner_url_unwraps_ed2k_link_with_bracketed_name():
    assert toInnerUrl(wrap("thunder", f"AA{ED2K}ZZ".encode())) == ED2K


def test_to_inner_url_reads_gbk_link():
    assert toInnerUrl(wrap("thunder", b"AA" + "https://example.com/中文.zip".encode("gbk") + b"ZZ")) == \
        "https://example.com/中文.zip"


@pytest.mark.parametrize("link", [
    pytest.param(wrap("thunder", b"AA" + wrap("qqdl", INNER.encode()).encode() + b"ZZ"), id="nested"),
    pytest.param("thunder://!!!", id="not-base64"),
    pytest.param(wrap("thunder", INNER.encode()), id="missing-marker"),
])
def test_to_inner_url_rejects_unknown_link(link):
    with pytest.raises(TaskError):
        toInnerUrl(link)


async def test_parse_wrapped_link_adds_task_of_inner_link(features, startServer):
    url = await startServer(buildRangeHandler(buildFileContent(100)))

    task = await features.parse(TaskOptions(url=wrap("thunder", f"AA{url}ZZ".encode())))

    assert isinstance(task, HttpTask)
    assert task.url == url


async def test_relink_wrapped_link_updates_to_inner_link(engine, features, startServer):
    content = buildFileContent(100)
    oldUrl = await startServer(buildRangeHandler(content))
    newUrl = await startServer(buildRangeHandler(content))
    task = await features.parse(TaskOptions(url=oldUrl))
    engine.taskService.add(task, autoStart=False)

    newTask = await features.parse(TaskOptions(url=wrap("qqdl", newUrl.encode())))
    engine.taskService.edit(task, {}, newTask)

    assert task.url == newUrl
