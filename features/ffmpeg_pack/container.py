from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from struct import pack, unpack_from

MAX_MOOV_SIZE = 16 << 20
TOP_LEVEL_MP4_BOXES = frozenset({
    b"ftyp", b"styp", b"moov", b"moof", b"mdat",
    b"free", b"skip", b"wide", b"pdin", b"sidx", b"uuid",
})


@dataclass(slots=True, frozen=True)
class TrackTable:
    trackIndex: int
    handlerType: bytes
    timescale: int
    duration: int
    stsdBox: bytes
    sampleDurations: tuple[int, ...]
    sampleCtsOffsets: tuple[int, ...] | None
    cttsVersion: int
    syncSamples: frozenset[int] | None
    sampleSizes: tuple[int, ...]
    sampleOffsets: tuple[int, ...]
    chunkSampleRanges: tuple[tuple[int, int, int], ...]


@dataclass(slots=True, frozen=True)
class ContainerIndex:
    format: str
    duration: float
    initEnd: int
    entries: tuple[tuple[float, int, int], ...]
    tracks: tuple[TrackTable, ...] = ()


@dataclass(slots=True, frozen=True)
class SegmentRange:
    patchedHeader: bytes
    segStart: int
    segEnd: int
    segStartTime: float
    segDuration: float


def buildTimeSuffix(startTime: float, endTime: float) -> str:
    startSec = max(0, int(startTime))
    endSec = max(0, int(endTime))
    if startSec == 0 and endSec == 0:
        return ""

    def toMinSec(sec: int) -> str:
        m, s = divmod(sec, 60)
        return f"{m:02d}m{s:02d}s"

    return f"[{toMinSec(startSec)}-{toMinSec(endSec)}]"


def findMoovRange(head: bytes, fileSize: int) -> tuple[bytes, int, int] | None:
    if len(head) < 8:
        return None
    firstType = head[4:8]
    if firstType not in TOP_LEVEL_MP4_BOXES:
        return None

    ftypBytes = b""
    moovSpan: tuple[int, int] | None = None
    sidxSpan: tuple[int, int] | None = None
    mdatEnd = 0
    total = fileSize if fileSize > 0 else len(head)

    pos = 0
    while pos + 8 <= len(head):
        size = unpack_from(">I", head, pos)[0]
        boxType = head[pos + 4:pos + 8]
        headerLen = 8
        if size == 1:
            if pos + 16 > len(head):
                break
            size = unpack_from(">Q", head, pos + 8)[0]
            headerLen = 16
        elif size == 0:
            size = total - pos
        if size < headerLen:
            break

        boxEnd = pos + size
        if boxType == b"ftyp" and boxEnd <= len(head):
            ftypBytes = head[pos:boxEnd]
        elif boxType == b"moov":
            moovSpan = (pos, size)
        elif boxType == b"sidx":
            sidxSpan = (pos, size)
        elif boxType == b"mdat" and moovSpan is None:
            mdatEnd = boxEnd

        if boxEnd > len(head):
            break
        pos = boxEnd

    if moovSpan is not None:
        moovPos, moovSize = moovSpan
        if sidxSpan is not None:
            sidxEnd = sidxSpan[0] + sidxSpan[1]
            if sidxEnd <= len(head):
                return b"", 0, 0
            if sidxEnd <= MAX_MOOV_SIZE and (fileSize <= 0 or sidxEnd <= fileSize):
                return b"", 0, sidxEnd
            return None
        if moovPos + moovSize <= len(head):
            return b"", 0, 0
        if moovSize > MAX_MOOV_SIZE or (fileSize > 0 and moovPos + moovSize > fileSize):
            return None
        return ftypBytes, moovPos, moovSize

    if mdatEnd > 0 and fileSize > mdatEnd:
        tailLen = fileSize - mdatEnd
        if tailLen <= MAX_MOOV_SIZE:
            return ftypBytes, mdatEnd, tailLen

    return None


