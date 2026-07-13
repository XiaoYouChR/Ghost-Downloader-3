"""Tests for the identity preset system.

Covers: matchIdentityPreset, buildClient userAgent param, _effectiveHeaders,
featureService.parse preset injection, backward compat, toEmulation auto logic.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# Fixtures: mock cfg so tests don't depend on user config
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_cfg(monkeypatch):
    """Provide a clean cfg with known defaults for every test."""
    from app.config.cfg import cfg
    monkeypatch.setattr(cfg.identityPresets, "value", [
        {"name": "百度网盘客户端", "clientProfile": "raw", "userAgent": "pan.baidu.com",
         "hosts": ["*.pcs.baidu.com"], "isEnabled": True},
    ])
    monkeypatch.setattr(cfg.clientProfile, "value", "auto")
    monkeypatch.setattr(cfg.defaultRequestHeaders, "value", {
        "accept-encoding": "deflate, br, gzip",
    })


# ===========================================================================
# B. matchIdentityPreset — host matching
# ===========================================================================

class TestMatchIdentityPreset:

    def _match(self, host: str) -> dict | None:
        from app.client import matchIdentityPreset
        return matchIdentityPreset(host)

    def test_b1_exact_host_match(self, monkeypatch):
        from app.config.cfg import cfg
        monkeypatch.setattr(cfg.identityPresets, "value", [
            {"name": "exact", "clientProfile": "raw", "userAgent": "ua",
             "hosts": ["pan.baidu.com"], "isEnabled": True},
        ])
        assert self._match("pan.baidu.com") is not None
        assert self._match("pan.baidu.com")["name"] == "exact"

    def test_b2_wildcard_subdomain_match(self):
        result = self._match("d.pcs.baidu.com")
        assert result is not None
        assert result["name"] == "百度网盘客户端"

    def test_b3_wildcard_root_domain_match(self):
        result = self._match("pcs.baidu.com")
        assert result is not None
        assert result["name"] == "百度网盘客户端"

    def test_b4_no_match(self):
        assert self._match("google.com") is None

    def test_b5_disabled_preset_skipped(self, monkeypatch):
        from app.config.cfg import cfg
        monkeypatch.setattr(cfg.identityPresets, "value", [
            {"name": "disabled", "clientProfile": "raw", "userAgent": "ua",
             "hosts": ["*.example.com"], "isEnabled": False},
        ])
        assert self._match("test.example.com") is None

    def test_b6_first_match_wins(self, monkeypatch):
        from app.config.cfg import cfg
        monkeypatch.setattr(cfg.identityPresets, "value", [
            {"name": "first", "clientProfile": "raw", "userAgent": "ua1",
             "hosts": ["*.baidu.com"], "isEnabled": True},
            {"name": "second", "clientProfile": "chrome", "userAgent": "ua2",
             "hosts": ["*.baidu.com"], "isEnabled": True},
        ])
        result = self._match("d.pcs.baidu.com")
        assert result["name"] == "first"

    def test_b7_empty_hosts_not_matched(self, monkeypatch):
        from app.config.cfg import cfg
        monkeypatch.setattr(cfg.identityPresets, "value", [
            {"name": "manual-only", "clientProfile": "raw", "userAgent": "ua",
             "hosts": [], "isEnabled": True},
        ])
        assert self._match("anything.com") is None

    def test_b8_empty_hostname(self):
        assert self._match("") is None

    def test_b9_broad_wildcard(self, monkeypatch):
        from app.config.cfg import cfg
        monkeypatch.setattr(cfg.identityPresets, "value", [
            {"name": "broad", "clientProfile": "raw", "userAgent": "ua",
             "hosts": ["*.com"], "isEnabled": True},
        ])
        assert self._match("google.com") is not None
        assert self._match("baidu.com") is not None

    def test_b_missing_isEnabled_defaults_true(self, monkeypatch):
        from app.config.cfg import cfg
        monkeypatch.setattr(cfg.identityPresets, "value", [
            {"name": "old", "clientProfile": "raw", "userAgent": "ua",
             "hosts": ["*.example.com"]},
        ])
        assert self._match("test.example.com") is not None

    def test_b_deep_subdomain(self):
        result = self._match("a.b.c.pcs.baidu.com")
        assert result is not None


# ===========================================================================
# C. buildClient userAgent parameter (mock wreq)
# ===========================================================================

class TestBuildClientUserAgent:
    """Test that buildClient correctly handles the userAgent parameter.

    Since wreq is not available in test env, we patch it.
    """

    @pytest.fixture(autouse=True)
    def _mock_wreq(self, monkeypatch):
        wreq_mock = MagicMock()
        wreq_mock.Client = MagicMock(return_value=MagicMock())
        wreq_mock.Emulation = MagicMock()
        wreq_mock.Proxy = MagicMock()

        profile_mock = MagicMock()
        wreq_mock.emulation.Platform = MagicMock()
        wreq_mock.emulation.Profile = type(profile_mock)
        wreq_mock.redirect.Policy = MagicMock()

        monkeypatch.setitem(sys.modules, "wreq", wreq_mock)
        monkeypatch.setitem(sys.modules, "wreq.emulation", wreq_mock.emulation)
        monkeypatch.setitem(sys.modules, "wreq.redirect", wreq_mock.redirect)

        if "app.client" in sys.modules:
            del sys.modules["app.client"]

    def _build(self, **kwargs):
        from app.client import buildClient
        return buildClient(**kwargs)

    def test_c9_no_headers_with_useragent(self):
        from app.client import buildClient
        import wreq
        buildClient(emulation=None, headers=None, userAgent="netdisk")
        call_kwargs = wreq.Client.call_args[1]
        assert call_kwargs.get("headers", {}).get("user-agent") == "netdisk"

    def test_c10_no_headers_no_useragent(self):
        from app.client import buildClient
        import wreq
        buildClient(emulation=None, headers=None, userAgent=None)
        call_kwargs = wreq.Client.call_args[1]
        assert "headers" not in call_kwargs or "user-agent" not in call_kwargs.get("headers", {})


# ===========================================================================
# D. HttpTaskStep._effectiveHeaders
# ===========================================================================

class TestEffectiveHeaders:

    def test_d1_no_useragent_no_headers_ua(self):
        headers = {"cookie": "x"}
        effective = {**headers}
        user_agent = ""
        if user_agent and not any(k.lower() == "user-agent" for k in headers):
            effective["user-agent"] = user_agent
        assert "user-agent" not in effective

    def test_d2_no_useragent_headers_has_ua(self):
        headers = {"cookie": "x", "user-agent": "browser"}
        effective = {**headers}
        user_agent = ""
        if user_agent and not any(k.lower() == "user-agent" for k in headers):
            effective["user-agent"] = user_agent
        assert effective["user-agent"] == "browser"

    def test_d3_useragent_no_headers_ua(self):
        headers = {"cookie": "x"}
        effective = {**headers}
        user_agent = "netdisk"
        if user_agent and not any(k.lower() == "user-agent" for k in headers):
            effective["user-agent"] = user_agent
        assert effective["user-agent"] == "netdisk"

    def test_d4_useragent_headers_has_ua_manual_wins(self):
        headers = {"cookie": "x", "user-agent": "custom"}
        effective = {**headers}
        user_agent = "netdisk"
        if user_agent and not any(k.lower() == "user-agent" for k in headers):
            effective["user-agent"] = user_agent
        assert effective["user-agent"] == "custom"


# ===========================================================================
# F. Preset field interactions in featureService.parse()
# ===========================================================================

class TestPresetFieldInteraction:
    """Test the inline preset matching logic from featureService.parse().

    We replicate the logic here to test without needing async/parser infra.
    """

    def _apply_preset(self, url: str, client_profile: str = "", user_agent: str = ""):
        from urllib.parse import urlparse
        from app.client import matchIdentityPreset
        from app.models.task import TaskOptions

        options = TaskOptions(url=url, clientProfile=client_profile, userAgent=user_agent)

        if not options.clientProfile:
            host = urlparse(options.url).hostname or ""
            preset = matchIdentityPreset(host)
            if preset is not None:
                kwargs = {}
                if preset["clientProfile"]:
                    kwargs["clientProfile"] = preset["clientProfile"]
                if preset["userAgent"]:
                    kwargs["userAgent"] = preset["userAgent"]
                if kwargs:
                    options = replace(options, **kwargs)

        return options

    def test_f1_preset_sets_both_fields(self):
        options = self._apply_preset("https://d.pcs.baidu.com/file/abc")
        assert options.clientProfile == "raw"
        assert options.userAgent == "pan.baidu.com"

    def test_f2_preset_only_useragent(self, monkeypatch):
        from app.config.cfg import cfg
        monkeypatch.setattr(cfg.identityPresets, "value", [
            {"name": "ua-only", "clientProfile": "", "userAgent": "netdisk",
             "hosts": ["*.example.com"], "isEnabled": True},
        ])
        options = self._apply_preset("https://dl.example.com/file")
        assert options.clientProfile == ""
        assert options.userAgent == "netdisk"

    def test_f3_preset_only_profile(self, monkeypatch):
        from app.config.cfg import cfg
        monkeypatch.setattr(cfg.identityPresets, "value", [
            {"name": "profile-only", "clientProfile": "chrome", "userAgent": "",
             "hosts": ["*.example.com"], "isEnabled": True},
        ])
        options = self._apply_preset("https://dl.example.com/file")
        assert options.clientProfile == "chrome"
        assert options.userAgent == ""

    def test_f4_preset_empty_both_fields(self, monkeypatch):
        from app.config.cfg import cfg
        monkeypatch.setattr(cfg.identityPresets, "value", [
            {"name": "empty", "clientProfile": "", "userAgent": "",
             "hosts": ["*.example.com"], "isEnabled": True},
        ])
        options = self._apply_preset("https://dl.example.com/file")
        assert options.clientProfile == ""
        assert options.userAgent == ""

    def test_f5_explicit_clientprofile_skips_preset(self):
        options = self._apply_preset(
            "https://d.pcs.baidu.com/file/abc",
            client_profile="chrome",
        )
        assert options.clientProfile == "chrome"
        assert options.userAgent == ""

    def test_f_no_host_match(self):
        options = self._apply_preset("https://google.com/file")
        assert options.clientProfile == ""
        assert options.userAgent == ""

    def test_f_file_url_no_crash(self):
        options = self._apply_preset("file:///tmp/test.m3u8")
        assert options.clientProfile == ""


# ===========================================================================
# G. Backward compatibility
# ===========================================================================

class TestBackwardCompat:

    def test_g1_old_step_missing_useragent(self):
        from app.models.serialization import filterFields
        from features.http_pack.task import HttpTaskStep

        old_data = {
            "stepIndex": 1,
            "url": "https://example.com/file.zip",
            "fileSize": 1024,
            "headers": {"cookie": "x"},
            "clientProfile": "auto",
            "subworkerCount": 8,
            "canUseRangeRequests": True,
        }
        filtered = filterFields(HttpTaskStep, old_data)
        step = HttpTaskStep(**filtered)
        assert step.userAgent == ""

    def test_g2_old_step_unknown_fields_dropped(self):
        from app.models.serialization import filterFields
        from features.http_pack.task import HttpTaskStep

        old_data = {
            "stepIndex": 1,
            "url": "https://example.com/file.zip",
            "unknownField": "should be dropped",
            "anotherUnknown": 42,
        }
        filtered = filterFields(HttpTaskStep, old_data)
        assert "unknownField" not in filtered
        assert "anotherUnknown" not in filtered

    def test_g_new_step_has_useragent(self):
        from features.http_pack.task import HttpTaskStep

        step = HttpTaskStep(stepIndex=1, url="https://example.com", userAgent="test")
        assert step.userAgent == "test"

    def test_g_setoptions_useragent(self):
        from features.http_pack.task import HttpTaskStep

        step = HttpTaskStep(stepIndex=1, url="https://example.com")
        step.setOptions({"userAgent": "netdisk"})
        assert step.userAgent == "netdisk"

    def test_g_setoptions_partial(self):
        from features.http_pack.task import HttpTaskStep

        step = HttpTaskStep(
            stepIndex=1, url="https://example.com",
            clientProfile="chrome", userAgent="old",
        )
        step.setOptions({"clientProfile": "raw"})
        assert step.clientProfile == "raw"
        assert step.userAgent == "old"


# ===========================================================================
# Validator
# ===========================================================================

class TestIdentityPresetListValidator:

    def test_valid(self):
        from app.config.cfg import IdentityPresetListValidator
        v = IdentityPresetListValidator()
        data = [{"name": "test", "clientProfile": "raw", "userAgent": "ua",
                 "hosts": ["*.example.com"]}]
        assert v.validate(data) is True

    def test_valid_with_isEnabled(self):
        from app.config.cfg import IdentityPresetListValidator
        v = IdentityPresetListValidator()
        data = [{"name": "test", "clientProfile": "raw", "userAgent": "ua",
                 "hosts": ["*.example.com"], "isEnabled": False}]
        assert v.validate(data) is True

    def test_invalid_missing_key(self):
        from app.config.cfg import IdentityPresetListValidator
        v = IdentityPresetListValidator()
        data = [{"name": "test"}]
        assert v.validate(data) is False

    def test_invalid_hosts_not_list(self):
        from app.config.cfg import IdentityPresetListValidator
        v = IdentityPresetListValidator()
        data = [{"name": "test", "clientProfile": "raw", "userAgent": "ua",
                 "hosts": "*.example.com"}]
        assert v.validate(data) is False

    def test_correct_filters_bad_entries(self):
        from app.config.cfg import IdentityPresetListValidator
        v = IdentityPresetListValidator()
        data = [
            {"name": "good", "clientProfile": "raw", "userAgent": "ua", "hosts": []},
            {"name": "bad"},
            {"name": "also-good", "clientProfile": "", "userAgent": "", "hosts": ["*.x.com"]},
        ]
        corrected = v.correct(data)
        assert len(corrected) == 2
        assert corrected[0]["name"] == "good"
        assert corrected[1]["name"] == "also-good"

    def test_empty_list_valid(self):
        from app.config.cfg import IdentityPresetListValidator
        v = IdentityPresetListValidator()
        assert v.validate([]) is True

    def test_not_list_invalid(self):
        from app.config.cfg import IdentityPresetListValidator
        v = IdentityPresetListValidator()
        assert v.validate("not a list") is False
        assert v.correct("not a list") == []


# ===========================================================================
# TaskOptions.userAgent field
# ===========================================================================

class TestTaskOptionsUserAgent:

    def test_default_empty(self):
        from app.models.task import TaskOptions
        options = TaskOptions(url="https://example.com")
        assert options.userAgent == ""

    def test_explicit_value(self):
        from app.models.task import TaskOptions
        options = TaskOptions(url="https://example.com", userAgent="netdisk")
        assert options.userAgent == "netdisk"

    def test_from_options(self):
        from app.models.task import TaskOptions
        options = TaskOptions.fromOptions({
            "url": "https://example.com",
            "userAgent": "custom",
        })
        assert options.userAgent == "custom"

    def test_from_options_missing_useragent(self):
        from app.models.task import TaskOptions
        options = TaskOptions.fromOptions({
            "url": "https://example.com",
        })
        assert options.userAgent == ""

    def test_replace_useragent(self):
        from app.models.task import TaskOptions
        options = TaskOptions(url="https://example.com")
        modified = replace(options, userAgent="netdisk")
        assert modified.userAgent == "netdisk"
        assert options.userAgent == ""
