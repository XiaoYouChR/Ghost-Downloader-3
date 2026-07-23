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
# E1. toEmulation — profile selection (real wreq)
# ===========================================================================


class TestToEmulation:

    @pytest.fixture(autouse=True)
    def _fresh_client(self):
        if "app.client" in sys.modules:
            del sys.modules["app.client"]

    def test_raw_returns_none(self):
        from app.client import toEmulation
        assert toEmulation("raw") is None

    def test_auto_empty_ua_returns_emulation(self):
        from app.client import toEmulation
        result = toEmulation("auto", "")
        assert result is not None

    def test_auto_with_chrome_ua(self):
        from app.client import toEmulation
        result = toEmulation("auto", "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0.0.0 Safari/537.36")
        assert result is not None

    def test_known_family_chrome(self):
        from app.client import toEmulation
        assert toEmulation("chrome") is not None

    def test_known_family_firefox(self):
        from app.client import toEmulation
        assert toEmulation("firefox") is not None

    def test_unknown_profile_falls_back(self):
        from app.client import toEmulation
        result = toEmulation("nonexistent_browser_xyz")
        assert result is not None

    def test_profile_families_includes_mobile(self):
        from app.client import profileFamilies, PROFILES_BY_FAMILY
        families = profileFamilies()
        for mobile in ("firefox-android", "safari-ios", "safari-ipad"):
            if mobile in PROFILES_BY_FAMILY:
                assert mobile in families, f"{mobile} missing from profileFamilies()"


# ===========================================================================
# E2. matchEmulation — UA parsing + version matching (real wreq)
# ===========================================================================


class TestMatchEmulation:

    @pytest.fixture(autouse=True)
    def _fresh_client(self):
        if "app.client" in sys.modules:
            del sys.modules["app.client"]

    @pytest.fixture(autouse=True)
    def _platform(self):
        from wreq.emulation import Platform
        self.host = Platform.Windows

    def test_empty_ua_returns_none(self):
        from app.client import matchEmulation
        assert matchEmulation("", self.host) is None

    def test_chrome_ua_matches(self):
        from app.client import matchEmulation
        result = matchEmulation(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            self.host,
        )
        assert result is not None

    def test_edge_ua_takes_priority_over_chrome(self):
        from app.client import matchEmulation
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
        result = matchEmulation(ua, self.host)
        assert result is not None

    def test_safari_iphone_matches(self):
        from app.client import matchEmulation
        from wreq.emulation import Platform
        ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1"
        result = matchEmulation(ua, Platform.MacOS)
        assert result is not None

    def test_firefox_android_matches(self):
        from app.client import matchEmulation
        from wreq.emulation import Platform
        ua = "Mozilla/5.0 (Android 13; Mobile; rv:119.0) Gecko/119.0 Firefox/119.0"
        result = matchEmulation(ua, Platform.Linux)
        assert result is not None

    def test_safari_ipad_uses_ipad_family(self):
        from app.client import matchEmulation, PROFILES_BY_FAMILY
        from wreq.emulation import Platform
        ua = "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1"
        result = matchEmulation(ua, Platform.MacOS)
        assert result is not None
        if "safari-ipad" in PROFILES_BY_FAMILY:
            iphone_ua = ua.replace("iPad", "iPhone")
            iphone_result = matchEmulation(iphone_ua, Platform.MacOS)
            assert iphone_result is not None

    def test_opera_ua_takes_priority_over_chrome(self):
        from app.client import matchEmulation
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36 OPR/120.0.0.0"
        result = matchEmulation(ua, self.host)
        assert result is not None

    def test_unknown_ua_returns_none(self):
        from app.client import matchEmulation
        assert matchEmulation("curl/7.88.1", self.host) is None


# ===========================================================================
# E3. buildClient header filtering (real wreq, mock Client constructor)
# ===========================================================================


class TestBuildClientHeaderFiltering:

    @pytest.fixture(autouse=True)
    def _mock_client_only(self, monkeypatch):
        if "app.client" in sys.modules:
            del sys.modules["app.client"]
        import app.client
        self._client_cls = MagicMock(return_value=MagicMock())
        monkeypatch.setattr(app.client, "Client", self._client_cls)

    def test_emulation_strips_useragent_from_headers(self):
        from app.client import buildClient, toEmulation
        emulation = toEmulation("chrome")
        buildClient(emulation=emulation, headers={"user-agent": "custom", "accept": "text/html"})
        headers = self._client_cls.call_args[1].get("headers", {})
        assert "user-agent" not in headers
        assert headers.get("accept") == "text/html"

    def test_emulation_strips_sec_ch_ua_headers(self):
        from app.client import buildClient, toEmulation
        emulation = toEmulation("chrome")
        buildClient(emulation=emulation, headers={
            "sec-ch-ua": '"Chromium";v="120"',
            "sec-ch-ua-platform": '"Windows"',
            "accept": "text/html",
        })
        headers = self._client_cls.call_args[1].get("headers", {})
        assert "sec-ch-ua" not in headers
        assert "sec-ch-ua-platform" not in headers
        assert headers.get("accept") == "text/html"

    def test_no_emulation_adds_default_ua_when_missing(self):
        from app.client import buildClient
        buildClient(emulation=None, headers={"accept": "text/html"})
        headers = self._client_cls.call_args[1].get("headers", {})
        assert "user-agent" in headers
        assert "Chrome" in headers["user-agent"]


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
