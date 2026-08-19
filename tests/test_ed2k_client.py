import asyncio

import pytest

from ed2k_pack.python_ed2k import Client


@pytest.mark.asyncio
async def test_cancelled_start_terminates_daemon(tmp_path):
    daemon = tmp_path / "slow-daemon"
    daemon.write_text(
        "#!/usr/bin/env python3\n"
        "import time\n"
        "time.sleep(60)\n"
    )
    daemon.chmod(0o755)

    client = Client(daemon, tmp_path / "data")
    start = asyncio.create_task(client.start())
    await asyncio.sleep(0.05)
    process = client._process
    assert process is not None
    start.cancel()

    with pytest.raises(asyncio.CancelledError):
        await start

    assert not client.isRunning
    assert client._process is None
    assert process.returncode is not None
