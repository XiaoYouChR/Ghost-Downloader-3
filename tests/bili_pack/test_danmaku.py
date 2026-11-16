from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest
from aiohttp import web

import bili_pack.danmaku as danmaku
from app.models.task import TaskError
from bili_pack.danmaku import (
    DanmakuItem,
    fetchDanmaku,
    parseSegment,
    toAss,
    toXml,
)


def encodeVarint(value: int) -> bytes:
    if value < 0:
        value &= 0xFFFFFFFFFFFFFFFF
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)


def encodeVarintField(fieldNum: int, value: int) -> bytes:
    return encodeVarint((fieldNum << 3) | 0) + encodeVarint(value)


def encodeBytesField(fieldNum: int, data: bytes) -> bytes:
    return encodeVarint((fieldNum << 3) | 2) + encodeVarint(len(data)) + data


def encodeElem(
    *,
    elemId: int = 0,
    progressMs: int = 0,
    mode: int = 1,
    fontsize: int = 25,
    color: int = 0xFFFFFF,
    midHash: str = "",
    content: str = "",
    ctime: int = 0,
    weight: int = 0,
    pool: int = 0,
    idStr: str = "",
) -> bytes:
    buf = bytearray()
    if elemId:
        buf.extend(encodeVarintField(1, elemId))
    if progressMs:
        buf.extend(encodeVarintField(2, progressMs))
    if mode:
        buf.extend(encodeVarintField(3, mode))
    if fontsize:
        buf.extend(encodeVarintField(4, fontsize))
    if color:
        buf.extend(encodeVarintField(5, color))
    if midHash:
        buf.extend(encodeBytesField(6, midHash.encode("utf-8")))
    if content:
        buf.extend(encodeBytesField(7, content.encode("utf-8")))
    if ctime:
        buf.extend(encodeVarintField(8, ctime))
    if weight:
        buf.extend(encodeVarintField(9, weight))
    if pool:
        buf.extend(encodeVarintField(11, pool))
    if idStr:
        buf.extend(encodeBytesField(12, idStr.encode("utf-8")))
    return bytes(buf)


def encodeSegment(elems: list[bytes], *, state: int = 0) -> bytes:
    buf = bytearray()
    for elem in elems:
        buf.extend(encodeBytesField(1, elem))
    if state:
        buf.extend(encodeVarintField(2, state))
    return bytes(buf)


def test_parse_segment_decodes_fields_and_black_default():
    raw = encodeSegment([
        encodeElem(
            elemId=101,
            progressMs=12345,
            mode=5,
            fontsize=36,
            color=0,
            midHash="abcd1234",
            content="黑色顶部弹幕",
            ctime=1700000000,
            weight=7,
            pool=1,
            idStr="101",
        ),
        encodeElem(
            elemId=102,
            progressMs=-500,
            color=0xFFFFFF,
            content="负时间白色",
        ),
        encodeElem(elemId=103, progressMs=100, content=""),
    ])

    items, isClosed = parseSegment(raw)

    assert isClosed is False
    assert len(items) == 2
    assert items[0] == DanmakuItem(
        id=101,
        progressMs=12345,
        mode=5,
        fontsize=36,
        color=0,
        midHash="abcd1234",
        content="黑色顶部弹幕",
        ctime=1700000000,
        weight=7,
        pool=1,
        idStr="101",
    )
    assert items[1].progressMs == 0
    assert items[1].color == 0xFFFFFF
    assert items[1].idStr == "102"


def test_parse_segment_handles_closed_and_truncated_bytes():
    closedRaw = encodeSegment([encodeElem(elemId=1, content="hello")], state=1)
    items, isClosed = parseSegment(closedRaw)
    assert isClosed is True
    assert len(items) == 1

    valid = encodeSegment([encodeElem(elemId=2, progressMs=1000, content="完整")])
    truncated = valid + encodeBytesField(1, encodeElem(elemId=3, content="截断"))[:-3]
    parsed, closedFlag = parseSegment(truncated)
    assert closedFlag is False
    assert [x.content for x in parsed] == ["完整"]


async def test_fetch_danmaku_dedupes_trims_and_skips_304(startServer, monkeypatch):
    seenSegments: list[int] = []

    async def handler(request: web.Request) -> web.Response:
        seg = int(request.query["segment_index"])
        seenSegments.append(seg)
        if seg == 1:
            return web.Response(body=encodeSegment([
                encodeElem(elemId=1, progressMs=10000, content="区间前"),
            ]))
        if seg == 2:
            return web.Response(body=encodeSegment([
                encodeElem(elemId=2, progressMs=360000, content="边界前"),
                encodeElem(elemId=3, progressMs=400000, content="中段A"),
                encodeElem(elemId=4, progressMs=500000, content="中段B"),
            ]))
        if seg == 3:
            return web.Response(body=encodeSegment([
                encodeElem(elemId=4, progressMs=500000, content="中段B重复"),
                encodeElem(elemId=5, progressMs=730000, content="区间后"),
            ]))
        return web.Response(status=304)

    baseUrl = await startServer(handler)
    monkeypatch.setattr(danmaku, "DANMAKU_SEG_API", baseUrl)

    items = await fetchDanmaku(
        cid=100,
        aid=200,
        duration=1200,
        startTime=390,
        endTime=725,
        signParams=lambda p: p,
    )
    assert sorted(seenSegments) == [2, 3]
    assert [(x.id, x.progressMs, x.content) for x in items] == [
        (3, 10000, "中段A"),
        (4, 110000, "中段B"),
    ]

    seenSegments.clear()
    probed = await fetchDanmaku(cid=100, duration=0, signParams=lambda p: p)
    assert seenSegments == [1, 2, 3, 4]
    assert [x.id for x in probed] == [1, 2, 3, 4, 5]


