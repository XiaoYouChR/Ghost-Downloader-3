import asyncio

import pytest

from ed2k_pack import session as session_module


class _FakeClient:
    instances = []

    def __init__(self, executable, dataDir):
        self.executable = executable
        self.dataDir = dataDir
        self.isRunning = False
        self.startCalls = 0
        self.closeCalls = 0
        self.__class__.instances.append(self)

    async def start(self, settings):
        self.startCalls += 1
        await asyncio.sleep(0)
        self.isRunning = True

    async def close(self):
        self.closeCalls += 1
        self.isRunning = False


@pytest.fixture
def fake_client(monkeypatch):
    _FakeClient.instances.clear()
    monkeypatch.setattr(session_module, "Client", _FakeClient)
    monkeypatch.setattr(session_module.ed2kRuntime, "path", lambda: "/tmp/goed2kd")
    return _FakeClient


@pytest.mark.asyncio
async def test_open_replaces_stopped_client(fake_client):
    session = session_module.ED2kSession()
    stopped = fake_client("/tmp/old", "/tmp/data")
    session._client = stopped

    await session._open()

    assert session._client is not stopped
    assert session._client.isRunning
    assert session._client.startCalls == 1


@pytest.mark.asyncio
async def test_concurrent_open_starts_one_client(fake_client):
    session = session_module.ED2kSession()

    await asyncio.gather(session._open(), session._open())

    assert len(fake_client.instances) == 1
    assert fake_client.instances[0].startCalls == 1
