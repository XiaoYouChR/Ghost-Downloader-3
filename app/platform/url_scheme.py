from __future__ import annotations

URL_SCHEME = "ghostdownloader"


def isLaunchUri(uri: str) -> bool:
    return uri.startswith(f"{URL_SCHEME}://")


def isWakeUri(uri: str) -> bool:
    return uri.rstrip("/") == f"{URL_SCHEME}://wake"
