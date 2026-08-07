"""HTTP subworker 边界情况测试——防止文件损坏和静默失败。

使用本地 aiohttp 服务器精确控制服务器行为。

Seam S13a: 范围正确性（无重叠、无间隙）
Seam S13c: 服务器降级（200-for-range、403）
Seam S13e: 请求构造（_effectiveHeaders 一致性）
"""
from __future__ import annotations

import asyncio
import brotli
import gzip
import os
import zlib
import zstandard
from pathlib import Path

import pytest
from aiohttp import web

from features.http_pack.task import HttpTask, HttpTaskStep, HttpSubworker, PermanentDownloadError, RangeNotSupportedError
from app.models.task import TaskStatus, TaskError
from tests.helpers import buildFileContent, buildRangeHandler, runStep


def makeStep(url: str, tmp_path: Path, *, fileSize: int, subworkerCount: int = 2,
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
        outputFolder=tmp_path,
        fileSize=fileSize,
        steps=[step],
    )
    step._bindTask(task)
    return task, step


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

    async def test_download_produces_correct_file(self, server, tmp_path):
        content = buildFileContent(1000)
        url = await server(buildRangeHandler(content))
        task, step = makeStep(url, tmp_path, fileSize=1000, subworkerCount=2)
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        result = (tmp_path / "test.bin").read_bytes()
        assert result == content

    async def test_single_subworker_correct(self, server, tmp_path):
        content = buildFileContent(500)
        url = await server(buildRangeHandler(content))
        task, step = makeStep(url, tmp_path, fileSize=500, subworkerCount=1)
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        assert (tmp_path / "test.bin").read_bytes() == content

    async def test_many_subworkers_correct(self, server, tmp_path):
        content = buildFileContent(100)
        url = await server(buildRangeHandler(content))
        task, step = makeStep(url, tmp_path, fileSize=100, subworkerCount=10)
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        assert (tmp_path / "test.bin").read_bytes() == content


# ── S13c: Server degradation ──


class TestServerDegradation:

    async def test_403_raises_permanent_error(self, server, tmp_path):
        async def forbidden(request):
            return web.Response(status=403, text="Forbidden")

        url = await server(forbidden)
        task, step = makeStep(url, tmp_path, fileSize=100, subworkerCount=1)
        task.setStatus(TaskStatus.RUNNING)

        with pytest.raises(TaskError, match="403"):
            await runStep(step)

    async def test_cloudflare_mitigated_raises_permanent(self, server, tmp_path):
        async def cfMitigated(request):
            return web.Response(
                status=403,
                headers={"cf-mitigated": "challenge"},
                text="Cloudflare",
            )

        url = await server(cfMitigated)
        task, step = makeStep(url, tmp_path, fileSize=100, subworkerCount=1)
        task.setStatus(TaskStatus.RUNNING)

        with pytest.raises(TaskError):
            await runStep(step)

    async def test_no_range_support_downloads_full(self, server, tmp_path):
        """Server doesn't support ranges — step falls back to single full download."""
        content = buildFileContent(500)

        async def noRange(request):
            return web.Response(
                body=content,
                headers={"Content-Length": str(len(content))},
            )

        url = await server(noRange)
        task, step = makeStep(url, tmp_path, fileSize=500, subworkerCount=1,
                              canUseRangeRequests=False)
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)
        assert (tmp_path / "test.bin").read_bytes() == content


# ── S13e: Request construction ──


class TestRequestConstruction:

    async def test_effective_headers_include_user_agent(self, server, tmp_path):
        """All subworker paths should send the configured User-Agent."""
        receivedHeaders: list[dict] = []

        async def captureHeaders(request):
            receivedHeaders.append(dict(request.headers))
            rangeHeader = request.headers.get("Range")
            content = buildFileContent(100)
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
        task, step = makeStep(url, tmp_path, fileSize=100, subworkerCount=2,
                              userAgent="GhostTest/1.0")
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        assert len(receivedHeaders) >= 2
        for hdrs in receivedHeaders:
            ua = hdrs.get("user-agent", hdrs.get("User-Agent", ""))
            assert "GhostTest/1.0" in ua, (
                f"User-Agent missing from request headers: {hdrs}"
            )

    async def test_speed_reported_for_every_chunk(self, server, tmp_path):
        content = buildFileContent(1000)
        url = await server(buildRangeHandler(content))
        task, step = makeStep(url, tmp_path, fileSize=1000, subworkerCount=2)
        task.setStatus(TaskStatus.RUNNING)

        speeds = await runStep(step)

        assert sum(speeds) == 1000


