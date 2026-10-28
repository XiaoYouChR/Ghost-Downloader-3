from __future__ import annotations

import asyncio
import gzip
from pathlib import Path
from struct import pack

import pytest
from aiohttp import web

from app.models.task import Task, TaskError, TaskStatus
from features.http_pack.task import HttpTask, HttpTaskStep
from tests.helpers import buildFileContent, buildRangeHandler, runStep


def buildStep(url: str, tmp_path: Path, *, fileSize: int, subworkerCount: int = 2,
             canUseRangeRequests: bool = True, userAgent: str = "") -> tuple[HttpTask, HttpTaskStep]:
    step = HttpTaskStep(stepIndex=0, url=url, fileSize=fileSize, subworkerCount=subworkerCount,
                        canUseRangeRequests=canUseRangeRequests, userAgent=userAgent, clientProfile="raw")
    task = HttpTask(name="test.bin", url=url, outputFolder=tmp_path, fileSize=fileSize, steps=[step])
    task.setStatus(TaskStatus.RUNNING)
    return task, step


def buildRangeRecorder(handler, ranges: list[str]):
    async def recording(request: web.Request) -> web.StreamResponse:
        ranges.append(request.headers.get("Range", ""))
        return await handler(request)
    return recording


def createRecord(path: Path, *subworkers: tuple[int, int, int]) -> None:
    Path(f"{path}.ghd").write_bytes(b"".join(pack("<QQQ", *subworker) for subworker in subworkers))


def buildFullBodyHandler(content: bytes):
    async def handler(request: web.Request) -> web.Response:
        return web.Response(body=content, headers={"Content-Length": str(len(content))})
    return handler


@pytest.mark.parametrize("subworkerCount", [1, 2, 10])
async def test_run_writes_served_file(startServer, tmp_path, subworkerCount):
    content = buildFileContent(1000)
    url = await startServer(buildRangeHandler(content))
    task, step = buildStep(url, tmp_path, fileSize=1000, subworkerCount=subworkerCount)

    await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content


async def test_run_fails_on_403(startServer, tmp_path):
    async def forbidden(request):
        return web.Response(status=403, text="Forbidden")

    url = await startServer(forbidden)
    task, step = buildStep(url, tmp_path, fileSize=100, subworkerCount=1)

    with pytest.raises(TaskError, match="403"):
        await runStep(step)


async def test_run_without_range_support_fetches_whole_file(startServer, tmp_path):
    content = buildFileContent(500)
    url = await startServer(buildFullBodyHandler(content))
    task, step = buildStep(url, tmp_path, fileSize=500, subworkerCount=1, canUseRangeRequests=False)

    await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content


async def test_run_finishes_when_server_sends_trailers(startServer, tmp_path):
    content = buildFileContent(500)

    async def chunkedWithTrailers(request: web.Request) -> web.Response:
        # aiohttp 不支持发送 trailer，只能直接写原始响应
        request.transport.write(
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nTrailer: x-checksum\r\nConnection: close\r\n\r\n"
            + f"{len(content):x}\r\n".encode() + content + b"\r\n0\r\nx-checksum: abc\r\n\r\n"
        )
        request.transport.close()
        return web.Response()

    url = await startServer(chunkedWithTrailers)
    task, step = buildStep(url, tmp_path, fileSize=500, subworkerCount=1, canUseRangeRequests=False)

    async with asyncio.timeout(3):
        await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content


async def test_run_falls_back_when_range_is_ignored(startServer, tmp_path):
    content = buildFileContent(500)
    url = await startServer(buildFullBodyHandler(content))
    task, step = buildStep(url, tmp_path, fileSize=500, subworkerCount=2)

    await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content


async def test_run_sends_user_agent_on_every_request(startServer, tmp_path):
    userAgents = []
    content = buildFileContent(100)
    handler = buildRangeHandler(content)

    async def recording(request):
        userAgents.append(request.headers.get("User-Agent"))
        return await handler(request)

    url = await startServer(recording)
    task, step = buildStep(url, tmp_path, fileSize=100, subworkerCount=2, userAgent="GhostTest/1.0")

    await runStep(step)

    assert userAgents.count("GhostTest/1.0") == len(userAgents) >= 2


