from __future__ import annotations

import asyncio
from contextlib import suppress
from hashlib import sha256
from pathlib import Path
from random import Random
from time import monotonic

import pytest
from aiohttp import web
from loguru import logger

from app.models.task import Task, TaskOptions, TaskStatus
from tests.helpers import buildRangeHandler, waitUntil

MIB = 1024 * 1024
RATE = 2 * MIB


@pytest.fixture(params=["desktop", "android"])
def enginePlatform(request):
    return request.param


@pytest.fixture
def engine(enginePlatform, startEngine):
    return startEngine(enginePlatform)


def buildServer(content, headers, ranges, *, isRedirected=False, shouldDisconnect=False, maxRange=0):
    sampleHandler = buildRangeHandler(content)

    async def serve(request):
        if any(request.headers.get(key) != value for key, value in headers.items()):
            return web.Response(status=403)
        if isRedirected and request.path == "/file":
            raise web.HTTPFound("/redirected/file")
        rangeHeader = request.headers.get("Range")
        start, end = (map(int, rangeHeader.removeprefix("bytes=").split("-"))
                      if rangeHeader else (0, len(content) - 1))
        if end - start + 1 <= 4096:
            return await sampleHandler(request)

        if rangeHeader and maxRange:
            end = min(end, start + maxRange - 1)
        ranges.append((start, end))
        response = web.StreamResponse(status=206 if rangeHeader else 200)
        response.content_length = end - start + 1
        if rangeHeader:
            response.headers["Content-Range"] = f"bytes {start}-{end}/{len(content)}"
        await response.prepare(request)
        started = monotonic()
        with suppress(ConnectionError):
            for offset in range(start, end + 1, 32768):
                last = min(offset + 32768, end + 1)
                await asyncio.sleep(max(0, started + (last - start) / RATE - monotonic()))
                await response.write(content[offset:last])
                if shouldDisconnect and last - start >= 65536:
                    request.transport.close()
                    break
        return response

    return serve


async def parse(engine, url, downloadFolder, headers=None):
    return await engine.featureService.parse(TaskOptions(url=url, outputFolder=downloadFolder,
                                                         headers=headers or {}, clientProfile="raw",
                                                         subworkerCount=1))


@pytest.mark.parametrize("shouldDisconnect", [False, True])
async def test_add_source_reuses_progress_and_finishes(engine, httpPack, startServer, downloadFolder, shouldDisconnect):
    content = Random(42).randbytes(10 * MIB)
    checksum = sha256(content).hexdigest()
    primaryHeaders = {"Cookie": "source=A", "Referer": "https://a.example/", "User-Agent": "Source-A"}
    mirrorHeaders = {"Cookie": "source=B", "Referer": "https://b.example/", "User-Agent": "Source-B"}
    primaryRanges, mirrorRanges = [], []
    primaryUrl = await startServer(buildServer(content, primaryHeaders, primaryRanges))
    mirrorUrl = await startServer(buildServer(content, mirrorHeaders, mirrorRanges,
                                             isRedirected=True, shouldDisconnect=shouldDisconnect))

    task = await parse(engine, primaryUrl, downloadFolder, primaryHeaders)
    incoming = await parse(engine, mirrorUrl, downloadFolder, mirrorHeaders)
    tasks = engine.taskService
    tasks.add(task)
    await waitUntil(lambda: task.currentSnapshot()[2] >= MIB)
    previousBytes = task.currentSnapshot()[2]
    added = []
    tasks.sourceAdded.connect(lambda target, source: added.append((target, source)))
    assert tasks.sourceTargets(incoming) == [task]
    tasks.addSource(task, incoming, checksum)
    await waitUntil(lambda: added == [(task, incoming)])

    primary, mirror = task.mirrorStep.sources
    assert primary.receivedBytes >= previousBytes
    assert tasks.tasks == [task]
    assert mirror.effectiveUrl.endswith("/redirected/file")
    await waitUntil(lambda: bool(mirrorRanges))
    await waitUntil(lambda: any(end < mirrorRanges[0][0] for _, end in primaryRanges))
    if shouldDisconnect:
        await waitUntil(lambda: mirror.isUnavailable)
        assert mirror.receivedBytes > 0
    else:
        await waitUntil(lambda: primary.speed > 0 and mirror.speed > 0 and primary.speed + mirror.speed >= 2.8 * MIB)
        before = primary.receivedBytes, mirror.receivedBytes
        await waitUntil(lambda: primary.receivedBytes > before[0] and mirror.receivedBytes > before[1])

    await waitUntil(lambda: task.status == TaskStatus.COMPLETED, timeout=12)
    assert task.checksums == {"sha256": checksum}
    assert sha256(Path(task.outputPath).read_bytes()).hexdigest() == checksum
    assert primary.receivedBytes + mirror.receivedBytes == len(content)
    assert list(downloadFolder.iterdir()) == [Path(task.outputPath)]