async def test_fetch_danmaku_raises_on_412_and_api_error(startServer, monkeypatch):
    mode = "412"

    async def handler(request: web.Request) -> web.Response:
        if mode == "412":
            return web.Response(status=412, text="blocked")
        return web.Response(
            text=json.dumps({"code": -400, "message": "参数错误"}),
            content_type="application/json",
        )

    baseUrl = await startServer(handler)
    monkeypatch.setattr(danmaku, "DANMAKU_SEG_API", baseUrl)

    with pytest.raises(TaskError, match="412"):
        await fetchDanmaku(cid=100, duration=60, signParams=lambda p: p)

    mode = "json_error"
    with pytest.raises(ValueError, match="参数错误"):
        await fetchDanmaku(cid=100, duration=60, signParams=lambda p: p)


def test_to_xml_escapes_and_handles_empty():
    items = [
        DanmakuItem(
            id=99,
            progressMs=1234,
            mode=1,
            fontsize=25,
            color=16777215,
            midHash="a1b2c3d4",
            content="A < B & C \"D\"\x00\x0b",
            ctime=1700000000,
            weight=6,
            pool=0,
            idStr="99",
        )
    ]
    xmlText = toXml(items, cid=12345)
    root = ET.fromstring(xmlText)
    assert root.tag == "i"
    assert root.findtext("chatid") == "12345"
    assert root.findtext("state") == "0"
    dNodes = root.findall("d")
    assert len(dNodes) == 1
    assert dNodes[0].attrib["p"] == "1.23400,1,25,16777215,1700000000,0,a1b2c3d4,99,6"
    assert dNodes[0].text == 'A < B & C "D"'

    emptyRoot = ET.fromstring(toXml([], cid=12345))
    assert emptyRoot.findtext("state") == "1"
    assert emptyRoot.findall("d") == []


def test_to_ass_normalizes_landscape_portrait_and_rotation():
    uhd = toAss([], width=3840, height=2160)
    assert "PlayResX: 1920\n" in uhd and "PlayResY: 1080\n" in uhd

    portrait = toAss([], width=1080, height=1920)
    assert "PlayResX: 1080\n" in portrait and "PlayResY: 1920\n" in portrait

    rotated = toAss([], width=1920, height=1080, rotate=1)
    assert "PlayResX: 1080\n" in rotated and "PlayResY: 1920\n" in rotated

    fallback = toAss([], width=0, height=0)
    assert "PlayResX: 1920\n" in fallback and "PlayResY: 1080\n" in fallback


def test_to_ass_formats_modes_colors_collisions_and_empty():
    items = [
        DanmakuItem(id=1, progressMs=1000, mode=1, fontsize=25, color=0xFFFFFF, content="第一条滚动"),
        DanmakuItem(id=2, progressMs=1000, mode=1, fontsize=25, color=0xFF0000, content="第二条滚动{含花括号}\n换行\\斜杠"),
        DanmakuItem(id=3, progressMs=1000, mode=5, fontsize=36, color=0x000000, content="黑色顶部"),
        DanmakuItem(id=4, progressMs=1000, mode=4, fontsize=25, color=0x00FF00, content="绿色底部"),
        DanmakuItem(id=5, progressMs=1000, mode=6, fontsize=25, color=0xFFFFFF, content="逆向弹幕"),
        DanmakuItem(id=6, progressMs=1000, mode=7, fontsize=25, color=0xFFFFFF, content="高级忽略"),
        DanmakuItem(id=7, progressMs=1000, mode=8, fontsize=25, color=0xFFFFFF, content="代码忽略"),
    ]
    assText = toAss(items, width=1920, height=1080, title="测试标题\n第二行")

    assert "Title: 测试标题 第二行\n" in assText
    assert "PlayResX: 1920\n" in assText
    assert "PlayResY: 1080\n" in assText

    dialogues = [line for line in assText.splitlines() if line.startswith("Dialogue: ")]
    assert len(dialogues) == 5
    assert "高级忽略" not in assText
    assert "代码忽略" not in assText

    # 同时间两条滚动弹幕应分配到不同 Y 轨道
    assert "\\move(1920,10," in dialogues[0]
    assert "\\move(1920,54," in dialogues[1]
    assert "\\c&H0000FF&" in dialogues[1]
    assert "\\{含花括号\\}\\N换行\\\\斜杠" in dialogues[1]

    # 黑色大字顶部弹幕附带白色描边
    assert "\\an8\\pos(960,10)\\fs54\\c&H000000&\\3c&HFFFFFF&" in dialogues[2]
    assert "\\an2\\pos(960,1070)\\c&H00FF00&" in dialogues[3]
    assert "\\move(-" in dialogues[4]

    portraitAss = toAss([], width=1920, height=1080, rotate=1, title="竖屏")
    assert "PlayResX: 1080\n" in portraitAss
    assert "PlayResY: 1920\n" in portraitAss
    assert "[Events]" in portraitAss
    assert "Dialogue:" not in portraitAss
