"""Android draft adapter. No Qt imports; extraction uses the same functions as Desktop."""
from __future__ import annotations

from pathlib import Path

from .choices import buildAudioLanguageChoices, buildAudioTiers, buildSubtitleChoices, buildVideoTiers
from .task import YouTubeFile, buildFormatPair, probeFormats, probePlaylist

UI_CLASS = "com.xychr.ghostdownloader.features.yt_dlp_pack.YtDlpUi"


def toDraftOptions(pairs) -> list[dict]:
    return [{"key": key, "label": label} for key, label in pairs]


def draftFields(task) -> dict:
    info = getattr(task, "_mediaInfo", {})
    hasInfo = bool(info.get("formats"))
    subtitles, _ = buildSubtitleChoices(info, "自动")
    page = task.files[0] if task.files and len(task.files) == 1 else None
    videoTiers = buildVideoTiers(info, "最佳画质") if hasInfo else [("0", "最佳画质")]
    audioTiers = buildAudioTiers(info, "最佳音质") if hasInfo else [("0", "最佳音质")]
    return {
        "canProbeMedia": True,
        "hasMediaInfo": hasInfo,
        "canProbePlaylist": task.isPlaylist,
        "controls": [
            {
                "id": "video",
                "title": "视频",
                "value": str(task.maxVideoHeight) if task.isVideoEnabled else "",
                "options": toDraftOptions(videoTiers),
                "isOptional": task.isAudioEnabled,
            },
            {
                "id": "audio",
                "title": "音频",
                "value": str(task.maxAudioBitrate) if task.isAudioEnabled else "",
                "options": toDraftOptions(audioTiers),
                "isOptional": task.isVideoEnabled,
            },
            {
                "id": "language",
                "title": "语言",
                "value": task.audioLanguages if task.isAudioEnabled else "",
                "options": toDraftOptions(buildAudioLanguageChoices(info)),
                "isMultiple": True,
                "isOptional": True,
            },
        ],
        "isCoverEnabled": task.isCoverEnabled,
        "hasCover": bool(task.coverUrl),
        "subtitles": toDraftOptions(subtitles),
        "subtitleLanguages": [s for s in task.subtitleLanguages.split(",") if s],
        "duration": int(info.get("duration") or 0) if not task.isPlaylist else 0,
        "startTime": page.startTime if page else 0,
        "endTime": page.endTime if page else 0,
        "hasPreview": any(f.get("format_note") == "storyboard" for f in info.get("formats") or []),
    }


def probe(task, url, kind):
    if kind == "media":
        info = probeFormats(url)
        if not info or not info.get("formats"):
            raise ValueError("No media formats found")
        task._mediaInfo = info
        choices = buildAudioLanguageChoices(info)
        if choices and not task.audioLanguages:
            task.audioLanguages = choices[0][0]
        thumbnailUrl = info.get("thumbnail") or ""
        if thumbnailUrl:
            task.setCoverUrl(thumbnailUrl)
        updateSize(task)
    elif kind == "playlist":
        result = probePlaylist(url)
        if not result:
            raise ValueError("No playlist entries found")
        task.setVideos(result)
    else:
        raise ValueError(f"Unsupported probe kind: {kind}")


def updateSize(task):
    info = getattr(task, "_mediaInfo", None)
    if not info:
        return
    video, audio = buildFormatPair(info, task)
    task.fileSize = sum(int(f.get("filesize") or f.get("filesize_approx") or 0)
                        for f in (video, audio) if f)


def setControl(task, controlId, value):
    tracks = (task.isVideoEnabled, task.isAudioEnabled, task.isCoverEnabled)
    if controlId == "video":
        task.isVideoEnabled = bool(value)
        if value:
            task.maxVideoHeight = int(value)
    elif controlId == "audio":
        task.isAudioEnabled = bool(value)
        if value:
            task.maxAudioBitrate = int(value)
    elif controlId == "language":
        task.audioLanguages = value
    elif controlId == "cover":
        task.isCoverEnabled = bool(value)
    else:
        raise ValueError(f"Unknown control: {controlId}")
    if (task.isVideoEnabled, task.isAudioEnabled, task.isCoverEnabled) != tracks:
        extension = "mp4" if task.isVideoEnabled else "m4a" if task.isAudioEnabled else "jpg"
        task.setName(f"{Path(task.name).stem}.{extension}")
    updateSize(task)


def setSubtitles(task, languages):
    _, auto = buildSubtitleChoices(getattr(task, "_mediaInfo", {}), "")
    task.subtitleLanguages = languages
    task.shouldIncludeAutoSubs = bool(auto.intersection(languages.split(",")))


def setTrim(task, start, end):
    duration = int(getattr(task, "_mediaInfo", {}).get("duration") or 0)
    if task.isPlaylist or not (0 <= start < (end or duration) <= duration):
        raise ValueError("Invalid trim range")
    if not task.files:
        task.files = [YouTubeFile(index=0, relativePath="")]
    task.files[0].startTime = start
    task.files[0].endTime = end


def fileFields(task) -> dict:
    return {
        file.index: {
            "startTime": file.startTime,
            "endTime": file.endTime,
        }
        for file in task.files or []
    }


def applyFileEdits(task, edits: dict):
    trim = {int(i): (v[0], v[1]) for i, v in (edits.get("trim") or {}).items()}
    for file in task.files or []:
        if file.index in trim:
            file.startTime, file.endTime = trim[file.index]


def buildPreview(info):
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


async def probePreview(task):
    return buildPreview(getattr(task, "_mediaInfo", {}))


def cookieState() -> dict:
    from .config import hasCookieFile

    return {"hasCookies": hasCookieFile()}


def saveCookies(cookieText: str):
    from .config import saveCookies as _saveCookies

    _saveCookies(cookieText)


def clearCookies():
    from .config import clearCookies as _clearCookies

    _clearCookies()