@pytest.mark.parametrize("isDifferent", [True, False])
async def test_add_source_rejects_mismatched_sample_or_range(engine, httpPack, startServer, downloadFolder, isDifferent):
    content = Random(42).randbytes(3 * MIB)
    different = bytearray(content)
    different[len(content) // 2] ^= 1
    valid = buildRangeHandler(bytes(different) if isDifferent else content)

    async def serve(request):
        response = await valid(request)
        if not isDifferent and request.headers.get("Range") != "bytes=1-1":
            response.headers["Content-Range"] = f"bytes 0-100/{len(content) + 1}"
        return response

    primaryRanges = []
    task = await parse(engine, await startServer(buildServer(content, {}, primaryRanges)), downloadFolder)
    incoming = await parse(engine, await startServer(serve), downloadFolder)
    tasks = engine.taskService
    tasks.add(task)
    await waitUntil(lambda: bool(primaryRanges))
    errors = []
    tasks.sourceAddFailed.connect(lambda target, source, error: errors.append(str(error)))
    tasks.addSource(task, incoming)
    await waitUntil(lambda: bool(errors))

    assert ("不一致" if isDifferent else "范围请求") in errors[0]
    assert len(task.mirrorStep.sources) == 1
    assert task.status == TaskStatus.RUNNING
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)
    assert Path(task.outputPath).read_bytes() == content


@pytest.mark.parametrize("isChecksumValid", [True, False])
async def test_add_source_to_paused_task_survives_restart(
    engine, enginePlatform, startEngine, httpPack, startServer, downloadFolder, isChecksumValid,
):
    content = Random(42).randbytes(5 * MIB)
    firstRanges, secondRanges = [], []
    primary = await startServer(buildServer(content, {}, firstRanges))
    mirror = await startServer(buildServer(content, {}, secondRanges))
    task = await parse(engine, primary, downloadFolder)
    incoming = await parse(engine, mirror, downloadFolder)
    engine.taskService.add(task)
    await waitUntil(lambda: task.currentSnapshot()[2] >= MIB)
    engine.taskService.pause(task)
    progress = task.currentSnapshot()[2]
    checksum = sha256(content).hexdigest() if isChecksumValid else "0" * 64
    engine.taskService.addSource(task, incoming, checksum)
    await waitUntil(lambda: len(task.mirrorStep.sources) == 2)
    assert task.status == TaskStatus.PAUSED
    engine.taskService.flush()

    restarted = startEngine(enginePlatform)
    restored = restarted.taskService.taskById(task.taskId)
    assert restored.status == TaskStatus.PAUSED
    assert restored.currentSnapshot()[2] >= progress
    assert restored.expectedSha256 == checksum
    assert [source.url for source in restored.mirrorStep.sources] == [primary, mirror]
    firstRanges.clear()
    restarted.taskService.start(restored)
    finalStatus = TaskStatus.COMPLETED if isChecksumValid else TaskStatus.FAILED
    await waitUntil(lambda: restored.status == finalStatus)
    assert secondRanges and all(start >= progress for start, _ in firstRanges + secondRanges)
    assert Path(restored.outputPath).read_bytes() == content
    assert restored.partPath.exists() != isChecksumValid
    if not isChecksumValid:
        assert "SHA256" in str(restored.lastError)


async def test_resume_after_immediate_pause_keeps_short_ranges(engine, httpPack, startServer, downloadFolder):
    content = Random(20).randbytes(7 * MIB)
    rangesA, rangesB = [], []
    primary = await startServer(buildServer(content, {}, rangesA, maxRange=MIB))
    mirror = await startServer(buildServer(content, {}, rangesB, maxRange=MIB))
    task = await parse(engine, primary, downloadFolder)
    incoming = await parse(engine, mirror, downloadFolder)
    tasks = engine.taskService
    tasks.add(task, autoStart=False)
    tasks.addSource(task, incoming, sha256(content).hexdigest())
    await waitUntil(lambda: len(task.mirrorStep.sources) == 2)
    tasks.start(task)
    await waitUntil(lambda: all(source.receivedBytes >= 65536 for source in task.mirrorStep.sources))

    for _ in range(3):
        before = sum(source.receivedBytes for source in task.mirrorStep.sources)
        tasks.pause(task)
        tasks.start(task)
        await waitUntil(lambda: task.status == TaskStatus.RUNNING
                        and sum(source.receivedBytes for source in task.mirrorStep.sources) >= before + 65536)

    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)
    assert Path(task.outputPath).read_bytes() == content
    assert rangesA and rangesB
    assert all(end - start < MIB for start, end in rangesA + rangesB)
    assert not task.partPath.exists()


