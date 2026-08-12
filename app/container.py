from __future__ import annotations

from collections import namedtuple
from struct import pack, unpack_from

SegmentRange = namedtuple("SegmentRange", ["patchedHeader", "segStart", "segEnd", "segStartTime", "segDuration"])


def buildMp4SegmentRange(headerData: bytes, startTime: int, endTime: int) -> SegmentRange:
    boxes = parseMp4Boxes(headerData)
    moovOffset, moovSize = boxes.get("moov", (0, 0))
    sidxOffset, sidxSize = boxes.get("sidx", (0, 0))
    if not sidxSize:
        raise ValueError("sidx box not found")

    dataStart = sidxOffset + sidxSize
    references = parseSidx(headerData, sidxOffset, sidxSize)

    segStart, segEnd, segStartTime, segDuration = buildByteRange(references, dataStart, startTime, endTime)

    # ftyp + moov only — strip sidx (its byte offsets are invalid for the partial file;
    # fMP4 moof boxes are self-describing, ffmpeg reads them sequentially)
    initEnd = moovOffset + moovSize
    patched = bytearray(headerData[:initEnd])
    moovData = headerData[moovOffset:initEnd]
    patchChunkOffsets(patched, moovOffset, moovData, 0, len(moovData), initEnd - segStart)
    patchMoovDuration(patched, moovOffset, moovData, segDuration)

    return SegmentRange(bytes(patched), segStart, segEnd, segStartTime, segDuration)


def buildWebmSegmentRange(headerData: bytes, startTime: int, endTime: int) -> SegmentRange:
    segmentDataOffset, cues = parseWebmCues(headerData)

    startMs = startTime * 1000
    endMs = endTime * 1000

    segStart = segmentDataOffset + cues[-1][1]
    segEnd = segStart
    segStartTime = 0.0
    segEndTime = 0.0
    for i, (cueTime, cuePos) in enumerate(cues):
        absPos = segmentDataOffset + cuePos
        if cueTime <= startMs:
            segStart = absPos
            segStartTime = cueTime / 1000.0
        if cueTime <= endMs:
            nextPos = (segmentDataOffset + cues[i + 1][1]) if i + 1 < len(cues) else None
            segEnd = nextPos if nextPos else absPos
            nextTime = cues[i + 1][0] / 1000.0 if i + 1 < len(cues) else cueTime / 1000.0
            segEndTime = nextTime

    if segEnd <= segStart:
        segEnd = len(headerData)

    headerSize = segStart
    segDuration = segEndTime - segStartTime if segEndTime > segStartTime else 0.0
    return SegmentRange(headerData[:headerSize], segStart, segEnd, segStartTime, segDuration)


# ── MP4 box parsing ─────────────────────────────────────────────


def parseMp4Boxes(data: bytes) -> dict[str, tuple[int, int]]:
    boxes: dict[str, tuple[int, int]] = {}
    pos = 0
    while pos + 8 <= len(data):
        size = unpack_from(">I", data, pos)[0]
        boxType = data[pos + 4:pos + 8].decode("ascii", errors="replace")
        if size < 8:
            break
        boxes[boxType] = (pos, size)
        pos += size
    return boxes


def parseSidx(data: bytes, offset: int, size: int) -> list[tuple[int, int]]:
    pos = offset + 8
    version = data[pos]
    pos += 4  # version + flags
    pos += 4  # reference_ID
    timescale = unpack_from(">I", data, pos)[0]
    pos += 4

    if version == 0:
        pos += 8  # earliest_presentation_time + first_offset (32-bit each)
    else:
        pos += 16  # 64-bit each

    pos += 2  # reserved
    referenceCount = unpack_from(">H", data, pos)[0]
    pos += 2

    references: list[tuple[int, int]] = []
    for _ in range(referenceCount):
        field1 = unpack_from(">I", data, pos)[0]
        referencedSize = field1 & 0x7FFFFFFF
        subsegmentDuration = unpack_from(">I", data, pos + 4)[0]
        pos += 12  # referenced_size + subsegment_duration + SAP fields
        durationSec = subsegmentDuration / timescale
        references.append((durationSec, referencedSize))

    return references


def buildByteRange(
    references: list[tuple[float, int]], headerSize: int, startTime: int, endTime: int
) -> tuple[int, int, float, float]:
    bytePos = headerSize
    timeSec = 0.0
    segStart = headerSize
    segEnd = headerSize
    segStartTime = 0.0
    segEndTime = 0.0
    foundStart = False

    for duration, size in references:
        refEnd = timeSec + duration
        if not foundStart and refEnd > startTime:
            segStart = bytePos
            segStartTime = timeSec
            foundStart = True
        bytePos += size
        if refEnd >= endTime:
            segEnd = bytePos
            segEndTime = refEnd
            break
        if foundStart:
            segEnd = bytePos
            segEndTime = refEnd
        timeSec = refEnd

    if segEnd <= segStart:
        segEnd = bytePos

    return segStart, segEnd, segStartTime, segEndTime - segStartTime