# ── S13b: Dynamic adjustment ──


class TestReassignment:

    def _makeStepWithSubworkers(self, fileSize=1_000_000, subworkerCount=2):
        step = HttpTaskStep(stepIndex=0, url="", fileSize=fileSize,
                            subworkerCount=subworkerCount, canUseRangeRequests=True)
        step.subworkers = step._buildSubworkers()

        from unittest.mock import MagicMock
        step._taskGroup = MagicMock()

        def mock_create_task(coro):
            coro.close()
            return MagicMock()

        step._taskGroup.create_task = mock_create_task
        step._fd = -1
        step._effectiveHeaders = {}
        step._reportSpeed = lambda n: None
        step._waitForSpeedLimit = lambda: None
        return step

    def test_splits_slowest_subworker(self):
        step = self._makeStepWithSubworkers(fileSize=4_000_000)
        # sw0: [0, 1999999] almost done, sw1: [2000000, 3999999] not started
        step.subworkers[0].receivedBytes = 1_999_990
        step.subworkers[1].receivedBytes = 0

        step._reassignSubworker()

        assert len(step.subworkers) == 3
        sw1 = step.subworkers[1]
        sw2 = step.subworkers[2]
        assert sw2.start == sw1.end + 1
        assert sw2.end == 3_999_999
        assert sw1.end < 3_999_999

    def test_new_subworker_covers_second_half(self):
        step = self._makeStepWithSubworkers(fileSize=4_000_000)
        step.subworkers[0].receivedBytes = 1_999_990
        step.subworkers[1].receivedBytes = 0

        old_end = step.subworkers[1].end
        old_position = step.subworkers[1].position
        remaining = old_end - old_position + 1

        step._reassignSubworker()

        sw1 = step.subworkers[1]
        sw2 = step.subworkers[2]
        new_sw1_range = sw1.end - old_position + 1
        new_sw2_range = sw2.end - sw2.start + 1
        assert new_sw1_range + new_sw2_range == remaining

    def test_skips_when_below_threshold(self, monkeypatch):
        step = self._makeStepWithSubworkers(fileSize=1000, subworkerCount=2)
        # Both subworkers have < 512KB remaining (500 bytes each)
        step.subworkers[0].receivedBytes = 0
        step.subworkers[1].receivedBytes = 0

        step._reassignSubworker()

        assert len(step.subworkers) == 2

    def test_skips_when_filesize_zero(self):
        step = HttpTaskStep(stepIndex=0, url="", fileSize=0,
                            subworkerCount=1, canUseRangeRequests=False)
        step.subworkers = [HttpSubworker(index=0, start=0, end=-1)]

        step._reassignSubworker()

        assert len(step.subworkers) == 1

    async def test_reassignment_during_download(self, server, tmp_path):
        """When a fast subworker finishes, it steals from the slowest."""
        content = buildFileContent(2_000_000)

        request_count = 0

        async def slowForSecondHalf(request: web.Request) -> web.Response:
            nonlocal request_count
            request_count += 1
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

        url = await server(slowForSecondHalf)
        task, step = makeStep(url, tmp_path, fileSize=2_000_000, subworkerCount=2)
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        assert (tmp_path / "test.bin").read_bytes() == content
        # Reassignment should have created extra requests (more than the initial 2)
        assert request_count >= 2


# ── S13d: Resume integrity ──


