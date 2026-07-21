"""HTTP subworker 边界情况测试——防止文件损坏和静默失败。

使用本地 aiohttp 服务器精确控制服务器行为。

Seam S13a: 范围正确性（无重叠、无间隙）
Seam S13c: 服务器降级（200-for-range、403）
Seam S13e: 请求构造（_effectiveHeaders 一致性）
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest
from aiohttp import web

from features.http_pack.task import HttpTask, HttpTaskStep, PermanentDownloadError
from app.models.task import TaskStatus, TaskError


# ── Test server ──


def makeFileContent(size: int) -> bytes:
    return bytes(i % 256 for i in range(size))


def rangeHandler(content: bytes):
    """Standard HTTP range server."""
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


@pytest.fixture
async def tmpdir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
async def server():
    """Yields a factory: call with a handler to get a base URL."""
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


def makeStep(url: str, tmpdir: Path, *, fileSize: int, subworkerCount: int = 2,
             canUseRangeRequests: bool = True, userAgent: str = "",
             clientProfile: str = "raw") -> tuple[HttpTask, HttpTaskStep]:
    step = HttpTaskStep(
        stepIndex=0,
        url=url,
        fileSize=fileSize,
        subworkerCount=subworkerCount,
        canUseRangeRequests=canUseRangeRequests,
        userAgent=userAgent,
        clientProfile=clientProfile,
    )
    task = HttpTask(
        name="test.bin",
        url=url,
        outputFolder=tmpdir,
        fileSize=fileSize,
        steps=[step],
    )
    step._bindTask(task)
    return task, step


async def runStep(step: HttpTaskStep) -> list[int]:
    """Run a step, collect reported speeds, return them."""
    speeds = []

    def reportSpeed(n):
        speeds.append(n)

    async def waitForSpeedLimit():
        pass

    await step.run(reportSpeed, waitForSpeedLimit)
    return speeds


# ── S13a: Range correctness ──


class TestRangeCorrectness:

    def test_buildSubworkers_two_workers_no_overlap(self):
        step = HttpTaskStep(stepIndex=0, url="", fileSize=1000,
                            subworkerCount=2, canUseRangeRequests=True)
        sws = step._buildSubworkers()
        assert len(sws) == 2
        assert sws[0].start == 0
        assert sws[0].end == 499
        assert sws[1].start == 500
        assert sws[1].end == 999

    def test_buildSubworkers_full_coverage(self):
        step = HttpTaskStep(stepIndex=0, url="", fileSize=1000,
                            subworkerCount=3, canUseRangeRequests=True)
        sws = step._buildSubworkers()
        covered = set()
        for sw in sws:
            for b in range(sw.start, sw.end + 1):
                assert b not in covered, f"byte {b} covered twice"
                covered.add(b)
        assert covered == set(range(1000))

    def test_buildSubworkers_one_byte_file(self):
        step = HttpTaskStep(stepIndex=0, url="", fileSize=1,
                            subworkerCount=1, canUseRangeRequests=True)
        sws = step._buildSubworkers()
        assert len(sws) == 1
        assert sws[0].start == 0
        assert sws[0].end == 0

    def test_buildSubworkers_clamps_to_filesize(self):
        step = HttpTaskStep(stepIndex=0, url="", fileSize=3,
                            subworkerCount=10, canUseRangeRequests=True)
        sws = step._buildSubworkers()
        assert len(sws) == 3

    def test_buildSubworkers_no_range_support(self):
        step = HttpTaskStep(stepIndex=0, url="", fileSize=1000,
                            subworkerCount=4, canUseRangeRequests=False)
        sws = step._buildSubworkers()
        assert len(sws) == 1
        assert sws[0].end == -1

    async def test_download_produces_correct_file(self, server, tmpdir):
        content = makeFileContent(1000)
        url = await server(rangeHandler(content))
        task, step = makeStep(url, tmpdir, fileSize=1000, subworkerCount=2)
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        result = (tmpdir / "test.bin").read_bytes()
        assert result == content

    async def test_single_subworker_correct(self, server, tmpdir):
        content = makeFileContent(500)
        url = await server(rangeHandler(content))
        task, step = makeStep(url, tmpdir, fileSize=500, subworkerCount=1)
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        assert (tmpdir / "test.bin").read_bytes() == content

    async def test_many_subworkers_correct(self, server, tmpdir):
        content = makeFileContent(100)
        url = await server(rangeHandler(content))
        task, step = makeStep(url, tmpdir, fileSize=100, subworkerCount=10)
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        assert (tmpdir / "test.bin").read_bytes() == content


# ── S13c: Server degradation ──


class TestServerDegradation:

    async def test_403_raises_permanent_error(self, server, tmpdir):
        async def forbidden(request):
            return web.Response(status=403, text="Forbidden")

        url = await server(forbidden)
        task, step = makeStep(url, tmpdir, fileSize=100, subworkerCount=1)
        task.setStatus(TaskStatus.RUNNING)

        with pytest.raises(TaskError, match="403"):
            await runStep(step)

    async def test_cloudflare_mitigated_raises_permanent(self, server, tmpdir):
        async def cfMitigated(request):
            return web.Response(
                status=403,
                headers={"cf-mitigated": "challenge"},
                text="Cloudflare",
            )

        url = await server(cfMitigated)
        task, step = makeStep(url, tmpdir, fileSize=100, subworkerCount=1)
        task.setStatus(TaskStatus.RUNNING)

        with pytest.raises(TaskError):
            await runStep(step)

    async def test_no_range_support_downloads_full(self, server, tmpdir):
        """Server doesn't support ranges — step falls back to single full download."""
        content = makeFileContent(500)

        async def noRange(request):
            return web.Response(
                body=content,
                headers={"Content-Length": str(len(content))},
            )

        url = await server(noRange)
        task, step = makeStep(url, tmpdir, fileSize=500, subworkerCount=1,
                              canUseRangeRequests=False)
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)
        assert (tmpdir / "test.bin").read_bytes() == content


