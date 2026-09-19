from __future__ import annotations

import json

import pytest

from app.config.cfg import cfg
from tests.helpers import StubFlows


class StubBrowserService:
    def __init__(self, boundPort=14370, summary=("", "")):
        self.boundPort = boundPort
        self.connectionSummary = summary
        self.token = "tok"

    def regenerateToken(self):
        self.token = "regenerated"


@pytest.fixture
def engine(bridge):
    instance = bridge.Engine.__new__(bridge.Engine)
    instance._flows = StubFlows()
    instance._browserService = StubBrowserService()
    return instance


@pytest.fixture
def setEnabled(monkeypatch):
    def apply(value: bool):
        monkeypatch.setattr(cfg.isBrowserExtensionEnabled, "value", value)
    return apply


@pytest.mark.parametrize(
    "isEnabled, boundPort, summary, expected",
    [
        (False, 14370, ("", ""), "idle"),
        (True, 0, ("", ""), "portUnavailable"),
        (True, 14370, ("", ""), "listening"),
        (True, 14370, ("development", "2.2.0"), "connected"),
    ],
)
def test_status_tells_the_view_why_the_extension_cannot_connect(
    engine, setEnabled, isEnabled, boundPort, summary, expected,
):
    setEnabled(isEnabled)
    engine._browserService = StubBrowserService(boundPort=boundPort, summary=summary)

    payload = json.loads(engine.browserExtension())

    assert payload["status"] == expected


def test_connected_status_carries_the_extension_version(engine, setEnabled):
    setEnabled(True)
    engine._browserService = StubBrowserService(summary=("development", "2.2.0"))

    payload = json.loads(engine.browserExtension())

    assert payload["extensionVersion"] == "2.2.0"


def test_emit_pushes_under_the_key_the_view_observes(engine, setEnabled):
    setEnabled(True)

    engine._emitBrowserExtension()

    assert json.loads(engine._flows.states["browserExtension"])["token"] == "tok"


def test_regenerating_the_token_repushes_even_when_nobody_was_connected(engine, setEnabled):
    setEnabled(True)

    engine.regenerateBrowserToken()

    assert json.loads(engine._flows.states["browserExtension"])["token"] == "regenerated"


def test_store_links_follow_the_constants_rather_than_a_local_copy(engine, bridge, setEnabled, monkeypatch):
    setEnabled(True)
    monkeypatch.setattr(bridge, "CHROME_WEBSTORE_URL", "https://example.test/chrome")
    monkeypatch.setattr(bridge, "EDGE_ADDONS_URL", "https://example.test/edge")
    monkeypatch.setattr(bridge, "FIREFOX_ADDONS_URL", "https://example.test/firefox")

    payload = json.loads(engine.browserExtension())

    assert payload["chromeWebstore"] == "https://example.test/chrome"
    assert payload["edgeAddons"] == "https://example.test/edge"
    assert payload["firefoxAddons"] == "https://example.test/firefox"
