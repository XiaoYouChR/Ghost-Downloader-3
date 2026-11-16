from __future__ import annotations

import asyncio
import html
import math
import re
import urllib.parse
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from app.client import buildClient
from app.models.task import TaskError

if TYPE_CHECKING:
    import wreq

DANMAKU_SEG_API = "https://api.bilibili.com/x/v2/dm/wbi/web/seg.so"
SEGMENT_SECONDS = 360
MAX_CONCURRENCY = 3
MAX_PROBE_SEGMENTS = 200
SCROLL_DURATION = 12.0
FIXED_DURATION = 5.0
BASE_FONT_SIZE = 38
TRACK_SLOT_HEIGHT = 44
TRACK_MARGIN_Y = 10
XML_INVALID_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
ASS_CONTROL_RE = re.compile(r"[\x00-\x09\x0b-\x1f]")


@dataclass(frozen=True, slots=True)
class DanmakuItem:
    id: int
    progressMs: int
    mode: int = 1
    fontsize: int = 25
    color: int = 0xFFFFFF
    midHash: str = ""
    content: str = ""
    ctime: int = 0
    weight: int = 0
    pool: int = 0
    idStr: str = ""


def parseVarint(buf: bytes, pos: int) -> tuple[int, int]:
    value = 0
    shift = 0
    length = len(buf)
    while pos < length:
        byte = buf[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return value, pos
        shift += 7
        if shift > 63:
            raise ValueError("varint 长度超出 64 位上限")
    raise ValueError("varint 数据被截断")


def parseFields(buf: bytes) -> Iterator[tuple[int, int | bytes]]:
    pos = 0
    length = len(buf)
    try:
        while pos < length:
            tag, pos = parseVarint(buf, pos)
            fieldNum = tag >> 3
            wireType = tag & 7
            if wireType == 0:
                val, pos = parseVarint(buf, pos)
                yield fieldNum, val
            elif wireType == 2:
                size, pos = parseVarint(buf, pos)
                end = pos + size
                if end > length:
                    return
                yield fieldNum, buf[pos:end]
                pos = end
            elif wireType in {1, 5}:
                end = pos + (8 if wireType == 1 else 4)
                if end > length:
                    return
                pos = end
            else:
                return
    except ValueError:
        return


def parseElem(buf: bytes) -> DanmakuItem | None:
    ints: dict[int, int] = {}
    strs: dict[int, str] = {}
    for fieldNum, value in parseFields(buf):
        if isinstance(value, int):
            ints[fieldNum] = value
        elif fieldNum in {6, 7, 12}:
            strs[fieldNum] = value.decode("utf-8", errors="replace")

    content = strs.get(7, "")
    if not content:
        return None

    rawProgress = ints.get(2, 0) & 0xFFFFFFFF
    progressMs = rawProgress - 0x100000000 if rawProgress >= 0x80000000 else rawProgress
    elemId = ints.get(1, 0)
    return DanmakuItem(
        id=elemId,
        progressMs=max(0, progressMs),
        mode=ints.get(3) or 1,
        fontsize=ints.get(4) or 25,
        # proto3 会省略默认标量 0，黑色 #000000 不会出现在线缆上
        color=ints.get(5, 0),
        midHash=strs.get(6, ""),
        content=content,
        ctime=ints.get(8, 0),
        weight=ints.get(9, 0),
        pool=ints.get(11, 0),
        idStr=strs.get(12) or (str(elemId) if elemId else ""),
    )


def parseSegment(buf: bytes) -> tuple[list[DanmakuItem], bool]:
    items: list[DanmakuItem] = []
    isClosed = False
    for fieldNum, value in parseFields(buf):
        if fieldNum == 1 and isinstance(value, bytes):
            item = parseElem(value)
            if item is not None:
                items.append(item)
        elif fieldNum == 2 and value == 1:
            isClosed = True
    return items, isClosed


async def fetchSegment(
    client: wreq.Client,
    *,
    cid: int,
    aid: int,
    segmentIndex: int,
    signParams: Callable[[dict[str, Any]], dict[str, Any]] | None,
) -> tuple[list[DanmakuItem], bool, int]:
    params: dict[str, Any] = {
        "type": 1,
        "oid": cid,
        "segment_index": segmentIndex,
    }
    if aid > 0:
        params["pid"] = aid
    if signParams is not None:
        params = signParams(params)
    url = f"{DANMAKU_SEG_API}?{urllib.parse.urlencode(params)}"

    response = await client.get(url)
    try:
        status = response.status.as_int()
        if status == 412:
            raise TaskError("Bilibili 拦截了弹幕请求（412 风控），请稍后再试")
        # 越界分段会直接返回空体 304，属于正常结尾而非异常
        if status == 304:
            return [], False, 0
        response.raise_for_status()

        contentType = bytes(response.headers.get("content-type") or b"").lower()
        if b"application/json" in contentType:
            payload = await response.json()
            if payload.get("code") not in {None, 0}:
                raise ValueError(payload.get("message") or "获取弹幕失败")
            return [], False, 0

        raw = bytes(await response.bytes())
    finally:
        response.close()

    if not raw:
        return [], False, 0
    items, isClosed = parseSegment(raw)
    return items, isClosed, len(raw)


def buildFilteredItems(
    items: Iterable[DanmakuItem],
    *,
    startTime: int = 0,
    endTime: int = 0,
) -> list[DanmakuItem]:
    deduped: list[DanmakuItem] = []
    seenIds: set[int] = set()
    startMs = max(0, startTime) * 1000
    endMs = endTime * 1000

    for item in items:
        if item.id:
            if item.id in seenIds:
                continue
            seenIds.add(item.id)
        if item.progressMs < startMs or (endMs > 0 and item.progressMs > endMs):
            continue
        if startMs > 0:
            item = replace(item, progressMs=item.progressMs - startMs)
        deduped.append(item)

    deduped.sort(key=lambda d: (d.progressMs, d.id))
    return deduped


async def fetchDanmaku(
    cid: int,
    *,
    aid: int = 0,
    duration: int = 0,
    startTime: int = 0,
    endTime: int = 0,
    headers: dict[str, str] | None = None,
    signParams: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    onProgress: Callable[[int, int, int], None] | None = None,
) -> list[DanmakuItem]:
    pageHeaders = headers or {}
    reqHeaders = {"referer": pageHeaders.get("referer") or pageHeaders.get("Referer") or "https://www.bilibili.com"}
    cookie = pageHeaders.get("cookie") or pageHeaders.get("Cookie") or ""
    if cookie:
        reqHeaders["cookie"] = cookie

    client = buildClient(emulation=None, headers=reqHeaders)
    try:
        if signParams is None:
            from .account import fetchWbiMixinKey, signWbiParams
            try:
                mixinKey = await fetchWbiMixinKey()
            except Exception:
                mixinKey = ""
            signParams = (lambda params: signWbiParams(params, mixinKey)) if mixinKey else None

        first = max(0, startTime) // SEGMENT_SECONDS + 1
        effectiveEnd = endTime if endTime > 0 else duration
        if effectiveEnd > 0:
            last = max(first, (effectiveEnd - 1) // SEGMENT_SECONDS + 1)
            segments = range(first, last + 1)
            total = len(segments)
            semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
            doneCount = 0
            isClosed = False

            async def fetchOne(segIdx: int) -> list[DanmakuItem]:
                nonlocal doneCount, isClosed
                if isClosed:
                    return []
                async with semaphore:
                    if isClosed:
                        return []
                    items, segClosed, byteCount = await fetchSegment(
                        client,
                        cid=cid,
                        aid=aid,
                        segmentIndex=segIdx,
                        signParams=signParams,
                    )
                    if segClosed:
                        isClosed = True
                    doneCount += 1
                    if onProgress is not None:
                        onProgress(doneCount, total, byteCount)
                    return [] if segClosed else items

            batches = await asyncio.gather(*(fetchOne(idx) for idx in segments))
            if isClosed:
                return []
            rawItems = [item for batch in batches for item in batch]
        else:
            rawItems = []
            for offset in range(MAX_PROBE_SEGMENTS):
                items, segClosed, byteCount = await fetchSegment(
                    client,
                    cid=cid,
                    aid=aid,
                    segmentIndex=first + offset,
                    signParams=signParams,
                )
                if onProgress is not None:
                    onProgress(offset + 1, 0, byteCount)
                if segClosed:
                    return []
                if byteCount == 0:
                    break
                rawItems.extend(items)
    finally:
        client.close()

    return buildFilteredItems(rawItems, startTime=startTime, endTime=endTime)


def toXmlText(text: str) -> str:
    return html.escape(XML_INVALID_RE.sub("", text), quote=True)


def toXml(items: Sequence[DanmakuItem], *, cid: int) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<i>",
        "    <chatserver>chat.bilibili.com</chatserver>",
        f"    <chatid>{cid}</chatid>",
        "    <mission>0</mission>",
        f"    <maxlimit>{max(len(items), 1500)}</maxlimit>",
        f"    <state>{0 if items else 1}</state>",
        "    <real_name>0</real_name>",
        "    <source>k-v</source>",
    ]
    for item in items:
        idText = item.idStr or (str(item.id) if item.id else "0")
        pAttr = (
            f"{item.progressMs / 1000:.5f},{item.mode},{item.fontsize},"
            f"{item.color},{item.ctime},{item.pool},"
            f"{toXmlText(item.midHash)},{toXmlText(idText)},{item.weight}"
        )
        lines.append(f'    <d p="{pAttr}">{toXmlText(item.content)}</d>')
    lines.append("</i>")
    return "\n".join(lines) + "\n"


def toAssTime(ms: int) -> str:
    totalCs = max(0, ms // 10)
    cs = totalCs % 100
    totalSec = totalCs // 100
    seconds = totalSec % 60
    minutes = (totalSec // 60) % 60
    hours = totalSec // 3600
    return f"{hours}:{minutes:02d}:{seconds:02d}.{cs:02d}"


def toAssText(text: str) -> str:
    cleaned = ASS_CONTROL_RE.sub("", text).replace("\r\n", "\n").replace("\r", "\n")
    return (
        cleaned.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", "\\N")
    )


def toTextWidth(text: str, fontPx: int) -> int:
    maxUnits = 0.0
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        units = sum(0.55 if ord(ch) < 128 else 1.0 for ch in line)
        if units > maxUnits:
            maxUnits = units
    return max(fontPx, math.ceil(maxUnits * fontPx) + 4)


def pickTrack(readyAt: Sequence[float], startSec: float, span: int) -> int:
    span = max(1, min(span, len(readyAt)))
    bestSlot = 0
    bestReady = math.inf
    for slot in range(len(readyAt) - span + 1):
        slotReady = max(readyAt[slot:slot + span])
        if startSec >= slotReady:
            return slot
        if slotReady < bestReady:
            bestReady = slotReady
            bestSlot = slot
    return bestSlot


def buildStyleOverrides(color: int, fontPx: int) -> str:
    tags: list[str] = []
    if fontPx != BASE_FONT_SIZE:
        tags.append(f"\\fs{fontPx}")
    rgb = color & 0xFFFFFF
    if rgb != 0xFFFFFF:
        r = (rgb >> 16) & 0xFF
        g = (rgb >> 8) & 0xFF
        b = rgb & 0xFF
        tags.append(f"\\c&H{b:02X}{g:02X}{r:02X}&")
        if 0.299 * r + 0.587 * g + 0.114 * b < 32:
            tags.append("\\3c&HFFFFFF&")
    return "".join(tags)


def toAss(
    items: Sequence[DanmakuItem],
    *,
    width: int = 1920,
    height: int = 1080,
    rotate: int = 0,
    title: str = "",
) -> str:
    if rotate in {1, 3}:
        width, height = height, width
    if width <= 0 or height <= 0:
        playResX, playResY = 1920, 1080
    elif width >= height:
        playResX, playResY = max(1, round(width * 1080 / height)), 1080
    else:
        playResX, playResY = 1080, max(1, round(height * 1080 / width))

    safeTitle = ASS_CONTROL_RE.sub("", title).replace("\r", " ").replace("\n", " ").strip() or "Danmaku"
    lines = [
        "[Script Info]",
        f"Title: {safeTitle}",
        "ScriptType: v4.00+",
        f"PlayResX: {playResX}",
        f"PlayResY: {playResY}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Danmaku,Microsoft YaHei,{BASE_FONT_SIZE},&H33FFFFFF,&H33FFFFFF,&H33000000,&H33000000,1,0,0,0,100,100,0,0,1,1.5,0,7,0,0,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    numSlots = max(1, (int(playResY * 0.75) - TRACK_MARGIN_Y) // TRACK_SLOT_HEIGHT)
    rtlTracks: list[tuple[float, float]] = [(0.0, 0.0)] * numSlots
    ltrTracks: list[tuple[float, float]] = [(0.0, 0.0)] * numSlots
    topTracks: list[float] = [0.0] * numSlots
    bottomTracks: list[float] = [0.0] * numSlots

    for item in items:
        if item.mode not in {1, 2, 3, 4, 5, 6}:
            continue
        fontPx = max(18, round((item.fontsize or 25) * 1.5))
        span = max(1, min(numSlots, (fontPx + 6 + TRACK_SLOT_HEIGHT - 1) // TRACK_SLOT_HEIGHT))
        textWidth = toTextWidth(item.content, fontPx)
        startSec = item.progressMs / 1000.0
        styleTags = buildStyleOverrides(item.color, fontPx)
        escapedText = toAssText(item.content)

        if item.mode in {1, 2, 3, 6}:
            endSec = startSec + SCROLL_DURATION
            tracks = ltrTracks if item.mode == 6 else rtlTracks
            leadTime = playResX * SCROLL_DURATION / (playResX + textWidth)
            readyAt = [max(0.0, tc, end - leadTime) for tc, end in tracks]
            slot = pickTrack(readyAt, startSec, span)
            tailClear = startSec + textWidth * SCROLL_DURATION / (playResX + textWidth)
            tracks[slot:slot + span] = [(tailClear, endSec)] * span
            y = TRACK_MARGIN_Y + slot * TRACK_SLOT_HEIGHT
            x1, x2 = (-textWidth, playResX) if item.mode == 6 else (playResX, -textWidth)
            motionTag = f"\\move({x1},{y},{x2},{y})"
            layer = 0
        else:
            endSec = startSec + FIXED_DURATION
            fixedTracks = topTracks if item.mode == 5 else bottomTracks
            slot = pickTrack(fixedTracks, startSec, span)
            fixedTracks[slot:slot + span] = [endSec] * span
            if item.mode == 5:
                y = TRACK_MARGIN_Y + slot * TRACK_SLOT_HEIGHT
                align = 8
            else:
                y = playResY - TRACK_MARGIN_Y - slot * TRACK_SLOT_HEIGHT
                align = 2
            motionTag = f"\\an{align}\\pos({playResX // 2},{y})"
            layer = 1

        startText = toAssTime(item.progressMs)
        endText = toAssTime(round(endSec * 1000))
        lines.append(
            f"Dialogue: {layer},{startText},{endText},Danmaku,,0,0,0,,{{{motionTag}{styleTags}}}{escapedText}"
        )

    return "\n".join(lines) + "\n"
