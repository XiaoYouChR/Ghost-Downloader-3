from __future__ import annotations

from aiohttp import web

from app import sources
from yt_dlp_pack.config import fetchNightlyWheel


def buildWheel(version: str, yanked: bool = False) -> dict:
    return {"filename": f"yt_dlp-{version}-py3-none-any.whl", "url": version, "yanked": yanked}


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
