from __future__ import annotations

from copy import deepcopy
from fnmatch import fnmatch
from urllib.parse import urlparse


DEFAULT_SITE_RULES = [
    {
        "id": "pixeldrain",
        "name": "PixelDrain",
        "hosts": ["pixeldrain.com", "*.pixeldrain.com"],
        "action": "pixeldrain_api",
        "enabled": True,
        "connections": 1,
        "description": "Uses the file API, correct Referer and one stable connection.",
    },
    {
        "id": "uupdump",
        "name": "UUP dump",
        "hosts": ["uupdump.net", "*.uupdump.net"],
        "action": "uupdump_post",
        "enabled": True,
        "connections": 1,
        "description": "Submits the required form and rejects HTML returned instead of ZIP data.",
    },
    {
        "id": "hdsex",
        "name": "HDSex",
        "hosts": ["hdsex.org", "*.hdsex.org"],
        "action": "prefer_latest_hls",
        "enabled": True,
        "connections": 1,
        "description": "Prefers the player's newest HLS manifest, skipping an earlier pre-roll stream.",
    },
]

SITE_RULE_ACTIONS = {
    "standard",
    "single_connection",
    "pixeldrain_api",
    "uupdump_post",
    "prefer_latest_hls",
}


def defaultSiteRules() -> list[dict]:
    return deepcopy(DEFAULT_SITE_RULES)


def normalizeHost(host: str) -> str:
    value = host.strip().lower()
    if "://" in value:
        value = (urlparse(value).hostname or "").lower()
    return value.strip("./")


def validateSiteRule(rule: object) -> bool:
    if not isinstance(rule, dict):
        return False
    hosts = rule.get("hosts")
    return (
        isinstance(rule.get("id"), str)
        and bool(rule["id"].strip())
        and isinstance(rule.get("name"), str)
        and bool(rule["name"].strip())
        and isinstance(hosts, list)
        and bool(hosts)
        and all(isinstance(host, str) and bool(normalizeHost(host)) for host in hosts)
        and rule.get("action") in SITE_RULE_ACTIONS
        and isinstance(rule.get("enabled"), bool)
        and isinstance(rule.get("connections", 1), int)
        and 1 <= rule.get("connections", 1) <= 256
    )


def matchingSiteRule(url: str, rules: list[dict]) -> dict | None:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return None
    for rule in rules:
        if not validateSiteRule(rule) or not rule.get("enabled", True):
            continue
        for pattern in rule["hosts"]:
            normalized = normalizeHost(pattern)
            if host == normalized or fnmatch(host, normalized):
                return rule
    return None


def publicSiteRules(rules: list[dict]) -> list[dict]:
    """Return the safe subset sent to the paired browser extension."""
    return [
        {
            "id": rule["id"],
            "name": rule["name"],
            "hosts": [normalizeHost(host) for host in rule["hosts"]],
            "action": rule["action"],
            "enabled": rule["enabled"],
        }
        for rule in rules
        if validateSiteRule(rule)
    ]
