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


def buildFragmentedMp4Header(segmentCount: int, segmentSize: int = 10_000, segmentDuration: int = 2000) -> bytes:
    ftyp = buildBox(b"ftyp", b"iso5\x00\x00\x02\x00iso5iso6mp41")
    mvex = buildBox(b"mvex", buildBox(b"trex", b"\x00" * 24))
    moov = buildBox(b"moov", buildBox(b"mvhd", b"\x00" * 100) + mvex)

    sidxBody = bytearray()
    sidxBody.extend(b"\x00\x00\x00\x00")  # version 0, flags 0
    sidxBody.extend(pack(">II", 1, 1000))  # reference_ID=1, timescale=1000
    sidxBody.extend(pack(">II", 0, 0))  # earliest_presentation_time=0, first_offset=0
    sidxBody.extend(pack(">HH", 0, segmentCount))
    for _ in range(segmentCount):
        sidxBody.extend(pack(">III", segmentSize, segmentDuration, 0x90000000))
    sidx = buildBox(b"sidx", bytes(sidxBody))
    return ftyp + moov + sidx + b"\x00\x00\x00\x18moof"


def buildEbmlId(ebmlId: int) -> bytes:
    for length in (1, 2, 3, 4):
        if ebmlId < (1 << (8 * length)):
            return ebmlId.to_bytes(length, "big")
    raise ValueError(ebmlId)


def buildVintSize(size: int) -> bytes:
    for length in range(1, 9):
        maxVal = (1 << (7 * length)) - 2
        if size <= maxVal:
            val = size | (1 << (7 * length))
            return val.to_bytes(length, "big")
    raise ValueError(size)


def buildUintElement(ebmlId: int, value: int) -> bytes:
    length = max(1, (value.bit_length() + 7) // 8)
    payload = value.to_bytes(length, "big")
    return buildEbmlId(ebmlId) + buildVintSize(len(payload)) + payload


def buildWebmHeaderWithCues(cueCount: int, clusterStride: int = 50_000, cueIntervalMs: int = 2000) -> bytes:
    ebml = buildEbmlId(0x1A45DFA3) + buildVintSize(4) + b"\x42\x86\x81\x01"
    timecodeScale = buildUintElement(0x2AD7B1, 1_000_000)
    durationPayload = pack(">d", float(cueCount * cueIntervalMs))
    durationElem = buildEbmlId(0x4489) + buildVintSize(8) + durationPayload
    infoPayload = timecodeScale + durationElem
    info = buildEbmlId(0x1549A966) + buildVintSize(len(infoPayload)) + infoPayload

    cuePoints = bytearray()
    for i in range(cueCount):
        cueTime = buildUintElement(0xB3, i * cueIntervalMs)
        cueClusterPos = buildUintElement(0xF1, 100_000 + i * clusterStride)
        cueTrackPos = buildEbmlId(0xB7) + buildVintSize(len(cueClusterPos)) + cueClusterPos
        pointPayload = cueTime + cueTrackPos
        cuePoints.extend(buildEbmlId(0xBB) + buildVintSize(len(pointPayload)) + pointPayload)
    cues = buildEbmlId(0x1C53BB6B) + buildVintSize(len(cuePoints)) + bytes(cuePoints)
    clusterHead = buildEbmlId(0x1F43B675) + buildVintSize(clusterStride)
    segmentPayload = info + cues + clusterHead
    segment = buildEbmlId(0x18538067) + b"\x01\xff\xff\xff\xff\xff\xff\xff" + segmentPayload
    return ebml + segment


def test_parse_fragmented_mp4_large_sidx_beyond_head_probe():
    header = buildFragmentedMp4Header(segmentCount=6000, segmentSize=10_000, segmentDuration=2000)
    assert len(header) > 65536
    totalSize = len(header) + 6000 * 10_000

    head = header[:65536]
    assert parseContainerIndex(head) is None

    moovRange = findMoovRange(head, totalSize)
    assert moovRange is not None
    prefix, offset, length = moovRange
    assert prefix == head
    assert offset == 65536
    assert offset + length == len(header) - 8  # right up to the end of sidx

    fullHeader = prefix + header[offset:offset + length]
    assert findMoovRange(fullHeader, totalSize) == (b"", 0, 0)

    index = parseContainerIndex(fullHeader)
    assert index is not None
    assert index.format == "fmp4"
    assert index.duration == pytest.approx(12000.0)

    seg = buildSegmentRange(fullHeader, index, 3600.0, 3660.0)
    assert seg is not None
    assert seg.segStartTime == pytest.approx(3600.0)
    assert seg.segEnd - seg.segStart == 30 * 10_000


def test_parse_webm_large_cues_beyond_head_probe():
    header = buildWebmHeaderWithCues(cueCount=5000, clusterStride=50_000, cueIntervalMs=2000)
    assert len(header) > 65536
    totalSize = len(header) + 5000 * 50_000

    head = header[:65536]
    assert parseContainerIndex(head) is None

    moovRange = findMoovRange(head, totalSize)
    assert moovRange is not None
    prefix, offset, length = moovRange
    assert prefix == head
    assert offset == 65536
    assert offset + length <= len(header)

    fullHeader = prefix + header[offset:offset + length]
    assert findMoovRange(fullHeader, totalSize) == (b"", 0, 0)

    index = parseContainerIndex(fullHeader)
    assert index is not None
    assert index.format == "webm"
    assert index.duration == pytest.approx(10000.0)

    seg = buildSegmentRange(fullHeader, index, 3600.0, 3660.0)
    assert seg is not None
    assert seg.segStartTime == pytest.approx(3600.0)
    assert seg.segEnd - seg.segStart == 31 * 50_000
