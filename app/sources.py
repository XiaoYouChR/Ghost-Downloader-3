from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from app.client import buildClient, fetchFile


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

SOURCE_ORDER = ("gitcode", "github")

GITCODE_REPOS = {
    "nilaoda/N_m3u8DL-RE": "XiaoYouChR/N_m3u8DL-RE-mirror",
    "quickjs-ng/quickjs": "XiaoYouChR/quickjs-mirror",
}


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


async def fetchLatestRelease(repo: str) -> tuple[Release, str]:
    for source in SOURCE_ORDER:
        mapped = GITCODE_REPOS.get(repo, repo) if source == "gitcode" else repo
        endpoints = SOURCES[source]
        url = f"{endpoints.api}/{mapped}/releases/latest"
        headers = {"accept": "application/vnd.github+json"} if source == "github" else {}
        client = buildClient(headers=headers, timeout=15)
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = await resp.json()
            return Release.fromResponse(data), source
        except Exception as e:
            logger.debug("从 {} 获取 {} release 失败: {}", source, repo, repr(e))
            continue
        finally:
            client.close()
    raise RuntimeError(f"无法获取 {repo} 的最新 release")


async def fetchLatestTag(repo: str) -> tuple[str, str]:
    release, source = await fetchLatestRelease(repo)
    return release.version, source


async def fetchJson(repo: str, branch: str, path: str) -> tuple[dict, str]:
    for source in SOURCE_ORDER:
        mapped = GITCODE_REPOS.get(repo, repo) if source == "gitcode" else repo
        endpoints = SOURCES[source]
        url = f"{endpoints.raw}/{mapped}{endpoints.rawInfix}{branch}/{path}"
        client = buildClient(timeout=15)
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            result = await resp.json()
            return result, source
        except Exception as e:
            logger.debug("从 {} 获取 {}/{} 失败: {}", source, repo, path, repr(e))
            continue
        finally:
            client.close()
    raise RuntimeError(f"无法获取 {repo}/{branch}/{path}")


async def fetchRawFile(
    repo: str, branch: str, path: str, outputPath: Path,
    onProgress: Callable[[float], None] | None = None,
) -> str:
    for source in SOURCE_ORDER:
        mapped = GITCODE_REPOS.get(repo, repo) if source == "gitcode" else repo
        endpoints = SOURCES[source]
        url = f"{endpoints.raw}/{mapped}{endpoints.rawInfix}{branch}/{path}"
        try:
            await fetchFile(url, outputPath, onProgress=onProgress)
            return source
        except Exception as e:
            logger.debug("从 {} 下载 {}/{} 失败: {}", source, repo, path, repr(e))
            continue
    raise RuntimeError(f"无法下载 {repo}/{branch}/{path}")


async def fetchReleaseAsset(
    repo: str, tag: str, asset: str, outputPath: Path,
    onProgress: Callable[[float], None] | None = None,
) -> str:
    for source in SOURCE_ORDER:
        mapped = GITCODE_REPOS.get(repo, repo) if source == "gitcode" else repo
        endpoints = SOURCES[source]
        url = f"{endpoints.download}/{mapped}/releases/download/{tag}/{asset}"
        try:
            await fetchFile(url, outputPath, onProgress=onProgress)
            return source
        except Exception as e:
            logger.debug("从 {} 下载 {}/{} 失败: {}", source, repo, asset, repr(e))
            continue
    raise RuntimeError(f"无法下载 {repo}/{tag}/{asset}")


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
    for source in SOURCE_ORDER:
        url = buildPypiUrl(package, source=source)
        client = buildClient(timeout=15)
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return await resp.json()
        except Exception as e:
            logger.debug("从 {} 获取 PyPI {} 失败: {}", source, package, repr(e))
            continue
        finally:
            client.close()
    raise RuntimeError(f"无法获取 PyPI 包信息: {package}")


def buildDownloadUrl(repo: str, tag: str, asset: str, *, source: str) -> str:
    mapped = GITCODE_REPOS.get(repo, repo) if source == "gitcode" else repo
    endpoints = SOURCES[source]
    return f"{endpoints.download}/{mapped}/releases/download/{tag}/{asset}"


def buildRawUrl(repo: str, branch: str, path: str, *, source: str) -> str:
    mapped = GITCODE_REPOS.get(repo, repo) if source == "gitcode" else repo
    endpoints = SOURCES[source]
    return f"{endpoints.raw}/{mapped}{endpoints.rawInfix}{branch}/{path}"