def patchMoovDuration(header: bytearray, moovOffset: int, moovData: bytes, segDuration: float) -> None:
    movieTimescale = 0
    pos = 8
    end = len(moovData)
    while pos + 8 <= end:
        size = unpack_from(">I", moovData, pos)[0]
        boxType = moovData[pos + 4:pos + 8]
        if size < 8 or pos + size > end:
            break
        if boxType == b"mvhd":
            version = moovData[pos + 8]
            movieTimescale = unpack_from(">I", moovData, pos + (20 if version == 0 else 28))[0]
            newDur = int(segDuration * movieTimescale) + movieTimescale
            if version == 0:
                absOff = moovOffset + pos + 24
                header[absOff:absOff + 4] = pack(">I", newDur)
            else:
                absOff = moovOffset + pos + 32
                header[absOff:absOff + 8] = pack(">q", newDur)
            break
        pos += size

    if not movieTimescale:
        return

    pos = 8
    while pos + 8 <= end:
        size = unpack_from(">I", moovData, pos)[0]
        boxType = moovData[pos + 4:pos + 8]
        if size < 8 or pos + size > end:
            break
        if boxType == b"trak":
            patchTrackDuration(header, moovOffset, moovData, pos + 8, pos + size, segDuration, movieTimescale)
        pos += size


def patchTrackDuration(
    header: bytearray, moovOffset: int, data: bytes, start: int, end: int,
    segDuration: float, movieTimescale: int,
) -> None:
    pos = start
    while pos + 8 <= end:
        size = unpack_from(">I", data, pos)[0]
        boxType = data[pos + 4:pos + 8]
        if size < 8 or pos + size > end:
            break
        if boxType == b"tkhd":
            version = data[pos + 8]
            newDur = int(segDuration * movieTimescale) + movieTimescale
            if version == 0:
                absOff = moovOffset + pos + 28
                header[absOff:absOff + 4] = pack(">I", newDur)
            else:
                absOff = moovOffset + pos + 36
                header[absOff:absOff + 8] = pack(">q", newDur)
        elif boxType == b"mdia":
            patchMdhdDuration(header, moovOffset, data, pos + 8, pos + size, segDuration)
        pos += size


def patchMdhdDuration(
    header: bytearray, moovOffset: int, data: bytes, start: int, end: int, segDuration: float,
) -> None:
    pos = start
    while pos + 8 <= end:
        size = unpack_from(">I", data, pos)[0]
        boxType = data[pos + 4:pos + 8]
        if size < 8 or pos + size > end:
            break
        if boxType == b"mdhd":
            version = data[pos + 8]
            if version == 0:
                timescale = unpack_from(">I", data, pos + 20)[0]
                newDur = int(segDuration * timescale) + timescale
                absOff = moovOffset + pos + 24
                header[absOff:absOff + 4] = pack(">I", newDur)
            else:
                timescale = unpack_from(">I", data, pos + 28)[0]
                newDur = int(segDuration * timescale) + timescale
                absOff = moovOffset + pos + 32
                header[absOff:absOff + 8] = pack(">q", newDur)
            break
        pos += size


def patchChunkOffsets(
    header: bytearray, baseOffset: int, data: bytes, start: int, end: int, delta: int
) -> None:
    CONTAINER_BOXES = {b"moov", b"trak", b"mdia", b"minf", b"stbl"}
    pos = start
    while pos + 8 <= end:
        size = unpack_from(">I", data, pos)[0]
        boxType = data[pos + 4:pos + 8]
        if size < 8 or pos + size > end:
            break
        if boxType in CONTAINER_BOXES:
            patchChunkOffsets(header, baseOffset, data, pos + 8, pos + size, delta)
        elif boxType == b"stco":
            patchOffsetEntries(header, baseOffset + pos, data, pos, size, delta, 4)
        elif boxType == b"co64":
            patchOffsetEntries(header, baseOffset + pos, data, pos, size, delta, 8)
        pos += size


def patchOffsetEntries(
    header: bytearray, absOffset: int, data: bytes, pos: int, size: int,
    delta: int, entrySize: int,
) -> None:
    boxHeaderSize = 12  # box header (8) + version (1) + flags (3)
    entryCount = unpack_from(">I", data, pos + boxHeaderSize)[0]
    entriesStart = pos + boxHeaderSize + 4

    fmt = ">I" if entrySize == 4 else ">q"

    for i in range(entryCount):
        off = entriesStart + i * entrySize
        if off + entrySize > pos + size:
            break
        value = unpack_from(fmt, data, off)[0]
        newValue = value + delta
        if entrySize == 4:
            newValue = newValue & 0xFFFFFFFF
        writeOff = absOffset + (off - pos)
        header[writeOff:writeOff + entrySize] = pack(fmt, newValue)


