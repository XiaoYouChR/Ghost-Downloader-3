"""GitHub proxy fallback 端到端测试。

使用本地 aiohttp 服务器模拟代理站宕机 → 自动 fallback 场景。

Seam S-GH1: GitHubHttpTaskStep.run() — download-time fallback
Seam S-GH2: GitHubParser.parse() — parse-time fallback chain
"""
from __future__ import annotations

import socket
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "features"))

import pytest
from aiohttp import web

from github_pack.pack import GitHubHttpTaskStep, GitHubParser
from http_pack.task import HttpTask, HttpTaskStep
from app.models.task import TaskOptions, ResourceTaskOptions, TaskStatus, TaskError


def makeFileContent(size: int) -> bytes:
    return bytes(i % 256 for i in range(size))


def rangeHandler(content: bytes):
    async def handler(request: web.Request) -> web.Response:
        rangeHeader = request.headers.get("Range")
        if rangeHeader is None:
            return web.Response(
                body=content,
                headers={"Content-Length": str(len(content)), "Accept-Ranges": "bytes"},
            )
        rangeSpec = rangeHeader.replace("bytes=", "")
        parts = rangeSpec.split("-")
        start = int(parts[0])
        end = int(parts[1]) if parts[1] else len(content) - 1
        body = content[start:end + 1]
        return web.Response(
            status=206,
            body=body,
            headers={
                "Content-Range": f"bytes {start}-{end}/{len(content)}",
                "Content-Length": str(len(body)),
            },
        )
    return handler


@pytest.fixture(autouse=True)
def noProxy(monkeypatch):
    monkeypatch.setattr("app.client.proxy", lambda: None)


@pytest.fixture
async def tmpdir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
async def server():
    runners = []

    async def start(handler):
        app = web.Application()
        app.router.add_get("/file", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        runners.append(runner)
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}/file"

    yield start

    for runner in runners:
        await runner.cleanup()


def closedPort() -> str:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}/file"


@pytest.fixture
def deadUrl():
    return closedPort()


def makeGitHubStep(url, tmpdir, *, fileSize, fallbackUrls=None,
                   subworkerCount=2, canUseRangeRequests=True):
    step = GitHubHttpTaskStep(
        stepIndex=0,
        url=url,
        fileSize=fileSize,
        subworkerCount=subworkerCount,
        canUseRangeRequests=canUseRangeRequests,
        clientProfile="raw",
        fallbackUrls=list(fallbackUrls or []),
    )
    task = HttpTask(
        name="test.bin",
        url="https://github.com/example/repo/releases/download/v1.0/file.zip",
        outputFolder=tmpdir,
        fileSize=fileSize,
        steps=[step],
    )
    step._bindTask(task)
    return task, step


async def runStep(step):
    speeds = []
    def reportSpeed(n):
        speeds.append(n)
    async def waitForSpeedLimit():
        pass
    await step.run(reportSpeed, waitForSpeedLimit)
    return speeds


# ── S-GH1: Download-time fallback ──


class TestDownloadTimeFallback:

    async def test_fallback_on_connection_refused(self, server, tmpdir, deadUrl):
        content = makeFileContent(1000)
        okUrl = await server(rangeHandler(content))

        task, step = makeGitHubStep(
            deadUrl, tmpdir, fileSize=1000, fallbackUrls=[okUrl],
        )
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        assert (tmpdir / "test.bin").read_bytes() == content
        assert step.url == okUrl

    async def test_no_fallback_on_permanent_error(self, server, tmpdir):
        content = makeFileContent(100)

        async def forbidden(request):
            return web.Response(status=403, text="Forbidden")

        forbiddenUrl = await server(forbidden)
        okUrl = await server(rangeHandler(content))

        task, step = makeGitHubStep(
            forbiddenUrl, tmpdir, fileSize=100, fallbackUrls=[okUrl],
        )
        task.setStatus(TaskStatus.RUNNING)

        with pytest.raises(TaskError, match="403"):
            await runStep(step)

    async def test_fallback_chain_tries_each(self, server, tmpdir, deadUrl):
        content = makeFileContent(500)
        okUrl = await server(rangeHandler(content))

        task, step = makeGitHubStep(
            deadUrl, tmpdir, fileSize=500, fallbackUrls=[closedPort(), okUrl],
        )
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        assert (tmpdir / "test.bin").read_bytes() == content
        assert step.url == okUrl

    async def test_all_fallbacks_exhausted(self, tmpdir, deadUrl):
        task, step = makeGitHubStep(
            deadUrl, tmpdir, fileSize=100,
            fallbackUrls=[closedPort()],
        )
        task.setStatus(TaskStatus.RUNNING)

        with pytest.raises(Exception):
            await runStep(step)


# ── S-GH2: Parse-time fallback ──


async def passThroughDelegate(options):
    step = HttpTaskStep(stepIndex=0, url=options.url, fileSize=100, clientProfile="raw")
    task = HttpTask(name="file.zip", url=options.url, fileSize=100, steps=[step])
    step._bindTask(task)
    return task


class TestParseTimeFallback:

    async def test_skips_dead_proxy(self, monkeypatch):
        parser = GitHubParser()

        callUrls = []
        async def rejectDeadProxy(options):
            callUrls.append(options.url)
            if "dead-proxy.com" in options.url:
                raise ConnectionError("refused")
            return await passThroughDelegate(options)

        parser.delegate = rejectDeadProxy
        monkeypatch.setattr("github_pack.pack.selectedProxySite", lambda: "https://dead-proxy.com")
        monkeypatch.setattr("github_pack.pack.GITHUB_PROXY_SITES", ("https://dead-proxy.com", "https://good-proxy.com"))

        options = TaskOptions(url="https://github.com/user/repo/releases/download/v1.0/file.zip")
        task = await parser.parse(options)

        assert task.packId == "github"
        assert task.url == options.url
        assert "good-proxy.com" in callUrls[-1]

    async def test_step_has_remaining_fallback_urls(self, monkeypatch):
        parser = GitHubParser()
        parser.delegate = passThroughDelegate
        monkeypatch.setattr("github_pack.pack.selectedProxySite", lambda: "https://proxy1.com")
        monkeypatch.setattr("github_pack.pack.GITHUB_PROXY_SITES", ("https://proxy1.com", "https://proxy2.com"))

        options = TaskOptions(url="https://github.com/user/repo/releases/download/v1.0/file.zip")
        task = await parser.parse(options)

        step = task.steps[0]
        assert isinstance(step, GitHubHttpTaskStep)
        assert len(step.fallbackUrls) == 2
        assert "proxy2.com" in step.fallbackUrls[0]
        assert step.fallbackUrls[1] == options.url

    async def test_resource_options_probes_proxy(self, monkeypatch):
        parser = GitHubParser()
        probedUrls = []

        async def trackingProbe(url, headers):
            probedUrls.append(url)
            raise ConnectionError("simulated")

        parser._probeProxy = trackingProbe
        parser.delegate = passThroughDelegate
        monkeypatch.setattr("github_pack.pack.selectedProxySite", lambda: "https://proxy.com")
        monkeypatch.setattr("github_pack.pack.GITHUB_PROXY_SITES", ("https://proxy.com",))

        options = ResourceTaskOptions(
            url="https://objects.githubusercontent.com/some/asset",
            name="file.zip", size=100, canUseRangeRequests=True,
        )
        task = await parser.parse(options)

        assert len(probedUrls) == 1
        assert "proxy.com" in probedUrls[0]
        assert task.url == options.url
