"""端到端测试：YouTube 时间段下载 (1:00-1:05)。

完整管道：yt-dlp extract → sidx parse → partial download → reconstruct → ffmpeg trim。
使用真实 YouTube URL，只下载 ~130KB 而非整个 6.7MB 文件。
"""
from __future__ import annotations

import importlib
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import pytest

from features.yt_dlp_pack.container import buildMp4SegmentRange

VIDEO_URL = "https://www.youtube.com/watch?v=uG44DZMMDtw"
START_TIME = 60
END_TIME = 65


def _loadYtDlp():
    from features.yt_dlp_pack.config import youTubeRuntime
    vendorPath = str(youTubeRuntime.ytDlpFolder())
    if vendorPath and vendorPath not in sys.path:
        sys.path.insert(0, vendorPath)
    return importlib.import_module("yt_dlp")


def _extractFormats(yt_dlp):
    from features.yt_dlp_pack.config import youTubeRuntime
    opts = {
        "quiet": True, "no_warnings": True,
        "allowed_extractors": ["youtube.*"],
        "nocheckcertificate": True,
        "noplaylist": True,
    }
    qjsPath = youTubeRuntime.qjsPath()
    if qjsPath:
        opts["js_runtimes"] = {"quickjs": {"path": qjsPath}}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(VIDEO_URL, download=False)


def _pickFormat(formats, role):
    if role == "video":
        candidates = [f for f in formats if f.get("vcodec", "none") != "none"
                      and f.get("acodec", "none") == "none" and f.get("ext") == "mp4"]
        return sorted(candidates, key=lambda f: f.get("height", 0))[0] if candidates else None
    candidates = [f for f in formats if f.get("acodec", "none") != "none"
                  and f.get("vcodec", "none") == "none" and f.get("ext") in ("mp4", "m4a")]
    return sorted(candidates, key=lambda f: f.get("abr", 0))[0] if candidates else None


def _fetchBytes(url, headers, start, end):
    req = urllib.request.Request(url, headers={
        **headers,
        "Range": f"bytes={start}-{end - 1}",
    })
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def _probeDuration(ffprobe, path):
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


@pytest.fixture(scope="module")
def yt_info():
    yt_dlp = _loadYtDlp()
    return _extractFormats(yt_dlp)


@pytest.fixture(scope="module")
def ffmpeg_paths():
    from features.ffmpeg_pack.config import ffmpegRuntime
    ffmpeg = ffmpegRuntime.path()
    ffprobe = ffmpegRuntime.ffprobePath()
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg not installed")
    return ffmpeg, ffprobe


@pytest.mark.network
class TestSegmentE2E:

    def test_video_segment_download_and_trim(self, yt_info, ffmpeg_paths):
        ffmpeg, ffprobe = ffmpeg_paths
        formats = yt_info.get("formats", [])
        fmt = _pickFormat(formats, "video")
        assert fmt, "no video format found"

        url = fmt["url"]
        headers = dict(fmt.get("http_headers") or {})

        # 1. Fetch header (4KB)
        headerData = _fetchBytes(url, headers, 0, 4096)
        assert len(headerData) >= 2048

        # 2. Parse sidx → SegmentRange
        seg = buildMp4SegmentRange(headerData, START_TIME, END_TIME)
        segmentSize = seg.segEnd - seg.segStart
        fullSize = int(fmt.get("filesize") or fmt.get("filesize_approx") or 0)

        print(f"\nSegment: {seg.segStart}-{seg.segEnd} ({segmentSize} bytes)")
        print(f"Full file: {fullSize} bytes")
        print(f"Saving: {100 - segmentSize * 100 // fullSize}%")

        assert segmentSize < fullSize // 2, "segment should be much smaller than full file"

        # 3. Download segment bytes
        segmentData = _fetchBytes(url, headers, seg.segStart, seg.segEnd)
        assert len(segmentData) == segmentSize

        # 4. Reconstruct: patchedHeader + segment → valid MP4
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(seg.patchedHeader)
            tmp.write(segmentData)
            reconstructed = Path(tmp.name)

        try:
            # 5. ffmpeg trim
            outputPath = reconstructed.with_name("trimmed.mp4")
            result = subprocess.run(
                [ffmpeg, "-y", "-v", "error",
                 "-ss", str(START_TIME - seg.segStartTime),
                 "-i", str(reconstructed),
                 "-t", str(END_TIME - START_TIME),
                 "-c", "copy", str(outputPath)],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"ffmpeg failed: {result.stderr}"
            assert outputPath.exists()
            assert outputPath.stat().st_size > 0

            # 6. Verify duration
            duration = _probeDuration(ffprobe, outputPath)
            print(f"Output duration: {duration:.2f}s (expected ~{END_TIME - START_TIME}s)")
            assert 3.0 <= duration <= 8.0, f"unexpected duration: {duration}"

        finally:
            reconstructed.unlink(missing_ok=True)
            outputPath.unlink(missing_ok=True)

    def test_audio_segment_download_and_trim(self, yt_info, ffmpeg_paths):
        ffmpeg, ffprobe = ffmpeg_paths
        formats = yt_info.get("formats", [])
        fmt = _pickFormat(formats, "audio")
        assert fmt, "no audio format found"

        url = fmt["url"]
        headers = dict(fmt.get("http_headers") or {})

        headerData = _fetchBytes(url, headers, 0, 4096)
        seg = buildMp4SegmentRange(headerData, START_TIME, END_TIME)

        segmentData = _fetchBytes(url, headers, seg.segStart, seg.segEnd)

        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as tmp:
            tmp.write(seg.patchedHeader)
            tmp.write(segmentData)
            reconstructed = Path(tmp.name)

        try:
            outputPath = reconstructed.with_name("trimmed.m4a")
            result = subprocess.run(
                [ffmpeg, "-y", "-v", "error",
                 "-ss", str(START_TIME - seg.segStartTime),
                 "-i", str(reconstructed),
                 "-t", str(END_TIME - START_TIME),
                 "-c", "copy", str(outputPath)],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"ffmpeg failed: {result.stderr}"
            assert outputPath.exists()

            duration = _probeDuration(ffprobe, outputPath)
            print(f"\nAudio output duration: {duration:.2f}s")
            assert 3.0 <= duration <= 8.0

        finally:
            reconstructed.unlink(missing_ok=True)
            outputPath.unlink(missing_ok=True)
