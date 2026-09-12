from __future__ import annotations

from .task import DIRECT_PROTOCOLS


def toCodecName(codec: str) -> str:
    if not codec or codec == "none":
        return ""
    c = codec.lower()
    if c.startswith("av01"):
        return "AV1"
    if c.startswith("vp9") or c.startswith("vp09"):
        return "VP9"
    if c.startswith("avc") or c.startswith("h264"):
        return "H.264"
    if c.startswith("hev") or c.startswith("hvc") or c.startswith("h265"):
        return "H.265"
    if c == "opus":
        return "Opus"
    if c.startswith("mp4a"):
        return "AAC"
    return ""


def toCodecLabel(fmt: dict) -> str:
    codec = toCodecName(fmt.get("vcodec", "")) or toCodecName(fmt.get("acodec", ""))
    br = fmt.get("vbr") or fmt.get("abr") or fmt.get("tbr") or 0
    parts = []
    if codec:
        parts.append(codec)
    if br >= 1000:
        parts.append(f"{br / 1000:.1f}Mbps")
    elif br > 0:
        parts.append(f"{int(br)}Kbps")
    return ", ".join(parts)


def buildVideoTiers(mediaInfo: dict, bestLabel: str) -> list[tuple[str, str]]:
    formats = mediaInfo.get("formats") or []
    best: dict[int, dict] = {}

    for f in formats:
        if f.get("vcodec") in (None, "none"):
            continue
        height = f.get("height") or 0
        if height <= 0:
            continue
        vbr = f.get("vbr") or f.get("tbr") or 0
        if height not in best or vbr > (best[height].get("vbr") or best[height].get("tbr") or 0):
            best[height] = f

    tiers = sorted(best.keys(), reverse=True)

    result: list[tuple[str, str]] = []
    if tiers:
        fmt = best[tiers[0]]
        fps = fmt.get("fps") or 0
        fpsLabel = "60" if fps > 30 else ""
        info = toCodecLabel(fmt)
        label = bestLabel + (f" ({tiers[0]}p{fpsLabel}, {info})" if info else f" ({tiers[0]}p{fpsLabel})")
        result.append(("0", label))

    for height in tiers:
        fmt = best[height]
        fps = fmt.get("fps") or 0
        fpsLabel = "60" if fps > 30 else ""
        info = toCodecLabel(fmt)
        label = f"{height}p{fpsLabel} ({info})" if info else f"{height}p{fpsLabel}"
        result.append((str(height), label))

    return result


def buildAudioTiers(mediaInfo: dict, bestLabel: str) -> list[tuple[str, str]]:
    formats = mediaInfo.get("formats") or []
    best: dict[int, dict] = {}

    for f in formats:
        if f.get("acodec") in (None, "none"):
            continue
        if f.get("vcodec", "none") != "none":
            continue
        abr = int(f.get("abr") or f.get("tbr") or 0)
        if abr <= 0:
            continue
        bucket = round(abr / 16) * 16
        if bucket not in best or abr > int(best[bucket].get("abr") or best[bucket].get("tbr") or 0):
            best[bucket] = f

    tiers = sorted(best.keys(), reverse=True)

    result: list[tuple[str, str]] = []
    if tiers:
        info = toCodecLabel(best[tiers[0]])
        result.append(("0", bestLabel + f" ({info})" if info else bestLabel))
    for bucket in tiers:
        fmt = best[bucket]
        abr = int(fmt.get("abr") or fmt.get("tbr") or 0)
        codec = toCodecName(fmt.get("acodec", ""))
        label = f"{abr}Kbps ({codec})" if codec else f"{abr}Kbps"
        result.append((str(abr), label))

    return result


def buildSubtitleChoices(mediaInfo: dict, automaticLabel: str) -> tuple[list[tuple[str, str]], set[str]]:
    choices: list[tuple[str, str]] = []
    autoLangs: set[str] = set()
    seen: set[str] = set()

    for lang in (mediaInfo.get("subtitles") or {}):
        if lang not in seen:
            seen.add(lang)
            choices.append((lang, lang))

    for lang in (mediaInfo.get("automatic_captions") or {}):
        if lang not in seen:
            seen.add(lang)
            autoLangs.add(lang)
            choices.append((lang, f"{lang} ({automaticLabel})"))

    return choices, autoLangs


def buildAudioLanguageChoices(mediaInfo: dict) -> list[tuple[str, str]]:
    formats = mediaInfo.get("formats") or []
    seen: dict[str, tuple[str, int]] = {}

    for f in formats:
        if f.get("acodec", "none") == "none" or f.get("vcodec", "none") != "none":
            continue
        if f.get("protocol") not in DIRECT_PROTOCOLS:
            continue
        lang = f.get("language")
        if not lang or lang in seen:
            continue
        note = f.get("format_note") or ""
        comma = note.find(",")
        displayName = note[:comma].strip() if comma >= 0 else note.strip()
        pref = f.get("language_preference") or 0
        if not displayName:
            displayName = f"{lang} (Original)" if pref >= 10 else lang
        seen[lang] = (displayName, pref)

    if len(seen) <= 1:
        return []

    items = sorted(seen.items(), key=lambda kv: (-kv[1][1], kv[1][0]))
    return [(lang, displayName) for lang, (displayName, _) in items]
