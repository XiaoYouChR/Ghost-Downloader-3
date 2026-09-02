from __future__ import annotations

import pytest
from aiohttp import web


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
