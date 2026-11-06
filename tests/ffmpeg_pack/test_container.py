from __future__ import annotations

from pathlib import Path
from struct import pack, unpack_from

import pytest

from ffmpeg_pack.container import (
    buildBox,
    buildMp4SegmentRange,
    buildSegmentRange,
    findMoovRange,
    parseBoxList,
    parseContainerIndex,
    parseMp4Boxes,
)

SAMPLE = Path(__file__).parents[1] / "samples" / "youtube_video_header.bin"


def buildTrackBox(
    handlerType: bytes,
    timescale: int,
    sampleCount: int,
    sampleDelta: int,
    sampleSize: int,
    chunkOffsets: list[int],
    syncSamples: list[int] | None = None,
) -> bytes:
    duration = sampleCount * sampleDelta
    tkhdPayload = bytearray(84)
    tkhdPayload[0:4] = b"\x00\x00\x00\x03"
    tkhdPayload[12:16] = pack(">I", 1 if handlerType == b"vide" else 2)
    tkhdPayload[20:24] = pack(">I", duration)
    tkhd = buildBox(b"tkhd", bytes(tkhdPayload))

    mdhdPayload = bytearray(24)
    mdhdPayload[12:16] = pack(">I", timescale)
    mdhdPayload[16:20] = pack(">I", duration)
    mdhd = buildBox(b"mdhd", bytes(mdhdPayload))

    hdlr = buildBox(b"hdlr", b"\x00" * 8 + handlerType + b"\x00" * 12 + b"Handler\x00")
    stsd = buildBox(b"stsd", b"\x00" * 4 + pack(">I", 1) + buildBox(b"avc1", b"\x00" * 78))
    stts = buildBox(b"stts", b"\x00" * 4 + pack(">III", 1, sampleCount, sampleDelta))
    stsc = buildBox(b"stsc", b"\x00" * 4 + pack(">IIII", 1, 1, 1, 1))
    stsz = buildBox(b"stsz", b"\x00" * 4 + pack(">II", sampleSize, sampleCount))
    stco = buildBox(b"stco", b"\x00" * 4 + pack(">I", len(chunkOffsets)) + b"".join(pack(">I", o) for o in chunkOffsets))

    stblChildren = [stsd, stts]
    if syncSamples is not None:
        stss = buildBox(
            b"stss",
            b"\x00" * 4 + pack(">I", len(syncSamples)) + b"".join(pack(">I", s) for s in syncSamples),
        )
        stblChildren.append(stss)
    stblChildren.extend([stsc, stsz, stco])
    stbl = buildBox(b"stbl", b"".join(stblChildren))
    minf = buildBox(b"minf", stbl)
    mdia = buildBox(b"mdia", mdhd + hdlr + minf)
    return buildBox(b"trak", tkhd + mdia)


def buildProgressiveMp4(*, faststart: bool = True, paddingSize: int = 0) -> bytes:
    ftyp = buildBox(b"ftyp", b"isom\x00\x00\x02\x00isomiso2mp41")
    sampleCount = 10
    videoSampleSize = 1000
    audioSampleSize = 500
    stride = videoSampleSize + audioSampleSize

    chunks = bytearray()
    for i in range(sampleCount):
        vTag = f"VID_{i:02d}_".encode()
        aTag = f"AUD_{i:02d}_".encode()
        chunks.extend(vTag + bytes([i]) * (videoSampleSize - len(vTag)))
        chunks.extend(aTag + bytes([i]) * (audioSampleSize - len(aTag)))
    if paddingSize > 0:
        chunks.extend(b"\x00" * paddingSize)
    mdat = buildBox(b"mdat", bytes(chunks))

    mvhdPayload = bytearray(100)
    mvhdPayload[12:16] = pack(">I", 1000)
    mvhdPayload[16:20] = pack(">I", sampleCount * 1000)
    mvhd = buildBox(b"mvhd", bytes(mvhdPayload))

    def makeMoov(mdatDataStart: int) -> bytes:
        vOffsets = [mdatDataStart + i * stride for i in range(sampleCount)]
        aOffsets = [mdatDataStart + i * stride + videoSampleSize for i in range(sampleCount)]
        vTrak = buildTrackBox(b"vide", 1000, sampleCount, 1000, videoSampleSize, vOffsets, [1, 3, 5, 7, 9])
        aTrak = buildTrackBox(b"soun", 1000, sampleCount, 1000, audioSampleSize, aOffsets, None)
        return buildBox(b"moov", mvhd + vTrak + aTrak)

    if faststart:
        dummyMoov = makeMoov(0)
        mdatDataStart = len(ftyp) + len(dummyMoov) + 8
        moov = makeMoov(mdatDataStart)
        return ftyp + moov + mdat
    else:
        mdatDataStart = len(ftyp) + 8
        moov = makeMoov(mdatDataStart)
        return ftyp + mdat + moov


