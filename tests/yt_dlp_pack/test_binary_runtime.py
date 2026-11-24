from __future__ import annotations

import pytest
from aiohttp import web

from app import sources
from app.models.task import TaskError
from yt_dlp_pack.config import fetchEjsWheel, fetchNightlyWheel


def buildWheel(version: str, yanked: bool = False, package: str = "yt_dlp") -> dict:
    return {"filename": f"{package}-{version}-py3-none-any.whl", "url": version, "yanked": yanked}


async def test_probe_nightly_is_latest_dev_build(startServer, monkeypatch):
    releases = {
        "2026.8.27.3630.dev0": [buildWheel("2026.8.27.3630.dev0")],
        "2026.8.20.234504.dev0": [buildWheel("2026.8.20.234504.dev0")],
        "2026.8.28.100.dev0": [buildWheel("2026.8.28.100.dev0", yanked=True)],
        "2026.8.29.1.dev0": [{"filename": "yt_dlp-2026.8.29.1.dev0.tar.gz", "url": "", "yanked": False}],
        "2026.9.1": [buildWheel("2026.9.1")],
    }

    async def handler(request):
        return web.json_response({"releases": releases})

    url = await startServer(handler)
    for source in sources.PYPI_MIRRORS:
        monkeypatch.setitem(sources.PYPI_MIRRORS, source, url)

    assert await fetchNightlyWheel() == ("2026.08.27.003630", "2026.8.27.3630.dev0")


async def test_fetch_ejs_wheel_matches_version_or_same_minor(startServer, monkeypatch):
    releases = {
        "0.7.0": [buildWheel("0.7.0", package="yt_dlp_ejs")],
        "0.8.0": [buildWheel("0.8.0", package="yt_dlp_ejs")],
        "0.8.1": [buildWheel("0.8.1", package="yt_dlp_ejs")],
        "0.8.2": [buildWheel("0.8.2", yanked=True, package="yt_dlp_ejs")],
        "0.8.3.dev0": [buildWheel("0.8.3.dev0", package="yt_dlp_ejs")],
    }

    async def handler(request):
        return web.json_response({"releases": releases})

    url = await startServer(handler)
    for source in sources.PYPI_MIRRORS:
        monkeypatch.setitem(sources.PYPI_MIRRORS, source, url)

    assert await fetchEjsWheel("0.8.0") == "0.8.0"
    assert await fetchEjsWheel("0.8.9") == "0.8.1"
    with pytest.raises(TaskError, match="yt-dlp-ejs"):
        await fetchEjsWheel("0.9.0")
