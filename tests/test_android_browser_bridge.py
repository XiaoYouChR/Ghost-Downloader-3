from __future__ import annotations

import json

import pytest

from app.config.cfg import cfg
from app.services.loopback_server import ListenFailure, ListenState, ListenStatus
from tests.helpers import StubFlows


class StubBrowserService:
    def __init__(self, summary=("", "")):
        self.connectionSummary = summary

    def regenerateToken(self):
        cfg.browserExtensionPairToken.value = "regenerated"


class StubServer:
    def __init__(self, state=ListenState(ListenStatus.LISTENING, 14370, hasIpv6=True)):
        self.state = state


@pytest.fixture
def engine(bridge, monkeypatch):
    monkeypatch.setattr(cfg.browserExtensionPairToken, "value", "tok")
    instance = bridge.Engine.__new__(bridge.Engine)
    instance._flows = StubFlows()
    instance._browserService = StubBrowserService()
    instance._browserServer = StubServer()
    return instance


@pytest.mark.parametrize(
    "state, summary, expected",
    [
        (ListenState(), ("", ""), "idle"),
        (ListenState(ListenStatus.FAILED, 14370, failure=ListenFailure.PORT_OCCUPIED), ("", ""), "failed"),
        (ListenState(ListenStatus.LISTENING, 14370), ("", ""), "listening"),
        (ListenState(ListenStatus.LISTENING, 14370), ("development", "2.2.0"), "connected"),
    ],
)
def test_status_tells_the_view_why_the_extension_cannot_connect(engine, state, summary, expected):
    engine._browserServer = StubServer(state)
    engine._browserService = StubBrowserService(summary=summary)

    payload = json.loads(engine.browserExtension())

    assert payload["status"] == expected
    assert payload["failure"] == state.failure


def test_connected_status_carries_the_extension_version(engine):
    engine._browserService = StubBrowserService(summary=("development", "2.2.0"))

    payload = json.loads(engine.browserExtension())

    assert payload["extensionVersion"] == "2.2.0"


def test_emit_pushes_under_the_key_the_view_observes(engine):
    engine._emitBrowserExtension()

    assert json.loads(engine._flows.states["browserExtension"])["token"] == "tok"


def test_regenerating_the_token_repushes_even_when_nobody_was_connected(engine):
    engine.regenerateBrowserToken()

    assert json.loads(engine._flows.states["browserExtension"])["token"] == "regenerated"


def test_store_links_follow_the_constants_rather_than_a_local_copy(engine, bridge, monkeypatch):
    monkeypatch.setattr(bridge, "CHROME_WEBSTORE_URL", "https://example.test/chrome")
    monkeypatch.setattr(bridge, "EDGE_ADDONS_URL", "https://example.test/edge")
    monkeypatch.setattr(bridge, "FIREFOX_ADDONS_URL", "https://example.test/firefox")

    payload = json.loads(engine.browserExtension())

    assert payload["chromeWebstore"] == "https://example.test/chrome"
    assert payload["edgeAddons"] == "https://example.test/edge"
    assert payload["firefoxAddons"] == "https://example.test/firefox"
