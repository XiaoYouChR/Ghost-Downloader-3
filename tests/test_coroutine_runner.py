from __future__ import annotations

import asyncio

from app.services.coroutine_runner import CoroutineRunner


async def test_work_cancelled_before_it_is_scheduled_never_runs():
    loop = asyncio.get_running_loop()
    runner = CoroutineRunner(loop.call_soon, loop=loop)
    started = []
    finished = []

    async def work():
        started.append(True)

    workId = runner.submit(work())
    runner.cancel(workId, finished=lambda: finished.append(True))
    await asyncio.sleep(0.05)

    assert started == []
    assert finished == [True]
