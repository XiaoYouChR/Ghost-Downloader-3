"""Android View adapter for BilibiliPack."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .account import (
    BilibiliAccount,
    QR_EXPIRED,
    QR_GOT_URL,
    QR_LOGIN_FAILED,
    QR_LOGIN_SUCCESS,
    QR_SCANNED,
    QR_UNSCANNED,
)

if TYPE_CHECKING:
    from app.signal import Signal
    from .pack import BilibiliPack
    from .task import BilibiliTask

UI_CLASS = "com.xychr.ghostdownloader.features.bili_pack.BilibiliUi"


def qualityOptions() -> list[dict[str, int | str]]:
    from .config import QUALITY_VALUES, QUALITY_LABELS
    return [{"value": v, "label": l} for v, l in zip(QUALITY_VALUES, QUALITY_LABELS)]


def audioQualityOptions() -> list[dict[str, int | str]]:
    from .config import AUDIO_QUALITY_VALUES, AUDIO_QUALITY_LABELS
    return [{"value": v, "label": l} for v, l in zip(AUDIO_QUALITY_VALUES, AUDIO_QUALITY_LABELS)]


QR_STATUS = {
    QR_GOT_URL: "ready",
    QR_UNSCANNED: "waiting",
    QR_SCANNED: "scanned",
    QR_EXPIRED: "expired",
    QR_LOGIN_SUCCESS: "success",
    QR_LOGIN_FAILED: "failed",
}


@dataclass(frozen=True)
class QrState:
    status: str = "loading"
    message: str = ""


_account: BilibiliAccount | None = None
_qr = QrState()
_loginUrl = ""


def init(pack: BilibiliPack) -> dict[str, Signal]:
    global _account
    _account = pack.account
    _account.qrStateChanged.connect(_onQrStateChanged)
    return {"accountState": _account.accountChanged, "qrState": _account.qrStateChanged}


def taskFields(task: BilibiliTask) -> dict[str, str | bool]:
    return {
        "fileSelectKind": "videos" if task.hasManyVideos else "pages",
        "canSelectFiles": task.isVideoEnabled or task.isAudioEnabled,
    }


def fileFields(task: BilibiliTask) -> dict[int, dict[str, int]]:
    return {
        page.index: {
            "startTime": page.startTime,
            "endTime": page.endTime,
        }
        for page in task.files or []
    }


def applyFileEdits(task: BilibiliTask, edits: dict[str, Any]) -> None:
    from .task import setTimeRanges

    trim = {int(i): (v[0], v[1]) for i, v in (edits.get("trim") or {}).items()}
    if trim:
        setTimeRanges(task.files or [], trim)
    for index, name in (edits.get("titles") or {}).items():
        setFileName(task, int(index), name)


def fileGroups(task: BilibiliTask) -> dict[int, list[str]]:
    if not task.hasManyVideos:
        return {}
    return {
        page.index: [group[0].episodeTitle or group[0].bvid or f"#{group[0].index}"]
        for group in task.videoGroups() for page in group
    }


def toDraftOptions(pairs: list[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"key": key, "label": label} for key, label in pairs]


def draftFields(task: BilibiliTask) -> dict[str, Any]:
    from .task import (
        audioTiers, currentAudioTier, currentVideoTier, subtitleChoices, videoTiers,
    )

    page = task.files[0] if task.files and len(task.files) == 1 else None
    return {
        "controls": [
            {
                "id": "video",
                "title": "视频",
                "value": currentVideoTier(task) if task.isVideoEnabled else "",
                "options": toDraftOptions(videoTiers(task)),
                "isOptional": task.isAudioEnabled,
            },
            {
                "id": "audio",
                "title": "音频",
                "value": currentAudioTier(task) if task.isAudioEnabled else "",
                "options": toDraftOptions(audioTiers(task)),
                "isOptional": task.isVideoEnabled,
            },
        ],
        "isCoverEnabled": task.isCoverEnabled,
        "hasCover": bool(task.coverUrl),
        "subtitles": toDraftOptions(subtitleChoices(task)),
        "subtitleLanguages": list(task.subtitleLanguages),
        "duration": page._duration if page else 0,
        "startTime": page.startTime if page else 0,
        "endTime": page.endTime if page else 0,
        "hasPreview": bool(page and page.cid),
    }


def setControl(task: BilibiliTask, controlId: str, value: str) -> None:
    if controlId == "video":
        task.isVideoEnabled = bool(value)
        if value:
            task.setVideoQuality(*map(int, value.split("-")))
    elif controlId == "audio":
        task.isAudioEnabled = bool(value)
        if value:
            task.setAudioQuality(int(value))
    elif controlId == "cover":
        task.isCoverEnabled = bool(value)
    else:
        raise ValueError(f"Unknown control: {controlId}")
    task.update()


def setSubtitles(task: BilibiliTask, languages: str) -> None:
    task.setSubtitleLanguages([lan for lan in languages.split(",") if lan])


def setTrim(task: BilibiliTask, startTime: int, endTime: int) -> None:
    if not task.files:
        return
    duration = task.files[0]._duration
    if len(task.files) != 1 or not (0 <= startTime < (endTime or duration) <= duration):
        raise ValueError("Invalid trim range")
    task.files[0].startTime = startTime
    task.files[0].endTime = endTime
    task.update()


def setFileName(task: BilibiliTask, index: int, name: str) -> None:
    from .task import setFileName as _setFileName
    _setFileName(task, index, name)


async def probePreview(task: BilibiliTask) -> dict[str, Any]:
    import re
    from urllib.parse import urlparse
    from app.client import buildClient

    page = task.files[0] if task.files and len(task.files) == 1 else None
    match = re.match(r"/video/(BV[a-zA-Z0-9]+|av\d+)", urlparse(task.url).path)
    if not page or not page.cid or not match:
        return {"sheets": []}
    videoId = match.group(1)
    key, value = ("aid", videoId[2:]) if videoId.startswith("av") else ("bvid", videoId)
    headers = {"Referer": "https://www.bilibili.com/"}
    cookie = page.headers.get("cookie") or page.headers.get("Cookie")
    client = buildClient(headers={**headers, **({"Cookie": cookie} if cookie else {})})
    try:
        response = await client.get(f"https://api.bilibili.com/x/player/videoshot?{key}={value}&cid={page.cid}&index=1")
        try:
            response.raise_for_status()
            payload = await response.json()
        finally:
            response.close()
        if payload.get("code") != 0:
            raise ValueError("Preview request failed")
        data = payload.get("data") or {}
        columns, rows = int(data.get("img_x_len") or 10), int(data.get("img_y_len") or 10)
        count = columns * rows
        timestamps = data.get("index") or []
        return {"sheets": [
            {"url": "https:" + url if url.startswith("//") else url,
             "columns": columns, "rows": rows, "times": timestamps[index * count:(index + 1) * count]}
            for index, url in enumerate(data.get("image") or [])
        ], "headers": headers}
    finally:
        client.close()


# ---- account state (called by Kotlin via packState/requestPack) ----

def accountState() -> dict[str, bool | str]:
    assert _account is not None
    return {
        "isLoggedIn": _account.isLoggedIn,
        "username": _account.username,
        "mid": _account.mid,
        "vip": _account.vip,
        "cookie": _account.cookie,
    }


def qrState() -> dict[str, str]:
    return {"status": _qr.status, "url": _loginUrl, "message": _qr.message}


def setCookie(cookie: str) -> None:
    assert _account is not None
    _account.setCookie(cookie)


def logout() -> None:
    assert _account is not None
    _account.logout()


def startQrLogin() -> None:
    global _qr, _loginUrl
    assert _account is not None
    _qr, _loginUrl = QrState(), ""
    _account.startQrLogin()


def cancelQrLogin() -> None:
    assert _account is not None
    _account.cancelQrLogin()


async def fetchCaptcha() -> dict[str, str]:
    assert _account is not None
    return await _account.fetchCaptcha()


async def fetchCountries() -> dict[str, Any]:
    assert _account is not None
    return await _account.fetchCountries()


async def sendSmsCode(cid: int, tel: str, captcha: str) -> None:
    assert _account is not None
    await _account.sendSmsCode(cid, tel, json.loads(captcha))


async def loginSms(cid: int, tel: str, code: str) -> None:
    assert _account is not None
    await _account.loginSms(cid, tel, code)


def _onQrStateChanged(code: int, text: str) -> None:
    global _qr, _loginUrl
    status = QR_STATUS.get(code, "failed")
    if status == "ready":
        _loginUrl = text
    _qr = QrState(status, message=text if status == "failed" else "")
