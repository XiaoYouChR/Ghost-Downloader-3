from __future__ import annotations

import asyncio
import sys

import pytest
from aiohttp import web

from tests.helpers import loadEngine


@pytest.fixture(scope="module")
def bridge():
    return loadEngine()


@pytest.fixture
async def server():
    """Yields a factory: call with a handler to get a base URL."""
    runners = []

    async def start(handler):
        app = web.Application()
        app.router.add_get("/file", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        runners.append(runner)
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}/file"

    yield start

    for runner in runners:
        await runner.cleanup()


def pytest_asyncio_loop_factories(config, item):
    marker = item.get_closest_marker("asyncio")
    if marker is None or "loop_factories" not in marker.kwargs:
        return {"asyncio": asyncio.new_event_loop}
    if sys.platform == "win32":
        from winloop import new_event_loop
    else:
        from uvloop import new_event_loop
    return {"asyncio": asyncio.new_event_loop, "uvloop": new_event_loop}
