"""Android View adapter for BilibiliPack."""
from __future__ import annotations

import json

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
    task.files[0].startTime = startTime
    task.files[0].endTime = endTime
    task.update()


def setFileName(task, index: int, name: str):
    from .task import setFileName as _setFileName
    _setFileName(task, index, name)


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