# ── S13e: Request construction ──


class TestRequestConstruction:

    async def test_effective_headers_include_user_agent(self, server, tmpdir):
        """All subworker paths should send the configured User-Agent.

        Known bug: normal-range path uses self.headers instead of
        self._effectiveHeaders, potentially omitting User-Agent.
        """
        receivedHeaders: list[dict] = []

        async def captureHeaders(request):
            receivedHeaders.append(dict(request.headers))
            rangeHeader = request.headers.get("Range")
            content = makeFileContent(100)
            if rangeHeader:
                parts = rangeHeader.replace("bytes=", "").split("-")
                start = int(parts[0])
                end = int(parts[1]) if parts[1] else len(content) - 1
                body = content[start:end + 1]
                return web.Response(
                    status=206, body=body,
                    headers={
                        "Content-Range": f"bytes {start}-{end}/{len(content)}",
                        "Content-Length": str(len(body)),
                    },
                )
            return web.Response(body=content, headers={"Content-Length": str(len(content))})

        url = await server(captureHeaders)
        task, step = makeStep(url, tmpdir, fileSize=100, subworkerCount=2,
                              userAgent="GhostTest/1.0")
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        assert len(receivedHeaders) >= 2
        for hdrs in receivedHeaders:
            ua = hdrs.get("user-agent", hdrs.get("User-Agent", ""))
            assert "GhostTest/1.0" in ua, (
                f"User-Agent missing from request headers: {hdrs}"
            )

    async def test_speed_reported_for_every_chunk(self, server, tmpdir):
        content = makeFileContent(1000)
        url = await server(rangeHandler(content))
        task, step = makeStep(url, tmpdir, fileSize=1000, subworkerCount=2)
        task.setStatus(TaskStatus.RUNNING)

        speeds = await runStep(step)

        assert sum(speeds) == 1000


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