@pytest.fixture
def videoHeader() -> bytes:
    return SAMPLE.read_bytes()


def test_build_header_from_ftyp_and_moov(videoHeader):
    seg = buildMp4SegmentRange(videoHeader, 60, 65)
    assert seg.patchedHeader[:4] == b"\x00\x00\x00\x1c"  # ftyp size=28
    assert seg.patchedHeader[4:8] == b"ftyp"
    boxes = parseMp4Boxes(videoHeader)
    moovEnd = boxes["moov"][0] + boxes["moov"][1]
    assert len(seg.patchedHeader) == moovEnd


def test_build_range_for_whole_video(videoHeader):
    seg = buildMp4SegmentRange(videoHeader, 0, 731)
    boxes = parseMp4Boxes(videoHeader)
    dataStart = boxes["sidx"][0] + boxes["sidx"][1]
    assert seg.segStart == dataStart
    assert seg.segEnd == 6744153


def test_build_range_for_first_seconds(videoHeader):
    seg = buildMp4SegmentRange(videoHeader, 0, 5)
    boxes = parseMp4Boxes(videoHeader)
    dataStart = boxes["sidx"][0] + boxes["sidx"][1]
    assert seg.segStart == dataStart
    assert seg.segEnd - seg.segStart < 100_000


def test_build_range_for_last_seconds(videoHeader):
    seg = buildMp4SegmentRange(videoHeader, 726, 731)
    assert seg.segEnd == 6744153
    assert seg.segEnd - seg.segStart < 100_000


def test_parse_progressive_mp4_head_moov():
    mp4 = buildProgressiveMp4(faststart=True)
    head = mp4[:65536]
    assert findMoovRange(head, len(mp4)) == (b"", 0, 0)

    index = parseContainerIndex(head)
    assert index is not None
    assert index.format == "mp4"
    assert index.duration == pytest.approx(10.0)

    seg = buildSegmentRange(head, index, 3.0, 6.0)
    assert seg is not None
    assert seg.segStartTime == pytest.approx(2.0)

    assembled = seg.patchedHeader + mp4[seg.segStart:seg.segEnd]
    topBoxes = {boxType: (bodyStart, boxEnd) for boxType, _, _, bodyStart, boxEnd in parseBoxList(assembled)}
    assert b"ftyp" in topBoxes
    assert b"moov" in topBoxes
    assert b"mdat" in topBoxes

    moovStart, moovEnd = topBoxes[b"moov"]
    traks = [b for b in parseBoxList(assembled, moovStart, moovEnd) if b[0] == b"trak"]
    mdia = next(b for b in parseBoxList(assembled, traks[0][3], traks[0][4]) if b[0] == b"mdia")
    minf = next(b for b in parseBoxList(assembled, mdia[3], mdia[4]) if b[0] == b"minf")
    stbl = next(b for b in parseBoxList(assembled, minf[3], minf[4]) if b[0] == b"stbl")
    stco = next(b for b in parseBoxList(assembled, stbl[3], stbl[4]) if b[0] == b"stco")
    firstChunkOffset = unpack_from(">I", assembled, stco[3] + 8)[0]
    assert assembled[firstChunkOffset:firstChunkOffset + 7] == b"VID_02_"


def test_parse_progressive_mp4_tail_moov():
    mp4 = buildProgressiveMp4(faststart=False, paddingSize=80_000)
    head = mp4[:65536]
    moovRange = findMoovRange(head, len(mp4))
    assert moovRange is not None
    prefix, offset, length = moovRange
    assert prefix[:8] == mp4[:8]
    assert offset > 65536
    assert offset + length == len(mp4)

    headerData = prefix + mp4[offset:offset + length]
    index = parseContainerIndex(headerData)
    assert index is not None
    assert index.format == "mp4"
    assert index.duration == pytest.approx(10.0)

    seg = buildSegmentRange(headerData, index, 4.0, 7.0)
    assert seg is not None
    assert seg.segStartTime == pytest.approx(4.0)
    assembled = seg.patchedHeader + mp4[seg.segStart:seg.segEnd]
    assert b"VID_04_" in assembled
    assert b"VID_00_" not in assembled[len(seg.patchedHeader):]