def parseContainerIndex(data: bytes) -> ContainerIndex | None:
    if len(data) < 8:
        return None

    if data[:4] == b"\x1a\x45\xdf\xa3":
        try:
            segmentDataOffset, duration, cues = parseWebmHeader(data)
        except ValueError:
            return None
        if not cues or duration <= 0:
            return None
        entries: list[tuple[float, int, int]] = []
        for i, (cueTimeMs, cuePos) in enumerate(cues):
            absPos = segmentDataOffset + cuePos
            nextPos = (segmentDataOffset + cues[i + 1][1]) if i + 1 < len(cues) else max(absPos, len(data))
            entries.append((cueTimeMs / 1000.0, absPos, max(0, nextPos - absPos)))
        initEnd = entries[0][1] if entries else segmentDataOffset
        return ContainerIndex(
            format="webm",
            duration=duration,
            initEnd=initEnd,
            entries=tuple(entries),
        )

    boxes = parseMp4Boxes(data)
    moovOffset, moovSize = boxes.get("moov", (0, 0))
    if not moovSize or moovOffset + moovSize > len(data):
        return None

    sidxOffset, sidxSize = boxes.get("sidx", (0, 0))
    if sidxSize and sidxOffset + sidxSize <= len(data):
        try:
            references = parseSidx(data, sidxOffset, sidxSize)
        except Exception:
            references = []
        if references:
            initEnd = sidxOffset + sidxSize
            bytePos = initEnd
            timeSec = 0.0
            fmp4Entries: list[tuple[float, int, int]] = []
            for refDur, refSize in references:
                fmp4Entries.append((timeSec, bytePos, refSize))
                timeSec += refDur
                bytePos += refSize
            if timeSec <= 0:
                return None
            return ContainerIndex(
                format="fmp4",
                duration=timeSec,
                initEnd=initEnd,
                entries=tuple(fmp4Entries),
            )

    duration, tracks = parseProgressiveMoov(data, moovOffset, moovSize)
    if duration <= 0 or not tracks:
        return None

    ftypOffset, ftypSize = boxes.get("ftyp", (0, 0))
    initEnd = (ftypSize if ftypOffset == 0 else 0) + moovSize + 8
    return ContainerIndex(
        format="mp4",
        duration=duration,
        initEnd=initEnd,
        entries=(),
        tracks=tracks,
    )


def buildSegmentRange(
    data: bytes,
    index: ContainerIndex,
    startTime: float,
    endTime: float,
) -> SegmentRange | None:
    effectiveEnd = endTime if endTime > 0 else index.duration
    if startTime < 0 or effectiveEnd <= startTime:
        return None
    try:
        if index.format == "fmp4":
            return buildMp4SegmentRange(data, startTime, effectiveEnd)
        if index.format == "webm":
            return buildWebmSegmentRange(data, startTime, effectiveEnd)
        if index.format == "mp4":
            return buildProgressiveSegmentRange(data, index, startTime, effectiveEnd)
    except Exception:
        return None
    return None


def buildMp4SegmentRange(headerData: bytes, startTime: float, endTime: float) -> SegmentRange:
    boxes = parseMp4Boxes(headerData)
    moovOffset, moovSize = boxes.get("moov", (0, 0))
    sidxOffset, sidxSize = boxes.get("sidx", (0, 0))
    if not sidxSize:
        raise ValueError("sidx box not found")

    dataStart = sidxOffset + sidxSize
    references = parseSidx(headerData, sidxOffset, sidxSize)

    segStart, segEnd, segStartTime, segDuration = buildByteRange(references, dataStart, startTime, endTime)

    # ftyp + moov only -> strip sidx (its byte offsets are invalid for the partial file;
    # fMP4 moof boxes are self-describing, ffmpeg reads them sequentially)
    initEnd = moovOffset + moovSize
    patched = bytearray(headerData[:initEnd])
    moovData = headerData[moovOffset:initEnd]
    patchChunkOffsets(patched, moovOffset, moovData, 0, len(moovData), initEnd - segStart)
    patchMoovDuration(patched, moovOffset, moovData, segDuration)

    return SegmentRange(bytes(patched), segStart, segEnd, segStartTime, segDuration)


def buildWebmSegmentRange(headerData: bytes, startTime: float, endTime: float) -> SegmentRange:
    segmentDataOffset, _, cues = parseWebmHeader(headerData)
    if not cues:
        raise ValueError("WebM cues not found")

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


def parseBoxList(data: bytes, start: int = 0, end: int | None = None) -> list[tuple[bytes, int, int, int, int]]:
    if end is None:
        end = len(data)
    boxes: list[tuple[bytes, int, int, int, int]] = []
    pos = start
    while pos + 8 <= end:
        size = unpack_from(">I", data, pos)[0]
        boxType = data[pos + 4:pos + 8]
        headerLen = 8
        if size == 1:
            if pos + 16 > end:
                break
            size = unpack_from(">Q", data, pos + 8)[0]
            headerLen = 16
        elif size == 0:
            size = end - pos
        if size < headerLen or pos + size > end:
            break
        boxes.append((boxType, pos, size, pos + headerLen, pos + size))
        pos += size
    return boxes


