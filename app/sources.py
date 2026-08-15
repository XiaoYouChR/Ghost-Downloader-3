from __future__ import annotations

from asyncio.staggered import staggered_race
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from app.client import buildClient, fetchFile


@dataclass(frozen=True)
class Repo:
    name: str
    mirrors: dict[str, str] = field(default_factory=dict)

    def forSource(self, source: str) -> str:
        return self.mirrors.get(source, self.name)


@dataclass(frozen=True)
class SourceEndpoints:
    api: str
    download: str
    raw: str
    rawInfix: str


SOURCES = {
    "gitcode": SourceEndpoints(
        api="https://api.gitcode.com/api/v5/repos",
        download="https://gitcode.com",
        raw="https://cdn.jsdelivr.net/gh",
        rawInfix="@",
    ),
    "github": SourceEndpoints(
        api="https://api.github.com/repos",
        download="https://github.com",
        raw="https://raw.githubusercontent.com",
        rawInfix="/",
    ),
}

SOURCE_ORDER = ("github", "gitcode")
STAGGER_DELAY = 0.3


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    size: int
    downloadCount: int
    downloadUrl: str


@dataclass(frozen=True)
class Release:
    version: str
    publishedAt: str
    body: str
    pageUrl: str
    prerelease: bool
    assets: list[ReleaseAsset]

    @classmethod
    def fromResponse(cls, data: dict[str, Any]) -> Release:
        version = ""
        for key in ("tag_name", "name"):
            value = str(data.get(key) or "").strip()
            if value:
                version = value
                break

        assets = [
            ReleaseAsset(
                name=a.get("name", ""),
                size=a.get("size", 0),
                downloadCount=a.get("download_count", 0),
                downloadUrl=a.get("browser_download_url", ""),
            )
            for a in data.get("assets", [])
        ]

        return cls(
            version=version or "Unknown",
            publishedAt=data.get("published_at", "") or data.get("created_at", ""),
            body=data.get("body", "") or "",
            pageUrl=data.get("html_url", ""),
            prerelease=data.get("prerelease", False),
            assets=assets,
        )


async def fetchLatestRelease(repo: Repo) -> tuple[Release, str]:
    async def attempt(source):
        endpoints = SOURCES[source]
        url = f"{endpoints.api}/{repo.forSource(source)}/releases/latest"
        headers = {"accept": "application/vnd.github+json"} if source == "github" else {}
        client = buildClient(headers=headers, timeout=15)
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = await resp.json()
            return Release.fromResponse(data), source
        except Exception as e:
            logger.debug("从 {} 获取 {} release 失败: {}", source, repo.name, repr(e))
            raise
        finally:
            client.close()

    result, index, _ = await staggered_race(
        [lambda s=s: attempt(s) for s in SOURCE_ORDER], STAGGER_DELAY)
    if index is not None:
        return result
    raise RuntimeError(f"无法获取 {repo.name} 的最新 release")


async def fetchLatestTag(repo: Repo) -> tuple[str, str]:
    release, source = await fetchLatestRelease(repo)
    return release.version, source


async def fetchJson(repo: Repo, branch: str, path: str) -> tuple[dict, str]:
    async def attempt(source):
        endpoints = SOURCES[source]
        url = f"{endpoints.raw}/{repo.forSource(source)}{endpoints.rawInfix}{branch}/{path}"
        client = buildClient(timeout=15)
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            result = await resp.json()
            return result, source
        except Exception as e:
            logger.debug("从 {} 获取 {}/{} 失败: {}", source, repo.name, path, repr(e))
            raise
        finally:
            client.close()

    result, index, _ = await staggered_race(
        [lambda s=s: attempt(s) for s in SOURCE_ORDER], STAGGER_DELAY)
    if index is not None:
        return result
    raise RuntimeError(f"无法获取 {repo.name}/{branch}/{path}")


async def fetchRawFile(
    repo: Repo, branch: str, path: str, outputPath: Path,
    onProgress: Callable[[float], None] | None = None,
) -> str:
    async def probe(source):
        endpoints = SOURCES[source]
        url = f"{endpoints.raw}/{repo.forSource(source)}{endpoints.rawInfix}{branch}/{path}"
        client = buildClient(timeout=10)
        try:
            resp = await client.get(url)
            try:
                resp.raise_for_status()
                return url, source
            finally:
                resp.close()
        except Exception as e:
            logger.debug("从 {} 下载 {}/{} 失败: {}", source, repo.name, path, repr(e))
            raise
        finally:
            client.close()

    result, index, _ = await staggered_race(
        [lambda s=s: probe(s) for s in SOURCE_ORDER], STAGGER_DELAY)
    if index is None:
        raise RuntimeError(f"无法下载 {repo.name}/{branch}/{path}")
    url, source = result
    await fetchFile(url, outputPath, onProgress=onProgress)
    return source


async def fetchReleaseAsset(
    repo: Repo, tag: str, asset: str, outputPath: Path,
    onProgress: Callable[[float], None] | None = None,
) -> str:
    async def probe(source):
        endpoints = SOURCES[source]
        url = f"{endpoints.download}/{repo.forSource(source)}/releases/download/{tag}/{asset}"
        client = buildClient(timeout=10)
        try:
            resp = await client.get(url)
            try:
                resp.raise_for_status()
                return url, source
            finally:
                resp.close()
        except Exception as e:
            logger.debug("从 {} 下载 {}/{} 失败: {}", source, repo.name, asset, repr(e))
            raise
        finally:
            client.close()

    result, index, _ = await staggered_race(
        [lambda s=s: probe(s) for s in SOURCE_ORDER], STAGGER_DELAY)
    if index is None:
        raise RuntimeError(f"无法下载 {repo.name}/{tag}/{asset}")
    url, source = result
    await fetchFile(url, outputPath, onProgress=onProgress)
    return source


PYPI_MIRRORS = {
    "gitcode": "https://mirrors.bfsu.edu.cn/pypi/web/json",
    "github": "https://pypi.org/pypi",
}


def buildPypiUrl(package: str, *, source: str) -> str:
    base = PYPI_MIRRORS.get(source, PYPI_MIRRORS["github"])
    if source == "gitcode":
        return f"{base}/{package}"
    return f"{base}/{package}/json"


async def fetchPypiJson(package: str) -> dict:
    async def attempt(source):
        url = buildPypiUrl(package, source=source)
        client = buildClient(timeout=15)
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return await resp.json()
        except Exception as e:
            logger.debug("从 {} 获取 PyPI {} 失败: {}", source, package, repr(e))
            raise
        finally:
            client.close()

    result, index, _ = await staggered_race(
        [lambda s=s: attempt(s) for s in SOURCE_ORDER], STAGGER_DELAY)
    if index is not None:
        return result
    raise RuntimeError(f"无法获取 PyPI 包信息: {package}")


def buildDownloadUrl(repo: Repo, tag: str, asset: str, *, source: str) -> str:
    endpoints = SOURCES[source]
    return f"{endpoints.download}/{repo.forSource(source)}/releases/download/{tag}/{asset}"


def buildRawUrl(repo: Repo, branch: str, path: str, *, source: str) -> str:
    endpoints = SOURCES[source]
    return f"{endpoints.raw}/{repo.forSource(source)}{endpoints.rawInfix}{branch}/{path}"
