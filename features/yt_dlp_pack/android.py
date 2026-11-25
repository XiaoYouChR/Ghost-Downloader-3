"""Android draft adapter. No Qt imports; extraction uses the same functions as Desktop."""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.i18n import N

from .choices import buildAudioLanguageChoices, buildAudioTiers, buildSubtitleChoices, buildVideoTiers
from .task import buildFormatPair, probeFormats, probePlaylist, parseLanguages

if TYPE_CHECKING:
    from .task import YouTubeTask

UI_CLASS = "com.xychr.ghostdownloader.features.yt_dlp_pack.YtDlpUi"


def toDraftOptions(pairs: list[tuple[str, str]], **params: Any) -> list[dict]:
    return [{"key": key, "label": label, "params": params} for key, label in pairs]


def draftFields(task: YouTubeTask) -> dict:
    info = getattr(task, "_mediaInfo", {})
    hasInfo = bool(info.get("formats"))
    subtitles, _ = buildSubtitleChoices(info, "{auto}")
    videoTiers = buildVideoTiers(info, "{best}") if hasInfo else [("0", "{best}")]
    audioTiers = buildAudioTiers(info, "{best}") if hasInfo else [("0", "{best}")]
    return {
        "canProbeMedia": True,
        "hasMediaInfo": hasInfo,
        "canProbePlaylist": task.isPlaylist,
        "controls": [
            {
                "id": "video",
                "title": N("TrackBar", "视频"),
                "value": str(task.maxVideoHeight) if task.isVideoEnabled else "",
                "options": toDraftOptions(videoTiers, best=N("YtDlpDraftCard", "最佳画质")),
                "isOptional": task.isAudioEnabled,
            },
            {
                "id": "audio",
                "title": N("TrackBar", "音频"),
                "value": str(task.maxAudioBitrate) if task.isAudioEnabled else "",
                "options": toDraftOptions(audioTiers, best=N("YtDlpDraftCard", "最佳音质")),
                "isOptional": task.isVideoEnabled,
            },
            {
                "id": "language",
                "title": N("YtDlpDraftCard", "音频语言"),
                "value": task.audioLanguages if task.isAudioEnabled else "",
                "options": toDraftOptions(buildAudioLanguageChoices(info)),
                "isMultiple": True,
                "isOptional": True,
            },
        ],
        "isCoverEnabled": task.isCoverEnabled,
        "hasCover": bool(task.coverUrl),
        "subtitles": toDraftOptions(subtitles, auto=N("YtDlpDraftCard", "自动")),
        "subtitleLanguages": [s for s in task.subtitleLanguages.split(",") if s],
        "duration": int(info.get("duration") or 0) if not task.isPlaylist else 0,
        "startTime": task.startTime,
        "endTime": task.endTime,
        "hasPreview": any(f.get("format_note") == "storyboard" for f in info.get("formats") or []),
    }


def probe(url: str, kind: str) -> Callable[[YouTubeTask], None]:
    if kind == "media":
        info = probeFormats(url)
        if not info or not info.get("formats"):
            raise ValueError("No media formats found")

        def apply(task: YouTubeTask) -> None:
            task._mediaInfo = info
            choices = buildAudioLanguageChoices(info)
            if choices and not task.audioLanguages:
                task.setAudioLanguages(choices[0][0])
            thumbnailUrl = info.get("thumbnail") or ""
            if thumbnailUrl:
                task.setCoverUrl(thumbnailUrl)
            updateSize(task)

        return apply
    if kind == "playlist":
        result = probePlaylist(url)
        if not result:
            raise ValueError("No playlist entries found")
        return lambda task: task.setVideos(result)
    raise ValueError(f"Unsupported probe kind: {kind}")


def updateSize(task: YouTubeTask) -> None:
    info = getattr(task, "_mediaInfo", None)
    if not info:
        return
    video, audio = buildFormatPair(info, task)
    task.fileSize = sum(int(f.get("filesize") or f.get("filesize_approx") or 0)
                        for f in (video, audio) if f)


def setControl(task: YouTubeTask, controlId: str, value: str) -> None:
    if controlId == "video":
        if value:
            task.maxVideoHeight = int(value)
        task.setTracks(bool(value), task.isAudioEnabled, task.isCoverEnabled)
    elif controlId == "audio":
        if value:
            task.maxAudioBitrate = int(value)
        task.setTracks(task.isVideoEnabled, bool(value), task.isCoverEnabled)
    elif controlId == "language":
        task.setAudioLanguages(value)
    elif controlId == "cover":
        task.setTracks(task.isVideoEnabled, task.isAudioEnabled, bool(value))
    else:
        raise ValueError(f"Unknown control: {controlId}")
    updateSize(task)


def setSubtitles(task: YouTubeTask, languages: str) -> None:
    _, auto = buildSubtitleChoices(getattr(task, "_mediaInfo", {}), "")
    task.setSubtitleLanguages(languages, bool(auto.intersection(parseLanguages(languages))))


def setTrim(task: YouTubeTask, start: int, end: int) -> None:
    task.startTime = start
    task.endTime = end


def fileFields(task: YouTubeTask) -> dict[int, dict[str, int]]:
    return {
        file.index: {
            "startTime": file.startTime,
            "endTime": file.endTime,
        }
        for file in task.files or []
    }


def applyFileEdits(task: YouTubeTask, edits: dict) -> None:
    trim = {int(i): (v[0], v[1]) for i, v in (edits.get("trim") or {}).items()}
    for file in task.files or []:
        if file.index in trim:
            file.startTime, file.endTime = trim[file.index]


def buildPreview(info: dict) -> dict:
    candidates = [f for f in info.get("formats") or []
                  if f.get("format_note") == "storyboard" and f.get("columns") and f.get("rows")]
    fmt = max(candidates, key=lambda f: f.get("width") or 0, default=None)
    if not fmt:
        return {"sheets": []}
    columns, rows = int(fmt["columns"]), int(fmt["rows"])
    count = columns * rows
    fps = float(fmt.get("fps") or 0)
    if fps <= 0:
        return {"sheets": []}
    sheets = []
    start = 0.0
    for fragment in fmt.get("fragments") or []:
        duration = float(fragment.get("duration") or 0)
        url = fragment.get("url") or fragment.get("path") or ""
        if url and duration > 0:
            sheets.append({
                "url": url, "columns": columns, "rows": rows,
                "times": [start + index / fps for index in range(count) if index / fps < duration],
            })
        start += duration
    return {"sheets": sheets, "headers": fmt.get("http_headers") or info.get("http_headers") or {}}


async def probePreview(task: YouTubeTask) -> dict:
    return buildPreview(getattr(task, "_mediaInfo", {}))


def cookieState() -> dict[str, bool]:
    from .config import hasCookieFile

    return {"hasCookies": hasCookieFile()}


def saveCookies(cookieText: str) -> None:
    from .config import saveCookies as _saveCookies

    _saveCookies(cookieText)


def clearCookies() -> None:
    from .config import clearCookies as _clearCookies

    _clearCookies()