# ── WebM / EBML parsing ─────────────────────────────────────────


def parseEbmlVarInt(data: bytes, pos: int) -> tuple[int, int]:
    if pos >= len(data):
        raise ValueError("unexpected end of EBML data")
    first = data[pos]
    if first == 0:
        raise ValueError("invalid EBML varint")
    length = 1
    mask = 0x80
    while length <= 8 and not (first & mask):
        length += 1
        mask >>= 1
    value = first & (mask - 1)
    for i in range(1, length):
        if pos + i >= len(data):
            raise ValueError("unexpected end of EBML data")
        value = (value << 8) | data[pos + i]
    return value, pos + length


def parseEbmlElementId(data: bytes, pos: int) -> tuple[int, int]:
    if pos >= len(data):
        raise ValueError("unexpected end of EBML data")
    first = data[pos]
    if first == 0:
        raise ValueError("invalid EBML element ID")
    length = 1
    mask = 0x80
    while length <= 4 and not (first & mask):
        length += 1
        mask >>= 1
    value = 0
    for i in range(length):
        if pos + i >= len(data):
            raise ValueError("unexpected end of EBML data")
        value = (value << 8) | data[pos + i]
    return value, pos + length


def parseEbmlUint(data: bytes, pos: int, size: int) -> int:
    value = 0
    for i in range(size):
        value = (value << 8) | data[pos + i]
    return value


EBML_ID_SEGMENT = 0x18538067
EBML_ID_CUES = 0x1C53BB6B
EBML_ID_CUE_POINT = 0xBB
EBML_ID_CUE_TIME = 0xB3
EBML_ID_CUE_TRACK_POSITIONS = 0xB7
EBML_ID_CUE_CLUSTER_POSITION = 0xF1

EBML_MASTER_IDS = {EBML_ID_SEGMENT, EBML_ID_CUES, EBML_ID_CUE_POINT, EBML_ID_CUE_TRACK_POSITIONS}


def parseWebmCues(data: bytes) -> tuple[int, list[tuple[int, int]]]:
    pos = 0

    elemId, pos = parseEbmlElementId(data, pos)
    elemSize, pos = parseEbmlVarInt(data, pos)
    pos += elemSize

    elemId, pos = parseEbmlElementId(data, pos)
    if elemId != EBML_ID_SEGMENT:
        raise ValueError("expected Segment element")
    _, pos = parseEbmlVarInt(data, pos)
    segmentDataOffset = pos

    cues: list[tuple[int, int]] = []
    limit = min(len(data), segmentDataOffset + 65536)

    while pos < limit:
        try:
            elemId, nextPos = parseEbmlElementId(data, pos)
            elemSize, nextPos = parseEbmlVarInt(data, nextPos)
        except ValueError:
            break

        if elemId == EBML_ID_CUES:
            cues = parseCuesElement(data, nextPos, nextPos + elemSize)
            break
        elif elemId in EBML_MASTER_IDS:
            pos = nextPos
        else:
            pos = nextPos + elemSize

    return segmentDataOffset, cues


def parseCuesElement(data: bytes, start: int, end: int) -> list[tuple[int, int]]:
    cues: list[tuple[int, int]] = []
    pos = start
    while pos < end:
        try:
            elemId, nextPos = parseEbmlElementId(data, pos)
            elemSize, nextPos = parseEbmlVarInt(data, nextPos)
        except ValueError:
            break
        if elemId == EBML_ID_CUE_POINT:
            cueTime, cuePos = parseCuePoint(data, nextPos, nextPos + elemSize)
            if cueTime >= 0 and cuePos >= 0:
                cues.append((cueTime, cuePos))
        pos = nextPos + elemSize
    return cues


def parseCuePoint(data: bytes, start: int, end: int) -> tuple[int, int]:
    cueTime = -1
    clusterPos = -1
    pos = start
    while pos < end:
        try:
            elemId, nextPos = parseEbmlElementId(data, pos)
            elemSize, nextPos = parseEbmlVarInt(data, nextPos)
        except ValueError:
            break
        if elemId == EBML_ID_CUE_TIME:
            cueTime = parseEbmlUint(data, nextPos, elemSize)
        elif elemId == EBML_ID_CUE_TRACK_POSITIONS:
            clusterPos = parseCueTrackPositions(data, nextPos, nextPos + elemSize)
        pos = nextPos + elemSize
    return cueTime, clusterPos


def parseCueTrackPositions(data: bytes, start: int, end: int) -> int:
    pos = start
    while pos < end:
        try:
            elemId, nextPos = parseEbmlElementId(data, pos)
            elemSize, nextPos = parseEbmlVarInt(data, nextPos)
        except ValueError:
            break
        if elemId == EBML_ID_CUE_CLUSTER_POSITION:
            return parseEbmlUint(data, nextPos, elemSize)
        pos = nextPos + elemSize
    return -1