async def test_run_reports_speed_adding_up_to_file_size(startServer, tmp_path):
    content = buildFileContent(1000)
    url = await startServer(buildRangeHandler(content))
    task, step = buildStep(url, tmp_path, fileSize=1000, subworkerCount=2)

    assert sum(await runStep(step)) == 1000


async def test_run_splits_slow_range_when_another_finishes(startServer, tmp_path):
    size = 2_000_000
    content = buildFileContent(size)
    ranges = []
    slowHalfStarted = asyncio.Event()

    async def slowSecondHalf(request: web.Request) -> web.StreamResponse:
        ranges.append(request.headers.get("Range", ""))
        if "Range" not in request.headers:
            # 回环上 1 MB 只需几毫秒，比新连接还快；真实网络中慢分片早已开始收数据
            response = web.StreamResponse(status=200, headers={"Content-Length": str(size)})
            await response.prepare(request)
            await slowHalfStarted.wait()
            await response.write(content)
            return response
        if request.headers["Range"] != f"bytes={size // 2}-{size - 1}":
            return await buildRangeHandler(content)(request)
        response = web.StreamResponse(status=206, headers={
            "Content-Range": f"bytes {size // 2}-{size - 1}/{size}", "Content-Length": str(size // 2)})
        await response.prepare(request)
        for offset in range(size // 2, size, 65536):
            await response.write(content[offset:min(offset + 65536, size)])
            await asyncio.sleep(0.05)
            slowHalfStarted.set()
        return response

    url = await startServer(slowSecondHalf)
    task, step = buildStep(url, tmp_path, fileSize=size, subworkerCount=2)

    await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content
    assert len(ranges) > 2


async def test_resume_requests_only_missing_bytes(startServer, tmp_path):
    content = buildFileContent(1000)
    ranges = []
    url = await startServer(buildRangeRecorder(buildRangeHandler(content), ranges))
    path = tmp_path / "test.bin"
    path.write_bytes(content[:700] + bytes(300))
    createRecord(path, (0, 500, 499), (500, 700, 999))
    task, step = buildStep(url, tmp_path, fileSize=1000, subworkerCount=2)

    await runStep(step)

    assert path.read_bytes() == content
    assert ranges == ["bytes=700-999"]
    assert not Path(f"{path}.ghd").exists()


@pytest.mark.parametrize("subworkerCount", [1, 4])
async def test_resume_with_new_thread_count_keeps_finished_bytes(startServer, tmp_path, subworkerCount):
    content = buildFileContent(1000)
    ranges = []
    url = await startServer(buildRangeRecorder(buildRangeHandler(content), ranges))
    path = tmp_path / "test.bin"
    path.write_bytes(content[:500] + bytes(500))
    createRecord(path, (0, 500, 499), (500, 500, 999))
    task, step = buildStep(url, tmp_path, fileSize=1000, subworkerCount=subworkerCount)

    await runStep(step)

    assert path.read_bytes() == content
    assert all(int(r.removeprefix("bytes=").split("-")[0]) >= 500 for r in ranges)


@pytest.mark.parametrize("record, fileSize", [
    (b"\xff" * 7, 1000),
    (pack("<QQQ", 0, 450, 494) + pack("<QQQ", 495, 495, 989), 990),
])
async def test_resume_from_unusable_record_starts_over(startServer, tmp_path, record, fileSize):
    content = buildFileContent(1000)
    url = await startServer(buildRangeHandler(content))
    path = tmp_path / "test.bin"
    path.write_bytes(bytes(1000))
    Path(f"{path}.ghd").write_bytes(record)
    task, step = buildStep(url, tmp_path, fileSize=fileSize, subworkerCount=2)

    await runStep(step)

    assert path.read_bytes() == content


async def test_run_corrects_size_from_browser(startServer, tmp_path):
    content = buildFileContent(1000)
    url = await startServer(buildRangeHandler(content))
    task, step = buildStep(url, tmp_path, fileSize=990, subworkerCount=4)

    await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content
    assert task.fileSize == 1000


async def test_run_segment_keeps_its_size(startServer, tmp_path):
    content = buildFileContent(1000)
    url = await startServer(buildRangeHandler(content))
    step = HttpTaskStep(stepIndex=0, url=url, fileSize=300, httpByteOffset=200,
                        subworkerCount=2, canUseRangeRequests=True, clientProfile="raw")
    task = Task(name="test.bin", url=url, packId="ffmpeg", outputFolder=tmp_path, fileSize=300, steps=[step])
    task.setStatus(TaskStatus.RUNNING)

    await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content[200:500]
    assert step.fileSize == 300


def buildSlowHandler(content: bytes, *, hasLength: bool = True):
    async def handler(request: web.Request) -> web.StreamResponse:
        rangeHeader = request.headers.get("Range")
        if rangeHeader is None:
            start, end, status, headers = 0, len(content) - 1, 200, {}
        else:
            first, _, last = rangeHeader.removeprefix("bytes=").partition("-")
            start, end, status = int(first), int(last) if last else len(content) - 1, 206
            headers = {"Content-Range": f"bytes {start}-{end}/{len(content)}"}
        response = web.StreamResponse(status=status, headers=headers)
        if hasLength:
            response.content_length = end - start + 1
        else:
            response.enable_chunked_encoding()
        await response.prepare(request)
        for offset in range(start, end + 1, 1024):
            await response.write(content[offset:min(offset + 1024, end + 1)])
            await asyncio.sleep(0.005)
        return response
    return handler


async def test_run_writes_original_bytes_when_range_counts_compressed_bytes(startServer, tmp_path):
    # https://github.com/XiaoYouChR/Ghost-Downloader-3/issues/888
    content = buildFileContent(20_000)
    compressed = gzip.compress(content)
    fullBody = buildSlowHandler(content, hasLength=False)
    compressedRange = buildRangeHandler(compressed)

    async def handler(request: web.Request) -> web.StreamResponse:
        if "Range" in request.headers:
            return await compressedRange(request)
        return await fullBody(request)

    url = await startServer(handler)
    task, step = buildStep(url, tmp_path, fileSize=len(compressed), subworkerCount=4)

    await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content


async def test_run_writes_original_bytes_when_range_total_disagrees(startServer, tmp_path):
    content = buildFileContent(20_000)
    compressed = gzip.compress(content)
    fullBody = buildSlowHandler(content)
    compressedRange = buildRangeHandler(compressed)

    async def handler(request: web.Request) -> web.StreamResponse:
        if "Range" in request.headers:
            return await compressedRange(request)
        return await fullBody(request)

    url = await startServer(handler)
    task, step = buildStep(url, tmp_path, fileSize=len(content), subworkerCount=4)

    await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content


async def test_run_sends_one_request_per_subworker(startServer, tmp_path):
    content = buildFileContent(1000)
    ranges = []
    url = await startServer(buildRangeRecorder(buildRangeHandler(content), ranges))
    task, step = buildStep(url, tmp_path, fileSize=1000, subworkerCount=4)

    await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content
    assert len(ranges) == 4


async def test_run_finishes_without_waiting_when_server_rejects_extra_requests(startServer, tmp_path):
    # EdgeOne 限流时返回 567
    content = buildFileContent(40_000)
    slow = buildSlowHandler(content)
    requestCount = 0

    async def rateLimited(request: web.Request) -> web.StreamResponse:
        nonlocal requestCount
        requestCount += 1
        if requestCount in {3, 4}:
            return web.Response(status=567, text="<html>blocked</html>")
        return await slow(request)

    url = await startServer(rateLimited)
    task, step = buildStep(url, tmp_path, fileSize=len(content), subworkerCount=4)

    async with asyncio.timeout(4):
        await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content


async def test_run_retries_first_request_after_server_error(startServer, tmp_path):
    content = buildFileContent(1000)
    handler = buildRangeHandler(content)
    requestCount = 0

    async def failingOnce(request: web.Request) -> web.StreamResponse:
        nonlocal requestCount
        requestCount += 1
        if requestCount == 1:
            return web.Response(status=503, text="busy")
        return await handler(request)

    url = await startServer(failingOnce)
    task, step = buildStep(url, tmp_path, fileSize=1000, subworkerCount=2)

    await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content


async def test_run_writes_file_when_content_range_has_non_ascii_digits(startServer, tmp_path):
    content = buildFileContent(1000)
    fullBody = buildFullBodyHandler(content)

    async def handler(request: web.Request) -> web.StreamResponse:
        if "Range" not in request.headers:
            return await fullBody(request)
        first, _, last = request.headers["Range"].removeprefix("bytes=").partition("-")
        body = content[int(first):int(last) + 1]
        # aiohttp 无法发送非 ASCII 响应头
        request.transport.write(
            f"HTTP/1.1 206 Partial Content\r\nContent-Range: bytes {first}-{last}/1".encode()
            + b"\xb2\r\n" + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body
        )
        request.transport.close()
        return web.Response()

    url = await startServer(handler)
    task, step = buildStep(url, tmp_path, fileSize=1000, subworkerCount=2)

    async with asyncio.timeout(4):
        await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content


async def test_run_restarts_single_stream_when_lengthless_response_breaks(startServer, tmp_path):
    content = buildFileContent(20_000)
    compressed = gzip.compress(content)
    compressedRange = buildRangeHandler(compressed)
    fullGets = 0

    async def breaksOnce(request: web.Request) -> web.StreamResponse:
        nonlocal fullGets
        if "Range" in request.headers:
            return await compressedRange(request)
        fullGets += 1
        response = web.StreamResponse()
        response.enable_chunked_encoding()
        await response.prepare(request)
        await response.write(content[:5000])
        if fullGets == 1:
            request.transport.close()
            return response
        await response.write(content[5000:])
        return response

    url = await startServer(breaksOnce)
    task, step = buildStep(url, tmp_path, fileSize=len(compressed), subworkerCount=4)

    await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content


async def test_run_stops_speed_up_when_server_rejects_new_connections(startServer, tmp_path):
    # 自动加速约每 10 秒判定一次
    content = buildFileContent(24 * 1024 * 1024)
    requestCount = rejectedCount = 0

    async def steadyThenRejecting(request: web.Request) -> web.StreamResponse:
        nonlocal requestCount, rejectedCount
        requestCount += 1
        if requestCount > 2:
            rejectedCount += 1
            return web.Response(status=567, text="<html>blocked</html>")
        first, _, last = request.headers.get("Range", "bytes=0-").removeprefix("bytes=").partition("-")
        start, end = int(first), int(last) if last else len(content) - 1
        headers = {"Content-Range": f"bytes {start}-{end}/{len(content)}"} if "Range" in request.headers else {}
        response = web.StreamResponse(status=206 if headers else 200, headers=headers)
        response.content_length = end - start + 1
        await response.prepare(request)
        for offset in range(start, end + 1, 32768):
            await response.write(content[offset:min(offset + 32768, end + 1)])
            await asyncio.sleep(0.05)
        return response

    url = await startServer(steadyThenRejecting)
    task, step = buildStep(url, tmp_path, fileSize=len(content), subworkerCount=2)

    await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content
    assert rejectedCount <= 4


async def test_run_finishes_when_rejection_arrives_after_left_subworker_ends(startServer, tmp_path):
    content = buildFileContent(20_000)
    fullBody = buildFullBodyHandler(content)

    async def slowRejection(request: web.Request) -> web.StreamResponse:
        if "Range" not in request.headers:
            return await fullBody(request)
        await asyncio.sleep(0.3)
        return web.Response(status=567, text="<html>blocked</html>")

    url = await startServer(slowRejection)
    task, step = buildStep(url, tmp_path, fileSize=len(content), subworkerCount=2)

    async with asyncio.timeout(3):
        await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content
