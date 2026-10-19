from __future__ import annotations

from pathlib import Path

import pytest

from app.container import (
    buildMp4SegmentRange,
    parseMp4Boxes,
)

SAMPLE = Path(__file__).parent / "samples" / "youtube_video_header.bin"


@pytest.fixture
def videoHeader() -> bytes:
    return SAMPLE.read_bytes()


def test_build_header_from_ftyp_and_moov(videoHeader):
    seg = buildMp4SegmentRange(videoHeader, 60, 65)
    assert seg.patchedHeader[:4] == b'\x00\x00\x00\x1c'  # ftyp size=28
    assert seg.patchedHeader[4:8] == b'ftyp'
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
