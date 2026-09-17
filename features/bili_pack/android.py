"""Android View adapter for BilibiliPack."""
from __future__ import annotations

import json
from dataclasses import dataclass

from .account import (
    QR_EXPIRED,
    QR_GOT_URL,
    QR_LOGIN_FAILED,
    QR_LOGIN_SUCCESS,
    QR_SCANNED,
    QR_UNSCANNED,
)

UI_CLASS = "com.xychr.ghostdownloader.features.bili_pack.BilibiliUi"

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


_account = None
_qr = QrState()
_loginUrl = ""


def init(pack) -> dict:
    global _account
    _account = pack.account
    _account.qrStateChanged.connect(_onQrStateChanged)
    return {"accountState": _account.accountChanged, "qrState": _account.qrStateChanged}


# ---- task/draft serialization (called by engine.py internally) ----

def taskFields(task) -> dict:
    return {
        "fileSelectKind": "season" if task.isSeason else "pages",
        "canSelectFiles": task.isVideoEnabled or task.isAudioEnabled,
    }


def fileFields(task) -> dict:
    return {
        page.index: {
            "startTime": page.startTime,
            "endTime": page.endTime,
        }
        for page in task.files or []
    }


def applyFileEdits(task, edits: dict):
    from .task import setTimeRanges

    trim = {int(i): (v[0], v[1]) for i, v in (edits.get("trim") or {}).items()}
    if trim:
        setTimeRanges(task.files or [], trim)
    for index, name in (edits.get("titles") or {}).items():
        setFileName(task, int(index), name)


def fileGroups(task) -> dict[int, list[str]]:
    if not task.isSeason:
        return {}
    return {
        page.index: [group[0].episodeTitle or group[0].bvid or f"#{group[0].index}"]
        for group in task.episodeGroups() for page in group
    }


def toDraftOptions(pairs) -> list[dict]:
    return [{"key": key, "label": label} for key, label in pairs]


def draftFields(task) -> dict:
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


# ---- draft mutations (called by engine.py setDraft dispatcher) ----

def setControl(task, controlId: str, value: str):
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


def setSubtitles(task, languages: str):
    task.setSubtitleLanguages([lan for lan in languages.split(",") if lan])


def setTrim(task, startTime: int, endTime: int):
    if not task.files:
        return
    duration = task.files[0]._duration
    if len(task.files) != 1 or not (0 <= startTime < (endTime or duration) <= duration):
        raise ValueError("Invalid trim range")
    task.files[0].startTime = startTime
    task.files[0].endTime = endTime
    task.update()


def setFileName(task, index: int, name: str):
    from .task import setFileName as _setFileName
    _setFileName(task, index, name)


async def probePreview(task):
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

def accountState() -> dict:
    return {
        "isLoggedIn": _account.isLoggedIn,
        "username": _account.username,
        "mid": _account.mid,
        "vip": _account.vip,
        "cookie": _account.cookie,
    }


def qrState() -> dict:
    return {"status": _qr.status, "url": _loginUrl, "message": _qr.message}


def setCookie(cookie: str):
    _account.setCookie(cookie)


def logout():
    _account.logout()


def startQrLogin():
    global _qr, _loginUrl
    _qr, _loginUrl = QrState(), ""
    _account.startQrLogin()


def cancelQrLogin():
    _account.cancelQrLogin()


async def fetchCaptcha() -> dict:
    return await _account.fetchCaptcha()


async def fetchCountries() -> dict:
    return await _account.fetchCountries()


async def sendSmsCode(cid: int, tel: str, captcha: str):
    await _account.sendSmsCode(cid, tel, json.loads(captcha))


async def loginSms(cid: int, tel: str, code: str):
    await _account.loginSms(cid, tel, code)


def _onQrStateChanged(code: int, text: str):
    global _qr, _loginUrl
    status = QR_STATUS.get(code, "failed")
    if status == "ready":
        _loginUrl = text
    _qr = QrState(status, message=text if status == "failed" else "")
