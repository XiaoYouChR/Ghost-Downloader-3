"""container.py 时间段下载核心逻辑测试。

Seam: buildMp4SegmentRange / buildWebmSegmentRange 纯函数。
输入：流头部 bytes + 起止时间 → 输出：SegmentRange(patchedHeader, segStart, segEnd)。

使用真实 YouTube 视频头部 fixture（itag 160, 730s, 6.7MB）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.container import (
    SegmentRange,
    buildMp4SegmentRange,
    _parseMp4Boxes,
    _parseSidx,
)

FIXTURE = Path(__file__).parent / "fixtures" / "youtube_video_header.bin"


@pytest.fixture
def video_header() -> bytes:
    return FIXTURE.read_bytes()


class TestParseMp4Boxes:

    def test_finds_required_boxes(self, video_header):
        boxes = _parseMp4Boxes(video_header)
        assert "ftyp" in boxes
        assert "moov" in boxes
        assert "sidx" in boxes

    def test_box_order_ftyp_moov_sidx(self, video_header):
        boxes = _parseMp4Boxes(video_header)
        assert boxes["ftyp"][0] < boxes["moov"][0] < boxes["sidx"][0]


class TestParseSidx:

    def test_reference_count(self, video_header):
        boxes = _parseMp4Boxes(video_header)
        offset, size = boxes["sidx"]
        refs = _parseSidx(video_header, offset, size)
        assert len(refs) == 146

    def test_references_cover_full_duration(self, video_header):
        boxes = _parseMp4Boxes(video_header)
        offset, size = boxes["sidx"]
        refs = _parseSidx(video_header, offset, size)
        totalDuration = sum(dur for dur, _ in refs)
        assert abs(totalDuration - 730.93) < 0.1

    def test_references_cover_full_filesize(self, video_header):
        boxes = _parseMp4Boxes(video_header)
        sidxOffset, sidxSize = boxes["sidx"]
        headerSize = sidxOffset + sidxSize
        refs = _parseSidx(video_header, sidxOffset, sidxSize)
        totalBytes = headerSize + sum(size for _, size in refs)
        assert totalBytes == 6744153


class TestBuildMp4SegmentRange:

    def test_segment_60_65(self, video_header):
        seg = buildMp4SegmentRange(video_header, 60, 65)
        assert isinstance(seg, SegmentRange)
        assert seg.segStart > 0
        assert seg.segEnd > seg.segStart
        assert seg.segEnd - seg.segStart < 200_000

    def test_segment_covers_requested_time(self, video_header):
        """segStart 对应的 reference 起始时间 <= startTime"""
        boxes = _parseMp4Boxes(video_header)
        sidxOffset, sidxSize = boxes["sidx"]
        headerSize = sidxOffset + sidxSize
        refs = _parseSidx(video_header, sidxOffset, sidxSize)

        seg = buildMp4SegmentRange(video_header, 60, 65)

        bytePos = headerSize
        timeSec = 0.0
        segStartTime = None
        segEndTime = None
        for dur, size in refs:
            if bytePos == seg.segStart:
                segStartTime = timeSec
            bytePos += size
            if bytePos == seg.segEnd:
                segEndTime = timeSec + dur
                break
            timeSec += dur

        assert segStartTime is not None, f"segStart {seg.segStart} not on reference boundary"
        assert segEndTime is not None, f"segEnd {seg.segEnd} not on reference boundary"
        assert segStartTime <= 60
        assert segEndTime >= 65

    def test_patched_header_is_ftyp_plus_moov(self, video_header):
        seg = buildMp4SegmentRange(video_header, 60, 65)
        assert seg.patchedHeader[:4] == b'\x00\x00\x00\x1c'  # ftyp size=28
        assert seg.patchedHeader[4:8] == b'ftyp'
        boxes = _parseMp4Boxes(video_header)
        moovEnd = boxes["moov"][0] + boxes["moov"][1]
        assert len(seg.patchedHeader) == moovEnd

    def test_full_video_returns_full_range(self, video_header):
        """startTime=0 endTime=731 should cover the entire file"""
        seg = buildMp4SegmentRange(video_header, 0, 731)
        boxes = _parseMp4Boxes(video_header)
        dataStart = boxes["sidx"][0] + boxes["sidx"][1]
        assert seg.segStart == dataStart
        assert seg.segEnd == 6744153

    def test_first_5_seconds(self, video_header):
        seg = buildMp4SegmentRange(video_header, 0, 5)
        boxes = _parseMp4Boxes(video_header)
        dataStart = boxes["sidx"][0] + boxes["sidx"][1]
        assert seg.segStart == dataStart
        assert seg.segEnd - seg.segStart < 100_000

    def test_last_5_seconds(self, video_header):
        seg = buildMp4SegmentRange(video_header, 726, 731)
        assert seg.segEnd == 6744153
        assert seg.segEnd - seg.segStart < 100_000