async def test_add_source_pins_version_before_writing(engine, httpPack, startServer, downloadFolder):
    content = Random(23).randbytes(2 * MIB)
    original = buildRangeHandler(content)
    changed = buildRangeHandler(b"\x00" * len(content))
    conditions = []

    async def mirror(request):
        header = request.headers["Range"]
        start, end = map(int, header.removeprefix("bytes=").split("-"))
        if end - start + 1 <= 4096:
            response = await original(request)
            response.headers["ETag"] = '"original"'
            return response
        conditions.append(request.headers.get("If-Match"))
        response = await changed(request)
        response.headers["ETag"] = '"new-object"'
        return response

    task = await parse(engine, await startServer(original), downloadFolder)
    incoming = await parse(engine, await startServer(mirror), downloadFolder)
    tasks = engine.taskService
    tasks.add(task, autoStart=False)
    tasks.addSource(task, incoming)
    await waitUntil(lambda: len(task.mirrorStep.sources) == 2)
    tasks.start(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)

    assert conditions and all(tag == '"original"' for tag in conditions)
    assert task.mirrorStep.sources[1].receivedBytes == 0
    assert Path(task.outputPath).read_bytes() == content


async def test_run_retries_when_both_sources_temporarily_fail(engine, httpPack, startServer, downloadFolder):
    content = Random(26).randbytes(2 * MIB)
    events = []

    def buildBusyServer(name):
        serve = buildServer(content, {}, [])

        async def busy(request):
            start, end = map(int, request.headers["Range"].removeprefix("bytes=").split("-"))
            if end - start + 1 > 4096 and name not in events:
                events.append(name)
                return web.Response(status=503, headers={"Retry-After": "2"})
            return await serve(request)

        return busy

    task = await parse(engine, await startServer(buildBusyServer("A")), downloadFolder)
    incoming = await parse(engine, await startServer(buildBusyServer("B")), downloadFolder)
    tasks = engine.taskService
    tasks.add(task, autoStart=False)
    tasks.addSource(task, incoming)
    await waitUntil(lambda: len(task.mirrorStep.sources) == 2)
    tasks.start(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED, timeout=9)

    assert sorted(events) == ["A", "B"]
    assert Path(task.outputPath).read_bytes() == content


async def test_add_source_keeps_redirect_and_credentials_out_of_diagnostics(
    engine, httpPack, startServer, downloadFolder,
):
    credential = "test-source-credential"
    signedParameter = "test-redirect-signature"
    original = buildRangeHandler(b"x" * 50000)
    different = buildRangeHandler(b"y" * 50000)

    async def serve(request):
        if request.path == "/file":
            raise web.HTTPFound(f"/storage/file?signature={signedParameter}")
        return await (different if request.headers.get("Cookie") else original)(request)

    task = await parse(engine, await startServer(original), downloadFolder)
    url = await startServer(serve)
    invalid = await parse(engine, url, downloadFolder, {"Cookie": credential})
    valid = await parse(engine, url, downloadFolder)
    tasks = engine.taskService
    tasks.add(task, autoStart=False)
    errors, messages = [], []
    tasks.sourceAddFailed.connect(lambda _, __, error: errors.append(str(error)))
    sink = logger.add(lambda message: messages.append(str(message)), diagnose=True, backtrace=True)
    try:
        tasks.addSource(task, invalid)
        await waitUntil(lambda: bool(errors))
        tasks.addSource(task, valid)
        await waitUntil(lambda: len(task.mirrorStep.sources) == 2)
    finally:
        logger.remove(sink)

    assert all(credential not in line and signedParameter not in line for line in errors + messages)
    mirror = task.mirrorStep.sources[1]
    assert signedParameter in mirror.effectiveUrl
    saved = task.toDict()
    savedStep = saved["steps"][0]
    assert "primaryEffectiveUrl" not in savedStep and "effectiveUrl" not in savedStep["mirror"]
    savedStep["primaryEffectiveUrl"] = mirror.effectiveUrl
    savedStep["mirror"]["effectiveUrl"] = mirror.effectiveUrl
    restored = Task.fromDict(saved)
    assert signedParameter not in str(restored.toDict())


async def test_edit_source_configuration_revalidates_partial_file(engine, httpPack, startServer, downloadFolder):
    content = Random(28).randbytes(4 * MIB)
    original = buildServer(content, {}, [])
    different = buildRangeHandler(b"y" * len(content))

    async def serve(request):
        return await (different if request.headers.get("Cookie") == "version=other" else original)(request)

    task = await parse(engine, await startServer(serve), downloadFolder)
    incoming = await parse(engine, await startServer(original), downloadFolder)
    tasks = engine.taskService
    tasks.add(task, autoStart=False)
    tasks.addSource(task, incoming)
    await waitUntil(lambda: len(task.mirrorStep.sources) == 2)
    tasks.start(task)
    await waitUntil(lambda: all(source.receivedBytes >= 65536 for source in task.mirrorStep.sources))
    before = min(source.receivedBytes for source in task.mirrorStep.sources)
    tasks.edit(task, {"headers": {"Cookie": "version=other"}})
    await waitUntil(lambda: task.status == TaskStatus.FAILED)

    assert "不一致" in str(task.lastError)
    assert task.partPath.exists()
    with Path(task.outputPath).open("rb") as output:
        assert output.read(before) == content[:before]
