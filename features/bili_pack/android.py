"""Android View adapter for BilibiliPack."""
from __future__ import annotations

import json

UI_CLASS = "com.xychr.ghostdownloader.packs.BilibiliUi"

_account = None
_qr: dict = {}


def init(pack):
    global _account
    _account = pack.account
    _account.qrStateChanged.connect(_onQrStateChanged)


# ---- task/draft serialization (called by engine.py internally) ----

def draftFields(task) -> dict:
    from .task import (
        audioTiers, currentAudioTier, currentVideoTier, subtitleChoices, videoTiers,
    )

    page = task.files[0] if task.files and len(task.files) == 1 else None
    return {
        "videoTiers": [{"key": k, "label": l} for k, l in videoTiers(task)],
        "audioTiers": [{"key": k, "label": l} for k, l in audioTiers(task)],
        "subtitles": [{"key": k, "label": l} for k, l in subtitleChoices(task)],
        "videoTier": currentVideoTier(task),
        "audioTier": currentAudioTier(task),
        "subtitleLanguages": list(task.subtitleLanguages),
        "isVideoEnabled": task.isVideoEnabled,
        "isAudioEnabled": task.isAudioEnabled,
        "isCoverEnabled": task.isCoverEnabled,
        "hasCover": bool(task.coverUrl),
        "canRenameFiles": True,
        "duration": page._duration if page else 0,
        "startTime": page.startTime if page else 0,
        "endTime": page.endTime if page else 0,
        "hasPreview": bool(page and page.cid),
    }


# ---- draft mutations (called by engine.py setDraft dispatcher) ----

def setTrack(task, track: str, isEnabled: bool):
    if track == "video":
        task.isVideoEnabled = isEnabled
    elif track == "audio":
        task.isAudioEnabled = isEnabled
    else:
        task.isCoverEnabled = isEnabled
    task.update()


def setQuality(task, track: str, key: str):
    if track == "video":
        qn, codecid = key.split("-")
        task.setVideoQuality(int(qn), int(codecid))
    else:
        task.setAudioQuality(int(key))


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
    return dict(_qr)


def setCookie(cookie: str):
    _account.setCookie(cookie)


def logout():
    _account.logout()


def startQrLogin():
    _qr.clear()
    _account.startQrLogin()


def cancelQrLogin():
    _account.cancelQrLogin()


def _onQrStateChanged(code: int, text: str):
    _qr["code"] = code
    _qr["url" if code == 0 else "text"] = text