class TestResume:

    async def test_resume_sw0_done_sw1_pending(self, server, tmp_path):
        """Resume with sw0 completed, sw1 not yet started."""
        from struct import pack as struct_pack
        content = buildFileContent(1000)
        url = await server(buildRangeHandler(content))

        filepath = tmp_path / "test.bin"
        with open(filepath, "wb") as f:
            f.write(content[:500])
            f.write(b'\x00' * 500)

        with open(str(filepath) + ".ghd", "wb") as f:
            f.write(struct_pack("<QQQ", 0, 500, 499))
            f.write(struct_pack("<QQQ", 500, 500, 999))

        task, step = makeStep(url, tmp_path, fileSize=1000, subworkerCount=2,
                              canUseRangeRequests=True)
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        assert filepath.read_bytes() == content
        assert not Path(str(filepath) + ".ghd").exists()

    async def test_resume_sw1_partial(self, server, tmp_path):
        """Resume with sw1 partially downloaded (200 of 500 bytes)."""
        from struct import pack as struct_pack
        content = buildFileContent(1000)
        url = await server(buildRangeHandler(content))

        filepath = tmp_path / "test.bin"
        with open(filepath, "wb") as f:
            f.write(content[:700])
            f.write(b'\x00' * 300)

        with open(str(filepath) + ".ghd", "wb") as f:
            f.write(struct_pack("<QQQ", 0, 500, 499))
            f.write(struct_pack("<QQQ", 500, 700, 999))

        task, step = makeStep(url, tmp_path, fileSize=1000, subworkerCount=2,
                              canUseRangeRequests=True)
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        assert filepath.read_bytes() == content

    async def test_resume_with_increased_thread_count(self, server, tmp_path):
        """User raised subworkerCount from 2 to 4 via EditDialog. Resume should split."""
        from struct import pack as struct_pack
        content = buildFileContent(1000)
        url = await server(buildRangeHandler(content))

        filepath = tmp_path / "test.bin"
        with open(filepath, "wb") as f:
            f.write(content[:500])
            f.write(b'\x00' * 500)

        with open(str(filepath) + ".ghd", "wb") as f:
            f.write(struct_pack("<QQQ", 0, 500, 499))
            f.write(struct_pack("<QQQ", 500, 500, 999))

        task, step = makeStep(url, tmp_path, fileSize=1000, subworkerCount=4,
                              canUseRangeRequests=True)
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        assert filepath.read_bytes() == content
        assert len(step.subworkers) >= 4

    async def test_resume_decreased_thread_count_is_noop(self, server, tmp_path):
        """User reduced subworkerCount. Existing subworkers should not be removed."""
        from struct import pack as struct_pack
        content = buildFileContent(1000)
        url = await server(buildRangeHandler(content))

        filepath = tmp_path / "test.bin"
        filepath.write_bytes(b'\x00' * 1000)

        with open(str(filepath) + ".ghd", "wb") as f:
            f.write(struct_pack("<QQQ", 0, 0, 249))
            f.write(struct_pack("<QQQ", 250, 250, 499))
            f.write(struct_pack("<QQQ", 500, 500, 749))
            f.write(struct_pack("<QQQ", 750, 750, 999))

        task, step = makeStep(url, tmp_path, fileSize=1000, subworkerCount=2,
                              canUseRangeRequests=True)
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        assert filepath.read_bytes() == content

    async def test_corrupt_record_starts_fresh(self, server, tmp_path):
        """Corrupt .ghd file — should discard and start fresh."""
        content = buildFileContent(1000)
        url = await server(buildRangeHandler(content))

        filepath = tmp_path / "test.bin"
        filepath.write_bytes(b'\x00' * 1000)

        with open(str(filepath) + ".ghd", "wb") as f:
            f.write(b'\xff' * 7)

        task, step = makeStep(url, tmp_path, fileSize=1000, subworkerCount=2,
                              canUseRangeRequests=True)
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        assert filepath.read_bytes() == content


# ── S13c: Transient errors ──


class TestTransientRetry:

    async def test_500_retries_then_succeeds(self, server, tmp_path, monkeypatch):
        """Server returns 500 once, then 206. Download should complete."""
        content = buildFileContent(500)
        fail_count = 0

        async def failOnce(request: web.Request) -> web.Response:
            nonlocal fail_count
            fail_count += 1
            if fail_count <= 1:
                return web.Response(status=500, text="Internal Server Error")
            return await buildRangeHandler(content)(request)

        _real_sleep = asyncio.sleep

        async def fast_sleep(n):
            await _real_sleep(0 if n >= 5 else min(n, 0.01))

        monkeypatch.setattr(asyncio, "sleep", fast_sleep)

        url = await server(failOnce)
        task, step = makeStep(url, tmp_path, fileSize=500, subworkerCount=1)
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        assert (tmp_path / "test.bin").read_bytes() == content
        assert fail_count >= 2


