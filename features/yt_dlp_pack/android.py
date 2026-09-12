"""Android draft adapter. No Qt imports; extraction uses the same functions as Desktop."""
from __future__ import annotations

from pathlib import Path

from .choices import buildAudioLanguageChoices, buildAudioTiers, buildSubtitleChoices, buildVideoTiers
from .task import YouTubeFile, buildFormatPair, probeFormats, probePlaylist

UI_CLASS = "com.xychr.ghostdownloader.packs.YtDlpUi"


def draftFields(task) -> dict:
    info = getattr(task, "_mediaInfo", {})
    hasInfo = bool(info.get("formats"))
    subtitles, _ = buildSubtitleChoices(info, "自动")
    page = task.files[0] if task.files and len(task.files) == 1 else None
    return {
        "canProbeMedia": True,
        "hasMediaInfo": hasInfo,
        "canProbePlaylist": task.isPlaylist,
        "videoTiers": [{"key": key, "label": label} for key, label in
                       (buildVideoTiers(info, "最佳画质") if hasInfo else [("0", "最佳画质")])],
        "audioTiers": [{"key": key, "label": label} for key, label in
                       (buildAudioTiers(info, "最佳音质") if hasInfo else [("0", "最佳音质")])],
        "videoTier": str(task.maxVideoHeight),
        "audioTier": str(task.maxAudioBitrate),
        "isVideoEnabled": task.isVideoEnabled,
        "isAudioEnabled": task.isAudioEnabled,
        "isCoverEnabled": task.isCoverEnabled,
        "hasCover": bool(task.coverUrl),
        "subtitles": [{"key": key, "label": label} for key, label in subtitles],
        "subtitleLanguages": [s for s in task.subtitleLanguages.split(",") if s],
        "audioLanguages": [{"key": key, "label": label} for key, label in buildAudioLanguageChoices(info)],
        "selectedAudioLanguages": [s for s in task.audioLanguages.split(",") if s],
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
        task.setCoverUrl(info.get("thumbnail") or "")
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


def setTrack(task, track, isEnabled):
    if track == "video":
        task.isVideoEnabled = isEnabled
    elif track == "audio":
        task.isAudioEnabled = isEnabled
    elif track == "cover":
        task.isCoverEnabled = isEnabled
    else:
        raise ValueError("Unknown track")
    extension = "mp4" if task.isVideoEnabled else "m4a" if task.isAudioEnabled else "jpg"
    task.setName(f"{Path(task.name).stem}.{extension}")
    updateSize(task)


def setQuality(task, track, key):
    if track == "video":
        task.maxVideoHeight = int(key)
    elif track == "audio":
        task.maxAudioBitrate = int(key)
    else:
        raise ValueError("Unknown track")
    updateSize(task)


def setAudioLanguages(task, languages):
    task.audioLanguages = languages
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
