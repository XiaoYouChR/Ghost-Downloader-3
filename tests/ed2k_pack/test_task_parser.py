from __future__ import annotations

import pytest

from app.models.pack import PackServices
from app.models.task import TaskOptions
from ed2k_pack import pack as packModule
from ed2k_pack.pack import ED2kPack
from http_pack.pack import HttpPack

ED2K = "ed2k://|file|[SubGroup] Show 01.mkv|1024|0123456789ABCDEF0123456789ABCDEF|/"


class FakeED2kSession:
    def open(self, coroutineRunner, createKelpie) -> None:
        pass

    async def close(self) -> None:
        pass

    def isActive(self, task) -> bool:
        return False


@pytest.fixture
def features(engine, monkeypatch):
    monkeypatch.setattr(packModule, "ed2kSession", FakeED2kSession())
    services = PackServices(coroutineRunner=engine.coroutineRunner, speedMeter=engine.speedMeter)
    for pack in (ED2kPack(services), HttpPack(services)):
        engine.featureService.register(pack)
    return engine.featureService


async def test_parse_link_with_bracketed_name(features):
    task = await features.parse(TaskOptions(url=ED2K))

    assert task.name == "[SubGroup] Show 01.mkv"


def test_match_link_with_bracketed_name(features):
    assert features.match(ED2K)


def test_match_passive_link_with_bracketed_name(features):
    assert features.matchPassive(ED2K)
