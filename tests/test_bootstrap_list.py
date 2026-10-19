from __future__ import annotations

import asyncio
import os
import time

import pytest
from aiohttp import web

from app.bootstrap_list import BootstrapList


def parseLines(data: bytes) -> list[str]:
    lines = data.decode().split()
    if not lines:
        raise ValueError("empty list")
    return lines


class Source:
    def __init__(self, body: bytes | None):
        self.body = body
        self.hits = 0
        self.url = ""

    async def onRequest(self, request: web.Request) -> web.Response:
        self.hits += 1
        await asyncio.sleep(0)
        if self.body is None:
            return web.Response(status=503)
        return web.Response(body=self.body)


@pytest.fixture
def startSource(config, startServer):
    async def start(body: bytes | None) -> Source:
        source = Source(body)
        source.url = await startServer(source.onRequest)
        return source
    return start


def buildList(tmp_path, *sources: Source) -> BootstrapList:
    snapshot = tmp_path / "snapshot.txt"
    snapshot.write_bytes(b"udp://snapshot:1\n")
    return BootstrapList(tmp_path / "cache", snapshot, lambda: [source.url for source in sources], parseLines)


async def test_load_snapshot_until_cached(tmp_path, startSource):
    bootstrapList = buildList(tmp_path, await startSource(None))

    assert bootstrapList.paths() == [tmp_path / "snapshot.txt"]


async def test_refresh_caches_every_source_in_order(tmp_path, startSource):
    a, b = await startSource(b"udp://a:1\nudp://a:2\n"), await startSource(b"udp://b:1\n")
    bootstrapList = buildList(tmp_path, a, b)

    await bootstrapList.refresh()

    assert [path.read_bytes() for path in bootstrapList.paths()] == [b"udp://a:1\nudp://a:2\n", b"udp://b:1\n"]
    statuses = bootstrapList.statuses()
    assert [(status.url, status.count, status.error) for status in statuses] == [(a.url, 2, ""), (b.url, 1, "")]
    assert all(status.updatedAt is not None for status in statuses)


async def test_refresh_failure_keeps_cache_and_shows_why(tmp_path, startSource):
    a, b = await startSource(b"udp://a:1\n"), await startSource(b"udp://b:1\n")
    bootstrapList = buildList(tmp_path, a, b)
    await bootstrapList.refresh()

    a.body = None
    await bootstrapList.refresh()

    assert bootstrapList.paths()[0].read_bytes() == b"udp://a:1\n"
    status = bootstrapList.statuses()[0]
    assert status.count == 1
    assert "503" in status.error


async def test_refresh_with_invalid_content_keeps_cache(tmp_path, startSource):
    a = await startSource(b"udp://a:1\n")
    bootstrapList = buildList(tmp_path, a)
    await bootstrapList.refresh()

    a.body = b"   "
    await bootstrapList.refresh()

    assert bootstrapList.paths()[0].read_bytes() == b"udp://a:1\n"
    assert "empty list" in bootstrapList.statuses()[0].error


async def test_refresh_twice_at_once_fetches_once(tmp_path, startSource):
    a = await startSource(b"udp://a:1\n")
    bootstrapList = buildList(tmp_path, a)

    await asyncio.gather(bootstrapList.refresh(), bootstrapList.refresh())

    assert a.hits == 1
    assert not bootstrapList.isRefreshing


async def test_refresh_needed_only_for_missing_or_old_sources(tmp_path, startSource):
    a = await startSource(b"udp://a:1\n")
    assert buildList(tmp_path, a).isStale()

    await buildList(tmp_path, a).refresh()
    assert not buildList(tmp_path, a).isStale()

    old = time.time() - 2 * 86400
    os.utime(buildList(tmp_path, a).paths()[0], (old, old))
    assert buildList(tmp_path, a).isStale()


async def test_refresh_after_failure_waits_until_next_day(tmp_path, startSource):
    bootstrapList = buildList(tmp_path, await startSource(None))

    await bootstrapList.refresh()

    assert not bootstrapList.isStale()


async def test_refresh_counts_shared_entries_once(tmp_path, startSource):
    a = await startSource(b"udp://a:1\nudp://shared:1\nudp://shared:1\n")
    b = await startSource(b"udp://b:1\nudp://shared:1\n")
    bootstrapList = buildList(tmp_path, a, b)

    await bootstrapList.refresh()

    assert [status.count for status in bootstrapList.statuses()] == [2, 2]
    assert bootstrapList.entryCount() == 3
