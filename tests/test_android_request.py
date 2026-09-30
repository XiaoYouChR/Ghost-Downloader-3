from __future__ import annotations

import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.services.coroutine_runner import CoroutineRunner
from app.models.task import TaskError
from app.services.loopback_server import ListenState, ListenStatus
from tests.helpers import StubFlows


class StubTaskDraft:
    def __init__(self):
        self.calls = []

    def setBaseOptions(self, options):
        self.calls.append(("setBaseOptions", threading.get_ident()))

    def setUrls(self, urls):
        self.calls.append(("setUrls", urls))


class StubServer:
    def __init__(self, state: ListenState):
        self.state = state


@pytest.fixture
def engine(bridge):
    instance = bridge.Bridge.__new__(bridge.Bridge)
    instance._loop = asyncio.new_event_loop()
    thread = threading.Thread(target=instance._loop.run_forever, daemon=True)
    thread.start()
    instance._coroutineRunner = CoroutineRunner(
        dispatcher=instance._loop.call_soon_threadsafe, isAlive=None, loop=instance._loop)
    instance._flows = StubFlows()
    instance.loopThreadId = thread.ident

    yield instance

    instance._loop.call_soon_threadsafe(instance._loop.stop)
    thread.join(timeout=2)
    instance._loop.close()


def test_concurrent_requests_all_run_on_the_loop_thread(engine):
    seen = []
    engine.record = lambda i: seen.append((i, threading.get_ident())) or i

    with ThreadPoolExecutor(10) as pool:
        results = list(pool.map(lambda i: engine.request("record", i), range(50)))

    assert results == list(range(50))
    assert sorted(i for i, _ in seen) == list(range(50))
    assert {threadId for _, threadId in seen} == {engine.loopThreadId}


def test_async_method_is_awaited_on_the_loop(engine):
    async def fetch(value):
        await asyncio.sleep(0.01)
        return value * 2

    engine.fetch = fetch

    assert engine.request("fetch", 21) == 42


def test_error_reaches_the_caller(engine):
    def fail():
        raise ValueError("Task no longer exists")

    engine.fail = fail

    with pytest.raises(ValueError, match="Task no longer exists"):
        engine.request("fail")


def test_draft_parse_through_request_does_not_deadlock(engine, monkeypatch):
    engine._taskDraft = StubTaskDraft()
    engine._draftOptions = {}

    engine.request("parse", "https://a.test/1\n\nhttps://a.test/2")

    assert engine._taskDraft.calls == [
        ("setBaseOptions", engine.loopThreadId),
        ("setUrls", ["https://a.test/1", "https://a.test/2"]),
    ]


@pytest.mark.parametrize("state, expected", [
    (ListenState(), {"status": "off", "port": 0, "error": None}),
    (ListenState(ListenStatus.LISTENING, 16800), {"status": "listening", "port": 16800, "error": None}),
    (ListenState(ListenStatus.FAILED, 16800, error=TaskError("端口 {port} 被占用，请更换端口", port=16800)),
     {"status": "failed", "port": 16800,
      "error": {"message": "端口 {port} 被占用，请更换端口", "params": {"port": "16800"}}}),
])
def test_aria2_listen_state_is_pushed(engine, state, expected):
    engine._aria2RpcServer = StubServer(state)

    engine._emitAria2Rpc()

    assert json.loads(engine._flows.states["aria2Rpc"]) == expected


def test_aria2_parse_failure_is_a_notice(engine):
    engine._onParseFailed("https://a.test/f", TaskError("发生了意外错误：{detail}", detail="unreachable"))

    [(key, value)] = engine._flows.events
    assert key == "notice"
    assert json.loads(value) == {"kind": "parseFailed", "url": "https://a.test/f",
                                 "message": "发生了意外错误：{detail}", "params": {"detail": "unreachable"}}
