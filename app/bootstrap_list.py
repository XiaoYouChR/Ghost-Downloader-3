from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

MAX_AGE = 86400


@dataclass(frozen=True)
class SubscriptionStatus:
    url: str
    count: int | None
    updatedAt: float | None
    error: str = ""


async def fetchBytes(url: str) -> bytes:
    from app.client import buildClient

    client = buildClient(readTimeout=30)
    try:
        response = await client.get(url)
        response.raise_for_status()
        return await response.bytes()
    finally:
        client.close()


class BootstrapList:
    def __init__(
        self,
        folder: Path,
        snapshot: Path,
        sources: Callable[[], list[str]],
        count: Callable[[bytes], int],
        fetch: Callable[[str], Awaitable[bytes]] = fetchBytes,
    ):
        self._folder = folder
        self._snapshot = snapshot
        self._sources = sources
        self._count = count
        self._fetch = fetch
        self._errors: dict[str, str] = {}
        self._refreshing: asyncio.Task | None = None
        self._lastRefreshAt = 0.0

    @property
    def isRefreshing(self) -> bool:
        return self._refreshing is not None

    def paths(self) -> list[Path]:
        cached = [path for url in self._sources() if (path := self._cachePath(url)).is_file()]
        return cached or [self._snapshot]

    def isStale(self) -> bool:
        now = time.time()
        if now - self._lastRefreshAt < MAX_AGE:
            return False
        return any(
            not path.is_file() or now - path.stat().st_mtime > MAX_AGE
            for path in map(self._cachePath, self._sources())
        )

    def statuses(self) -> list[SubscriptionStatus]:
        statuses = []
        for url in self._sources():
            path = self._cachePath(url)
            isCached = path.is_file()
            statuses.append(SubscriptionStatus(
                url,
                self._count(path.read_bytes()) if isCached else None,
                path.stat().st_mtime if isCached else None,
                self._errors.get(url, ""),
            ))
        return statuses

    async def refresh(self) -> None:
        if self._refreshing is None:
            self._refreshing = asyncio.ensure_future(self._fetchAll())
        await asyncio.shield(self._refreshing)

    async def _fetchAll(self) -> None:
        try:
            self._lastRefreshAt = time.time()
            await asyncio.gather(*map(self._fetchOne, self._sources()))
        finally:
            self._refreshing = None

    async def _fetchOne(self, url: str) -> None:
        try:
            data = await self._fetch(url)
            self._count(data)
            path = self._cachePath(url)
            path.parent.mkdir(parents=True, exist_ok=True)
            partPath = path.with_suffix(".part")
            partPath.write_bytes(data)
            partPath.replace(path)
            self._errors.pop(url, None)
        except Exception as e:
            self._errors[url] = str(e) or type(e).__name__

    def _cachePath(self, url: str) -> Path:
        return self._folder / hashlib.sha1(url.encode()).hexdigest()[:16]
