import asyncio
import os
import time

import pytest

from app.bootstrap_list import BootstrapList


def parseLines(data: bytes) -> list[str]:
    lines = data.decode().split()
    if not lines:
        raise ValueError("empty list")
    return lines


def makeList(tmp_path, sources: list[str], bodies: dict[str, bytes], fetched: list[str] | None = None):
    snapshot = tmp_path / "snapshot.txt"
    snapshot.write_bytes(b"udp://snapshot:1\n")

    async def fetch(url: str) -> bytes:
        if fetched is not None:
            fetched.append(url)
        await asyncio.sleep(0)
        if url not in bodies:
            raise OSError("unreachable")
        return bodies[url]

    return BootstrapList(tmp_path / "cache", snapshot, lambda: sources, parseLines, fetch)


def test_snapshot_is_used_until_anything_is_cached(tmp_path):
    bootstrapList = makeList(tmp_path, ["https://a"], {})

    assert bootstrapList.paths() == [tmp_path / "snapshot.txt"]


async def test_refresh_caches_every_source_in_order(tmp_path):
    bootstrapList = makeList(tmp_path, ["https://a", "https://b"], {
        "https://a": b"udp://a:1\nudp://a:2\n",
        "https://b": b"udp://b:1\n",
    })

    await bootstrapList.refresh()

    paths = bootstrapList.paths()
    assert [p.read_bytes() for p in paths] == [b"udp://a:1\nudp://a:2\n", b"udp://b:1\n"]
    statuses = bootstrapList.statuses()
    assert [(s.url, s.count, s.error) for s in statuses] == [("https://a", 2, ""), ("https://b", 1, "")]
    assert all(s.updatedAt is not None for s in statuses)


async def test_failed_source_keeps_its_cache_and_reports_why(tmp_path):
    bodies = {"https://a": b"udp://a:1\n", "https://b": b"udp://b:1\n"}
    bootstrapList = makeList(tmp_path, ["https://a", "https://b"], bodies)
    await bootstrapList.refresh()

    del bodies["https://a"]
    await bootstrapList.refresh()

    assert bootstrapList.paths()[0].read_bytes() == b"udp://a:1\n"
    status = bootstrapList.statuses()[0]
    assert status.count == 1
    assert "unreachable" in status.error


async def test_invalid_content_never_replaces_the_cache(tmp_path):
    bodies = {"https://a": b"udp://a:1\n"}
    bootstrapList = makeList(tmp_path, ["https://a"], bodies)
    await bootstrapList.refresh()

    bodies["https://a"] = b"   "
    await bootstrapList.refresh()

    assert bootstrapList.paths()[0].read_bytes() == b"udp://a:1\n"
    assert "empty list" in bootstrapList.statuses()[0].error


async def test_concurrent_refreshes_fetch_once(tmp_path):
    fetched: list[str] = []
    bootstrapList = makeList(tmp_path, ["https://a"], {"https://a": b"udp://a:1\n"}, fetched)

    await asyncio.gather(bootstrapList.refresh(), bootstrapList.refresh())

    assert fetched == ["https://a"]
    assert not bootstrapList.isRefreshing


async def test_list_is_stale_only_when_a_source_is_missing_or_old(tmp_path):
    bodies = {"https://a": b"udp://a:1\n"}
    assert makeList(tmp_path, ["https://a"], bodies).isStale()

    await makeList(tmp_path, ["https://a"], bodies).refresh()
    assert not makeList(tmp_path, ["https://a"], bodies).isStale()

    cached = makeList(tmp_path, ["https://a"], bodies).paths()[0]
    old = time.time() - 2 * 86400
    os.utime(cached, (old, old))
    assert makeList(tmp_path, ["https://a"], bodies).isStale()


async def test_failed_refresh_is_not_retried_until_the_next_day(tmp_path):
    bootstrapList = makeList(tmp_path, ["https://a"], {})

    await bootstrapList.refresh()

    assert not bootstrapList.isStale()


async def test_entries_shared_by_subscriptions_are_counted_once(tmp_path):
    bootstrapList = makeList(tmp_path, ["https://a", "https://b"], {
        "https://a": b"udp://a:1\nudp://shared:1\nudp://shared:1\n",
        "https://b": b"udp://b:1\nudp://shared:1\n",
    })

    await bootstrapList.refresh()

    assert [s.count for s in bootstrapList.statuses()] == [2, 2]
    assert bootstrapList.entryCount() == 3