def parseMp4Boxes(data: bytes) -> dict[str, tuple[int, int]]:
    boxes: dict[str, tuple[int, int]] = {}
    for boxType, pos, size, _, _ in parseBoxList(data):
        boxes[boxType.decode("ascii", errors="replace")] = (pos, size)
    return boxes


def buildBox(boxType: bytes, payload: bytes) -> bytes:
    return pack(">I4s", 8 + len(payload), boxType) + payload


def parseSidx(data: bytes, offset: int, size: int) -> list[tuple[float, int]]:
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

    references: list[tuple[float, int]] = []
    for _ in range(referenceCount):
        field1 = unpack_from(">I", data, pos)[0]
        referencedSize = field1 & 0x7FFFFFFF
        subsegmentDuration = unpack_from(">I", data, pos + 4)[0]
        pos += 12  # referenced_size + subsegment_duration + SAP fields
        durationSec = subsegmentDuration / timescale
        references.append((durationSec, referencedSize))

    return references


def buildByteRange(
    references: list[tuple[float, int]], headerSize: int, startTime: float, endTime: float
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


# ── Progressive MP4 (moov/stbl) parsing & patching ──────────────


def parseProgressiveMoov(data: bytes, moovOffset: int, moovSize: int) -> tuple[float, tuple[TrackTable, ...]]:
    movieDuration = 0.0
    tracks: list[TrackTable] = []
    trackIndex = 0
    for boxType, _, _, bodyStart, boxEnd in parseBoxList(data, moovOffset + 8, moovOffset + moovSize):
        if boxType == b"mvhd":
            version = data[bodyStart]
            if version == 0 and bodyStart + 20 <= boxEnd:
                ts = unpack_from(">I", data, bodyStart + 12)[0]
                dur = unpack_from(">I", data, bodyStart + 16)[0]
                if ts > 0:
                    movieDuration = dur / ts
            elif version == 1 and bodyStart + 28 <= boxEnd:
                ts = unpack_from(">I", data, bodyStart + 20)[0]
                dur = unpack_from(">Q", data, bodyStart + 24)[0]
                if ts > 0:
                    movieDuration = dur / ts
        elif boxType == b"trak":
            table = parseTrackBox(data, bodyStart, boxEnd, trackIndex)
            if table is not None:
                tracks.append(table)
            trackIndex += 1

    if movieDuration <= 0 and tracks:
        movieDuration = max((t.duration / t.timescale for t in tracks if t.timescale > 0), default=0.0)
    return movieDuration, tuple(tracks)


def parseTrackBox(data: bytes, start: int, end: int, trackIndex: int) -> TrackTable | None:
    for boxType, _, _, bodyStart, boxEnd in parseBoxList(data, start, end):
        if boxType == b"mdia":
            timescale = 0
            duration = 0
            handlerType = b""
            stblSpan: tuple[int, int] | None = None
            for subType, _, _, subStart, subEnd in parseBoxList(data, bodyStart, boxEnd):
                if subType == b"mdhd":
                    timescale, duration = parseMdhdBox(data, subStart, subEnd)
                elif subType == b"hdlr":
                    handlerType = parseHdlrBox(data, subStart, subEnd)
                elif subType == b"minf":
                    for minfType, _, _, minfStart, minfEnd in parseBoxList(data, subStart, subEnd):
                        if minfType == b"stbl":
                            stblSpan = (minfStart, minfEnd)
            if timescale > 0 and stblSpan is not None:
                return parseStblBox(
                    data, stblSpan[0], stblSpan[1],
                    trackIndex, handlerType, timescale, duration,
                )
    return None


def parseMdhdBox(data: bytes, bodyStart: int, bodyEnd: int) -> tuple[int, int]:
    if bodyStart + 4 > bodyEnd:
        return 0, 0
    version = data[bodyStart]
    if version == 0 and bodyStart + 20 <= bodyEnd:
        ts = unpack_from(">I", data, bodyStart + 12)[0]
        dur = unpack_from(">I", data, bodyStart + 16)[0]
        return ts, dur
    if version == 1 and bodyStart + 28 <= bodyEnd:
        ts = unpack_from(">I", data, bodyStart + 20)[0]
        dur = unpack_from(">Q", data, bodyStart + 24)[0]
        return ts, dur
    return 0, 0


def parseHdlrBox(data: bytes, bodyStart: int, bodyEnd: int) -> bytes:
    if bodyStart + 12 <= bodyEnd:
        return data[bodyStart + 8:bodyStart + 12]
    return b""


def parseStblBox(
    data: bytes,
    bodyStart: int,
    bodyEnd: int,
    trackIndex: int,
    handlerType: bytes,
    timescale: int,
    duration: int,
) -> TrackTable | None:
    stsdBox = b""
    sttsEntries: list[tuple[int, int]] = []
    cttsEntries: list[tuple[int, int]] = []
    cttsVersion = 0
    hasCtts = False
    syncSamples: set[int] | None = None
    stscEntries: list[tuple[int, int, int]] = []
    defaultSampleSize = 0
    sampleCount = 0
    sampleSizesList: list[int] = []
    chunkOffsets: list[int] = []

    for boxType, boxPos, _, subStart, subEnd in parseBoxList(data, bodyStart, bodyEnd):
        if boxType == b"stsd":
            stsdBox = data[boxPos:subEnd]
        elif boxType == b"stts" and subStart + 8 <= subEnd:
            count = unpack_from(">I", data, subStart + 4)[0]
            pos = subStart + 8
            for _ in range(count):
                if pos + 8 > subEnd:
                    break
                sc, sd = unpack_from(">II", data, pos)
                sttsEntries.append((sc, sd))
                pos += 8
        elif boxType == b"ctts" and subStart + 8 <= subEnd:
            hasCtts = True
            cttsVersion = data[subStart]
            count = unpack_from(">I", data, subStart + 4)[0]
            pos = subStart + 8
            fmt = ">Ii" if cttsVersion == 1 else ">II"
            for _ in range(count):
                if pos + 8 > subEnd:
                    break
                sc, co = unpack_from(fmt, data, pos)
                cttsEntries.append((sc, co))
                pos += 8
        elif boxType == b"stss" and subStart + 8 <= subEnd:
            count = unpack_from(">I", data, subStart + 4)[0]
            pos = subStart + 8
            syncSamples = set()
            for _ in range(count):
                if pos + 4 > subEnd:
                    break
                syncSamples.add(unpack_from(">I", data, pos)[0] - 1)
                pos += 4
        elif boxType == b"stsc" and subStart + 8 <= subEnd:
            count = unpack_from(">I", data, subStart + 4)[0]
            pos = subStart + 8
            for _ in range(count):
                if pos + 12 > subEnd:
                    break
                fc, spc, sdi = unpack_from(">III", data, pos)
                stscEntries.append((fc, spc, sdi))
                pos += 12
        elif boxType == b"stsz" and subStart + 12 <= subEnd:
            defaultSampleSize = unpack_from(">I", data, subStart + 4)[0]
            sampleCount = unpack_from(">I", data, subStart + 8)[0]
            if defaultSampleSize == 0:
                pos = subStart + 12
                for _ in range(sampleCount):
                    if pos + 4 > subEnd:
                        break
                    sampleSizesList.append(unpack_from(">I", data, pos)[0])
                    pos += 4
        elif boxType == b"stco" and subStart + 8 <= subEnd:
            count = unpack_from(">I", data, subStart + 4)[0]
            pos = subStart + 8
            for _ in range(count):
                if pos + 4 > subEnd:
                    break
                chunkOffsets.append(unpack_from(">I", data, pos)[0])
                pos += 4
        elif boxType == b"co64" and subStart + 8 <= subEnd:
            count = unpack_from(">I", data, subStart + 4)[0]
            pos = subStart + 8
            for _ in range(count):
                if pos + 8 > subEnd:
                    break
                chunkOffsets.append(unpack_from(">Q", data, pos)[0])
                pos += 8

    if not stsdBox or not sttsEntries or not stscEntries or not chunkOffsets or sampleCount <= 0:
        return None

    sampleSizes = (defaultSampleSize,) * sampleCount if defaultSampleSize > 0 else tuple(sampleSizesList)
    if len(sampleSizes) != sampleCount:
        return None

    sampleDurations: list[int] = []
    for sc, sd in sttsEntries:
        sampleDurations.extend([sd] * sc)
    if len(sampleDurations) < sampleCount:
        lastDelta = sampleDurations[-1] if sampleDurations else 0
        sampleDurations.extend([lastDelta] * (sampleCount - len(sampleDurations)))
    elif len(sampleDurations) > sampleCount:
        del sampleDurations[sampleCount:]

    sampleCtsOffsets: tuple[int, ...] | None = None
    if hasCtts:
        ctsList: list[int] = []
        for sc, co in cttsEntries:
            ctsList.extend([co] * sc)
        if len(ctsList) < sampleCount:
            ctsList.extend([0] * (sampleCount - len(ctsList)))
        elif len(ctsList) > sampleCount:
            del ctsList[sampleCount:]
        sampleCtsOffsets = tuple(ctsList)

    chunkCount = len(chunkOffsets)
    sampleOffsets: list[int] = [0] * sampleCount
    chunkSampleRanges: list[tuple[int, int, int]] = []
    sampleIdx = 0

    for idx, (firstChunk, samplesPerChunk, sdi) in enumerate(stscEntries):
        nextFirstChunk = stscEntries[idx + 1][0] if idx + 1 < len(stscEntries) else chunkCount + 1
        startChunkIdx = max(0, firstChunk - 1)
        endChunkIdx = min(chunkCount, nextFirstChunk - 1)
        for chunkIdx in range(startChunkIdx, endChunkIdx):
            if sampleIdx >= sampleCount or samplesPerChunk <= 0:
                break
            cStart = sampleIdx
            cEnd = min(sampleCount, sampleIdx + samplesPerChunk)
            byteOffset = chunkOffsets[chunkIdx]
            for s in range(cStart, cEnd):
                sampleOffsets[s] = byteOffset
                byteOffset += sampleSizes[s]
            chunkSampleRanges.append((cStart, cEnd, sdi))
            sampleIdx = cEnd

    if sampleIdx == 0:
        return None
    if sampleIdx < sampleCount:
        sampleCount = sampleIdx
        sampleSizes = sampleSizes[:sampleCount]
        sampleDurations = sampleDurations[:sampleCount]
        sampleOffsets = sampleOffsets[:sampleCount]
        if sampleCtsOffsets is not None:
            sampleCtsOffsets = sampleCtsOffsets[:sampleCount]

    return TrackTable(
        trackIndex=trackIndex,
        handlerType=handlerType,
        timescale=timescale,
        duration=duration,
        stsdBox=stsdBox,
        sampleDurations=tuple(sampleDurations),
        sampleCtsOffsets=sampleCtsOffsets,
        cttsVersion=cttsVersion,
        syncSamples=frozenset(syncSamples) if syncSamples is not None else None,
        sampleSizes=sampleSizes,
        sampleOffsets=tuple(sampleOffsets),
        chunkSampleRanges=tuple(chunkSampleRanges),
    )


def findTrackSampleRange(
    table: TrackTable, startTime: float, endTime: float, alignToSync: bool
) -> tuple[int, int, float, float]:
    sampleCount = len(table.sampleSizes)
    timescale = table.timescale
    startTicks = startTime * timescale
    endTicks = endTime * timescale

    dts = 0
    s0 = 0
    s0Ticks = 0
    s1 = sampleCount
    s1Ticks = sum(table.sampleDurations)

    for i, dur in enumerate(table.sampleDurations):
        isSync = table.syncSamples is None or i in table.syncSamples
        if dts <= startTicks:
            if not alignToSync or isSync:
                s0 = i
                s0Ticks = dts
        if dts >= endTicks and i > s0:
            s1 = i
            s1Ticks = dts
            break
        dts += dur

    if s1 <= s0:
        s1 = sampleCount
        s1Ticks = sum(table.sampleDurations)

    actualStart = s0Ticks / timescale
    actualEnd = s1Ticks / timescale
    return s0, s1, actualStart, max(0.0, actualEnd - actualStart)


def buildProgressiveSegmentRange(
    data: bytes,
    index: ContainerIndex,
    startTime: float,
    endTime: float,
) -> SegmentRange | None:
    if not index.tracks:
        return None

    primary = next((t for t in index.tracks if t.handlerType == b"vide"), index.tracks[0])
    p0, p1, segStartTime, segDuration = findTrackSampleRange(
        primary, startTime, endTime, alignToSync=True,
    )
    segEndTime = segStartTime + segDuration

    trackSlices: dict[int, tuple[TrackTable, int, int]] = {
        primary.trackIndex: (primary, p0, p1),
    }
    for track in index.tracks:
        if track.trackIndex == primary.trackIndex:
            continue
        t0, t1, _, _ = findTrackSampleRange(
            track, segStartTime, segEndTime, alignToSync=False,
        )
        trackSlices[track.trackIndex] = (track, t0, t1)

    segStart = min(
        t.sampleOffsets[s0]
        for t, s0, _ in trackSlices.values()
    )
    segEnd = max(
        t.sampleOffsets[s1 - 1] + t.sampleSizes[s1 - 1]
        for t, _, s1 in trackSlices.values()
    )
    if segEnd <= segStart:
        return None

    boxes = parseMp4Boxes(data)
    ftypOffset, ftypSize = boxes.get("ftyp", (0, 0))
    ftypBytes = data[ftypOffset:ftypOffset + ftypSize] if ftypSize else b""
    moovOffset, moovSize = boxes["moov"]

    # First pass with delta=0 to measure exact patchedMoov length, then second pass with exact delta
    dummyMoov = buildPatchedMoov(data, moovOffset, moovSize, trackSlices, segDuration, 0)
    newMdatDataStart = len(ftypBytes) + len(dummyMoov) + 8
    delta = newMdatDataStart - segStart
    patchedMoov = buildPatchedMoov(data, moovOffset, moovSize, trackSlices, segDuration, delta)

    mdatPayloadSize = segEnd - segStart
    mdatBoxSize = 8 + mdatPayloadSize if 8 + mdatPayloadSize <= 0xFFFFFFFF else 0
    mdatHeader = pack(">I4s", mdatBoxSize, b"mdat")

    patchedHeader = ftypBytes + patchedMoov + mdatHeader
    return SegmentRange(patchedHeader, segStart, segEnd, segStartTime, segDuration)


def buildPatchedMoov(
    data: bytes,
    moovOffset: int,
    moovSize: int,
    trackSlices: dict[int, tuple[TrackTable, int, int]],
    segDuration: float,
    delta: int,
) -> bytes:
    movieTimescale = 1000
    children: list[bytes] = []
    trackIndex = 0
    for boxType, boxPos, _, bodyStart, boxEnd in parseBoxList(data, moovOffset + 8, moovOffset + moovSize):
        if boxType == b"mvhd":
            patchedMvhd, ts = patchMvhdDuration(data[boxPos:boxEnd], bodyStart - boxPos, segDuration)
            if ts > 0:
                movieTimescale = ts
            children.append(patchedMvhd)
        elif boxType == b"trak":
            if trackIndex in trackSlices:
                children.append(buildPatchedTrak(
                    data, bodyStart, boxEnd, trackSlices[trackIndex],
                    segDuration, movieTimescale, delta,
                ))
            trackIndex += 1
        elif boxType != b"mvex":
            children.append(data[boxPos:boxEnd])
    return buildBox(b"moov", b"".join(children))


def buildPatchedTrak(
    data: bytes,
    start: int,
    end: int,
    trackSlice: tuple[TrackTable, int, int],
    segDuration: float,
    movieTimescale: int,
    delta: int,
) -> bytes:
    children: list[bytes] = []
    for boxType, boxPos, _, bodyStart, boxEnd in parseBoxList(data, start, end):
        if boxType == b"tkhd":
            children.append(patchTkhdDuration(
                data[boxPos:boxEnd], bodyStart - boxPos, segDuration, movieTimescale,
            ))
        elif boxType == b"mdia":
            children.append(buildPatchedMdia(data, bodyStart, boxEnd, trackSlice, segDuration, delta))
        elif boxType != b"edts":
            children.append(data[boxPos:boxEnd])
    return buildBox(b"trak", b"".join(children))


def buildPatchedMdia(
    data: bytes,
    start: int,
    end: int,
    trackSlice: tuple[TrackTable, int, int],
    segDuration: float,
    delta: int,
) -> bytes:
    children: list[bytes] = []
    for boxType, boxPos, _, bodyStart, boxEnd in parseBoxList(data, start, end):
        if boxType == b"mdhd":
            children.append(patchMdhdDurationBox(data[boxPos:boxEnd], bodyStart - boxPos, segDuration))
        elif boxType == b"minf":
            children.append(buildPatchedMinf(data, bodyStart, boxEnd, trackSlice, delta))
        else:
            children.append(data[boxPos:boxEnd])
    return buildBox(b"mdia", b"".join(children))


def buildPatchedMinf(
    data: bytes,
    start: int,
    end: int,
    trackSlice: tuple[TrackTable, int, int],
    delta: int,
) -> bytes:
    table, s0, s1 = trackSlice
    children: list[bytes] = []
    for boxType, boxPos, _, _, boxEnd in parseBoxList(data, start, end):
        if boxType == b"stbl":
            children.append(buildPatchedStbl(table, s0, s1, delta))
        else:
            children.append(data[boxPos:boxEnd])
    return buildBox(b"minf", b"".join(children))


def toRunLengthEntries(values: Sequence[int]) -> list[tuple[int, int]]:
    if not values:
        return []
    entries: list[tuple[int, int]] = []
    prev = values[0]
    count = 1
    for v in values[1:]:
        if v == prev:
            count += 1
        else:
            entries.append((count, prev))
            prev = v
            count = 1
    entries.append((count, prev))
    return entries


def buildPatchedStbl(table: TrackTable, s0: int, s1: int, delta: int) -> bytes:
    children: list[bytes] = [table.stsdBox]

    sttsRuns = toRunLengthEntries(table.sampleDurations[s0:s1])
    sttsPayload = bytearray(pack(">II", 0, len(sttsRuns)))
    for sc, sd in sttsRuns:
        sttsPayload.extend(pack(">II", sc, sd))
    children.append(buildBox(b"stts", bytes(sttsPayload)))

    if table.sampleCtsOffsets is not None:
        cttsRuns = toRunLengthEntries(table.sampleCtsOffsets[s0:s1])
        cttsHeader = (table.cttsVersion << 24)
        cttsPayload = bytearray(pack(">II", cttsHeader, len(cttsRuns)))
        fmt = ">Ii" if table.cttsVersion == 1 else ">II"
        for sc, co in cttsRuns:
            cttsPayload.extend(pack(fmt, sc, co))
        children.append(buildBox(b"ctts", bytes(cttsPayload)))

    if table.syncSamples is not None:
        slicedSync = [s - s0 + 1 for s in sorted(table.syncSamples) if s0 <= s < s1]
        if not slicedSync or slicedSync[0] != 1:
            slicedSync.insert(0, 1)
        stssPayload = bytearray(pack(">II", 0, len(slicedSync)))
        for s in slicedSync:
            stssPayload.extend(pack(">I", s))
        children.append(buildBox(b"stss", bytes(stssPayload)))

    slicedChunks: list[tuple[int, int, int]] = []
    for cStart, cEnd, sdi in table.chunkSampleRanges:
        if cEnd <= s0:
            continue
        if cStart >= s1:
            break
        subStart = max(s0, cStart)
        subEnd = min(s1, cEnd)
        chunkOffset = max(0, table.sampleOffsets[subStart] + delta)
        slicedChunks.append((subEnd - subStart, sdi, chunkOffset))

    stscEntries: list[tuple[int, int, int]] = []
    for idx, (spc, sdi, _) in enumerate(slicedChunks):
        if not stscEntries or stscEntries[-1][1] != spc or stscEntries[-1][2] != sdi:
            stscEntries.append((idx + 1, spc, sdi))
    stscPayload = bytearray(pack(">II", 0, len(stscEntries)))
    for fc, spc, sdi in stscEntries:
        stscPayload.extend(pack(">III", fc, spc, sdi))
    children.append(buildBox(b"stsc", bytes(stscPayload)))

    slicedSizes = table.sampleSizes[s0:s1]
    stszPayload = bytearray(pack(">III", 0, 0, len(slicedSizes)))
    for sz in slicedSizes:
        stszPayload.extend(pack(">I", sz))
    children.append(buildBox(b"stsz", bytes(stszPayload)))

    useCo64 = any(off > 0xFFFFFFFF for _, _, off in slicedChunks)
    if useCo64:
        co64Payload = bytearray(pack(">II", 0, len(slicedChunks)))
        for _, _, off in slicedChunks:
            co64Payload.extend(pack(">Q", off))
        children.append(buildBox(b"co64", bytes(co64Payload)))
    else:
        stcoPayload = bytearray(pack(">II", 0, len(slicedChunks)))
        for _, _, off in slicedChunks:
            stcoPayload.extend(pack(">I", off))
        children.append(buildBox(b"stco", bytes(stcoPayload)))

    return buildBox(b"stbl", b"".join(children))


def patchMvhdDuration(rawBox: bytes, bodyStart: int, segDuration: float) -> tuple[bytes, int]:
    patched = bytearray(rawBox)
    version = patched[bodyStart]
    if version == 0 and bodyStart + 20 <= len(patched):
        ts = unpack_from(">I", patched, bodyStart + 12)[0]
        newDur = int(segDuration * ts)
        patched[bodyStart + 16:bodyStart + 20] = pack(">I", newDur)
        return bytes(patched), ts
    if version == 1 and bodyStart + 28 <= len(patched):
        ts = unpack_from(">I", patched, bodyStart + 20)[0]
        newDur = int(segDuration * ts)
        patched[bodyStart + 24:bodyStart + 32] = pack(">Q", newDur)
        return bytes(patched), ts
    return bytes(patched), 0


def patchTkhdDuration(rawBox: bytes, bodyStart: int, segDuration: float, movieTimescale: int) -> bytes:
    patched = bytearray(rawBox)
    version = patched[bodyStart]
    newDur = int(segDuration * movieTimescale)
    if version == 0 and bodyStart + 24 <= len(patched):
        patched[bodyStart + 20:bodyStart + 24] = pack(">I", newDur)
    elif version == 1 and bodyStart + 36 <= len(patched):
        patched[bodyStart + 28:bodyStart + 36] = pack(">Q", newDur)
    return bytes(patched)


def patchMdhdDurationBox(rawBox: bytes, bodyStart: int, segDuration: float) -> bytes:
    patched = bytearray(rawBox)
    version = patched[bodyStart]
    if version == 0 and bodyStart + 20 <= len(patched):
        ts = unpack_from(">I", patched, bodyStart + 12)[0]
        newDur = int(segDuration * ts)
        patched[bodyStart + 16:bodyStart + 20] = pack(">I", newDur)
    elif version == 1 and bodyStart + 28 <= len(patched):
        ts = unpack_from(">I", patched, bodyStart + 20)[0]
        newDur = int(segDuration * ts)
        patched[bodyStart + 24:bodyStart + 32] = pack(">Q", newDur)
    return bytes(patched)


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
    containerBoxes = {b"moov", b"trak", b"mdia", b"minf", b"stbl"}
    pos = start
    while pos + 8 <= end:
        size = unpack_from(">I", data, pos)[0]
        boxType = data[pos + 4:pos + 8]
        if size < 8 or pos + size > end:
            break
        if boxType in containerBoxes:
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


def parseEbmlFloat(data: bytes, pos: int, size: int) -> float:
    if size == 4:
        return unpack_from(">f", data, pos)[0]
    if size == 8:
        return unpack_from(">d", data, pos)[0]
    return 0.0


EBML_ID_SEGMENT = 0x18538067
EBML_ID_INFO = 0x1549A966
EBML_ID_TIMESTAMP_SCALE = 0x2AD7B1
EBML_ID_DURATION = 0x4489
EBML_ID_CUES = 0x1C53BB6B
EBML_ID_CUE_POINT = 0xBB
EBML_ID_CUE_TIME = 0xB3
EBML_ID_CUE_TRACK_POSITIONS = 0xB7
EBML_ID_CUE_CLUSTER_POSITION = 0xF1

EBML_MASTER_IDS = {EBML_ID_SEGMENT, EBML_ID_CUES, EBML_ID_CUE_POINT, EBML_ID_CUE_TRACK_POSITIONS}


def parseWebmInfoDuration(data: bytes, start: int, end: int) -> float:
    timestampScale = 1_000_000
    rawDuration = 0.0
    pos = start
    while pos < end:
        try:
            elemId, nextPos = parseEbmlElementId(data, pos)
            elemSize, nextPos = parseEbmlVarInt(data, nextPos)
        except ValueError:
            break
        if nextPos + elemSize > end:
            break
        if elemId == EBML_ID_TIMESTAMP_SCALE:
            timestampScale = parseEbmlUint(data, nextPos, elemSize) or 1_000_000
        elif elemId == EBML_ID_DURATION:
            rawDuration = parseEbmlFloat(data, nextPos, elemSize)
        pos = nextPos + elemSize
    return rawDuration * timestampScale / 1_000_000_000 if rawDuration > 0 else 0.0


def parseWebmHeader(data: bytes) -> tuple[int, float, list[tuple[int, int]]]:
    pos = 0

    elemId, pos = parseEbmlElementId(data, pos)
    elemSize, pos = parseEbmlVarInt(data, pos)
    pos += elemSize

    elemId, pos = parseEbmlElementId(data, pos)
    if elemId != EBML_ID_SEGMENT:
        raise ValueError("expected Segment element")
    _, pos = parseEbmlVarInt(data, pos)
    segmentDataOffset = pos

    duration = 0.0
    cues: list[tuple[int, int]] = []
    limit = min(len(data), segmentDataOffset + 65536)

    while pos < limit:
        try:
            elemId, nextPos = parseEbmlElementId(data, pos)
            elemSize, nextPos = parseEbmlVarInt(data, nextPos)
        except ValueError:
            break

        if elemId == EBML_ID_INFO and nextPos + elemSize <= len(data):
            duration = parseWebmInfoDuration(data, nextPos, nextPos + elemSize)
            pos = nextPos + elemSize
        elif elemId == EBML_ID_CUES:
            cues = parseCuesElement(data, nextPos, min(len(data), nextPos + elemSize))
            break
        elif elemId in EBML_MASTER_IDS:
            pos = nextPos
        else:
            pos = nextPos + elemSize

    if duration <= 0 and cues:
        duration = cues[-1][0] / 1000.0
    return segmentDataOffset, duration, cues


def parseWebmCues(data: bytes) -> tuple[int, list[tuple[int, int]]]:
    segmentDataOffset, _, cues = parseWebmHeader(data)
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