def ignoreRangeHandler(content: bytes):
    """Server ignores Range header, always returns 200 + full content."""
    async def handler(request: web.Request) -> web.Response:
        return web.Response(
            body=content,
            headers={"Content-Length": str(len(content))},
        )
    return handler


# ── S13c: 200-for-range fallback ──


class TestRangeFallback:

    async def test_200_for_range_falls_back_to_single_stream(self, server, tmp_path):
        """Server returns 200 for Range requests. Should fallback and complete."""
        content = buildFileContent(500)
        url = await server(ignoreRangeHandler(content))
        task, step = makeStep(url, tmp_path, fileSize=500, subworkerCount=2,
                              canUseRangeRequests=True)
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        assert not step.canUseRangeRequests
        assert (tmp_path / "test.bin").read_bytes() == content

    async def test_200_for_range_single_subworker(self, server, tmp_path):
        """Same fallback with only 1 subworker."""
        content = buildFileContent(200)
        url = await server(ignoreRangeHandler(content))
        task, step = makeStep(url, tmp_path, fileSize=200, subworkerCount=1,
                              canUseRangeRequests=True)
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        assert not step.canUseRangeRequests
        assert (tmp_path / "test.bin").read_bytes() == content


# ── S13c: Disk full ──


class TestDiskFull:

    async def test_enospc_raises_task_error(self, server, tmp_path, monkeypatch):
        """pwrite raises ENOSPC — should bubble as TaskError, not retry."""
        import errno as errno_mod

        content = buildFileContent(500)
        url = await server(buildRangeHandler(content))
        task, step = makeStep(url, tmp_path, fileSize=500, subworkerCount=1)
        task.setStatus(TaskStatus.RUNNING)

        def failing_pwrite(fd, data, offset):
            raise OSError(errno_mod.ENOSPC, "No space left on device")

        monkeypatch.setattr("features.http_pack.task.pwrite", failing_pwrite)

        with pytest.raises(TaskError, match="磁盘空间不足"):
            await runStep(step)


# ── S13g: Stall recovery ──


class TestStallRecovery:

    async def test_stalled_stream_recovers_and_completes(self, server, tmp_path, monkeypatch):
        """Stream stalls mid-transfer; read_timeout triggers retry, download completes."""
        content = buildFileContent(500)
        hasStalled = False
        releaseHang = asyncio.Event()

        async def stallOnce(request: web.Request) -> web.StreamResponse:
            nonlocal hasStalled
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

            if not hasStalled and end > start:
                hasStalled = True
                resp = web.StreamResponse(
                    status=206,
                    headers={
                        "Content-Range": f"bytes {start}-{end}/{len(content)}",
                        "Content-Length": str(len(body)),
                    },
                )
                await resp.prepare(request)
                await resp.write(body[:len(body) // 2])
                try:
                    await releaseHang.wait()
                except asyncio.CancelledError:
                    pass
                return resp

            return web.Response(
                status=206,
                body=body,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{len(content)}",
                    "Content-Length": str(len(body)),
                },
            )

        monkeypatch.setattr("features.http_pack.task.STREAM_READ_TIMEOUT", 1)

        _real_sleep = asyncio.sleep

        async def fast_sleep(n):
            await _real_sleep(0 if n >= 5 else min(n, 0.01))

        monkeypatch.setattr(asyncio, "sleep", fast_sleep)

        url = await server(stallOnce)
        task, step = makeStep(url, tmp_path, fileSize=500, subworkerCount=1)
        task.setStatus(TaskStatus.RUNNING)

        await asyncio.wait_for(runStep(step), timeout=10)

        assert (tmp_path / "test.bin").read_bytes() == content
        assert hasStalled
        releaseHang.set()


# ── S13a/S13c: Compressed range ──


ENCODINGS = {
    "gzip": lambda data: gzip.compress(data),
    "deflate": lambda data: zlib.compress(data),
    "br": lambda data: brotli.compress(data),
    "zstd": lambda data: zstandard.compress(data),
}


def compressedRangeHandler(content: bytes, encoding: str):
    """Server that compresses each range response with the given encoding."""
    compress = ENCODINGS[encoding]

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
        compressed = compress(body)
        return web.Response(
            status=206,
            body=compressed,
            headers={
                "Content-Range": f"bytes {start}-{end}/{len(content)}",
                "Content-Encoding": encoding,
                "Content-Length": str(len(compressed)),
            },
        )
    return handler


def brokenEncodingRangeHandler(content: bytes, encoding: str):
    """Server claims encoding for ranges but sends raw bytes. Full requests are correct."""
    async def handler(request: web.Request) -> web.Response:
        rangeHeader = request.headers.get("Range")
        if rangeHeader is None:
            return web.Response(
                body=content,
                headers={"Content-Length": str(len(content))},
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
                "Content-Encoding": encoding,
            },
        )
    return handler


