from __future__ import annotations

import pytest

from app.models.pack import PackServices
from http_pack.pack import HttpPack


@pytest.fixture
def features(engine):
    services = PackServices(coroutineRunner=engine.coroutineRunner, speedMeter=engine.speedMeter)
    engine.featureService.register(HttpPack(services))
    return engine.featureService


def test_match_skips_broken_link(features):
    assert not features.match("http://[abc")