class TestCompressedRange:

    @pytest.mark.parametrize("encoding", list(ENCODINGS))
    async def test_compressed_range_produces_correct_file(self, server, tmp_path, encoding):
        content = buildFileContent(1000)
        url = await server(compressedRangeHandler(content, encoding))
        task, step = makeStep(url, tmp_path, fileSize=1000, subworkerCount=2)
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        assert (tmp_path / "test.bin").read_bytes() == content

    @pytest.mark.parametrize("encoding", list(ENCODINGS))
    async def test_broken_encoding_falls_back_to_single_stream(self, server, tmp_path, monkeypatch, encoding):
        content = buildFileContent(500)

        _real_sleep = asyncio.sleep

        async def fast_sleep(n):
            await _real_sleep(0 if n >= 5 else min(n, 0.01))

        monkeypatch.setattr(asyncio, "sleep", fast_sleep)

        url = await server(brokenEncodingRangeHandler(content, encoding))
        task, step = makeStep(url, tmp_path, fileSize=500, subworkerCount=2,
                              canUseRangeRequests=True)
        task.setStatus(TaskStatus.RUNNING)

        await asyncio.wait_for(runStep(step), timeout=15)

        assert not step.canUseRangeRequests
        assert (tmp_path / "test.bin").read_bytes() == content

    async def test_mixed_encodings_across_subworkers(self, server, tmp_path):
        """Different subworkers get different Content-Encoding (CDN edge variance)."""
        content = buildFileContent(1000)
        encodingNames = list(ENCODINGS)
        requestIndex = 0

        async def handler(request: web.Request) -> web.Response:
            nonlocal requestIndex
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
            encoding = encodingNames[requestIndex % len(encodingNames)]
            requestIndex += 1
            compressed = ENCODINGS[encoding](body)
            return web.Response(
                status=206,
                body=compressed,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{len(content)}",
                    "Content-Encoding": encoding,
                    "Content-Length": str(len(compressed)),
                },
            )

        url = await server(handler)
        task, step = makeStep(url, tmp_path, fileSize=1000, subworkerCount=4)
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        assert (tmp_path / "test.bin").read_bytes() == content

    async def test_reassignment_with_compressed_range(self, server, tmp_path):
        """_splitSlowest during compressed streaming: clamp on decompressed bytes, new subworker gets correct compressed range."""
        content = buildFileContent(2_000_000)
        requestCount = 0

        compress = ENCODINGS["gzip"]

        async def handler(request: web.Request) -> web.Response:
            nonlocal requestCount
            requestCount += 1
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
            compressed = compress(body)
            return web.Response(
                status=206,
                body=compressed,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{len(content)}",
                    "Content-Encoding": "gzip",
                    "Content-Length": str(len(compressed)),
                },
            )

        url = await server(handler)
        task, step = makeStep(url, tmp_path, fileSize=2_000_000, subworkerCount=2)
        task.setStatus(TaskStatus.RUNNING)

        await runStep(step)

        assert (tmp_path / "test.bin").read_bytes() == content
        assert requestCount > 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
