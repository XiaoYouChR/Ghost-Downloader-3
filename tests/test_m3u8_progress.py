"""M3U8TaskStep._parseOutputLine 的输出格式解析测试。

Seam: _parseOutputLine — 输入一行 N_m3u8DL-RE stdout 文本，
观察 progress / speed / receivedBytes / task.fileSize 的更新。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from app.format import toBytes
from app.models.task import Task, TaskStep, TaskStatus
from features.m3u8_pack.task import M3U8Task, M3U8TaskStep


def makeStep() -> M3U8TaskStep:
    task = M3U8Task(
        name="test.mp4",
        url="http://test",
        fileSize=1,
        outputFolder=Path("."),
    )
    step = M3U8TaskStep(stepIndex=1)
    task.addStep(step)
    return step


class TestVodProgressV06:
    """N_m3u8DL-RE v0.6.0 的 VOD 进度格式——无空格分隔。"""

    def test_with_sizes_no_spaces(self):
        step = makeStep()
        step._parseOutputLine(
            "Vid 1280x720 | 2000 Kbps ━━━━━━ 6/6857 0.09% 3.12MB/3.48GB1.55MBps01:27:07"
        )
        assert step.progress == pytest.approx(0.09)
        assert step.speed == toBytes("1.55", "MBps")
        assert step.receivedBytes == toBytes("3.12", "MB")
        assert step.task.fileSize == toBytes("3.48", "GB")

    def test_dash_speed_only(self):
        step = makeStep()
        step._parseOutputLine(
            "Vid 1280x720 | 2000 Kbps ━━━━━━ 0/6857 0.00% -191.58KBps --:--:--"
        )
        assert step.progress == pytest.approx(0.0)
        assert step.speed == toBytes("191.58", "KBps")

    def test_dash_speed_with_retries(self):
        step = makeStep()
        step._parseOutputLine(
            "Vid 1280x720 | 2000 Kbps ━━━━━━ 0/6857 0.00% -0.00Bps(9) --:--:--"
        )
        assert step.progress == pytest.approx(0.0)
        assert step.speed == 0

    def test_zero_bps(self):
        step = makeStep()
        step._parseOutputLine(
            "Vid 1920x1080 | 6221 Kbps ━━━━━━ 0/64 0.00% -0.00Bps --:--:--"
        )
        assert step.progress == pytest.approx(0.0)
        assert step.speed == 0


class TestVodProgressLegacy:
    """旧版 N_m3u8DL-RE 的格式——字段间有空格。"""

    def test_legacy_format(self):
        step = makeStep()
        step._parseOutputLine(
            "12/64 18.75% 12.34MB/56.78MB 1.23MBps 00:01:30"
        )
        assert step.progress == pytest.approx(18.75)
        assert step.speed == toBytes("1.23", "MBps")
        assert step.receivedBytes == toBytes("12.34", "MB")
        assert step.task.fileSize == toBytes("56.78", "MB")


class TestConcatenatedBuffer:
    """NonAnsiWriter 剥掉换行符后，多条进度拼成一串——取最后一条。"""

    def test_takes_last_vod_match(self):
        step = makeStep()
        blob = (
            "Vid 1280x720 | 1650 Kbps | 30 ━━━━━━ 3/155 1.94% -0.00Bps00:00:37"
            "Vid 1280x720 | 1650 Kbps | 30 ━━━━━━ 35/155 22.58% 30.99MB/137.26MB28.45MBps00:00:06"
            "Vid 1280x720 | 1650 Kbps | 30 ━━━━━━ 100/155 64.52% 71.82MB/148.43MB40.83MBps00:00:02"
        )
        step._parseOutputLine(blob)
        assert step.progress == pytest.approx(64.52)
        assert step.speed == toBytes("40.83", "MBps")
        assert step.receivedBytes == toBytes("71.82", "MB")
        assert step.task.fileSize == toBytes("148.43", "MB")

    def test_last_message_takes_tail(self):
        step = makeStep()
        filler = "x" * 2000
        step._parseOutputLine(filler)
        assert step.lastMessage == filler[-1000:]


class TestLiveProgress:
    """SimpleLiveRecordManager2 的直播进度格式。"""

    def test_basic(self):
        step = makeStep()
        step._parseOutputLine(
            "Vid ━━━━━━ 01m30s/02m00s 125/250 Recording 50% 1.55MBps"
        )
        assert step.liveElapsed == "01m30s"
        assert step.liveTotal == "02m00s"
        assert step.liveStatus == "Recording"
        assert step.progress == pytest.approx(50)
        assert step.speed == toBytes("1.55", "MBps")

    def test_over_one_hour(self):
        step = makeStep()
        step._parseOutputLine(
            "Vid ━━━━━━ 01h05m30s/01h30m00s 3000/4500 Recording 66% 2.10MBps"
        )
        assert step.liveElapsed == "01h05m30s"
        assert step.liveTotal == "01h30m00s"
        assert step.progress == pytest.approx(66)

    def test_waiting_with_dash_speed(self):
        step = makeStep()
        step._parseOutputLine(
            "Vid ━━━━━━ 00m00s/00m00s 0/0 Waiting 0% -"
        )
        assert step.liveStatus == "Waiting"
        assert step.progress == pytest.approx(0)
        assert step.speed == 0


class TestLiveRecordProgress:
    """HTTPLiveRecordManager 的直播录制格式——无百分比。"""

    def test_basic(self):
        step = makeStep()
        step._parseOutputLine(
            "Vid ━━━━━━ 01m30s/02m00s 130.00MB 125/250 Recording 1.55MBps"
        )
        assert step.liveElapsed == "01m30s"
        assert step.liveTotal == "02m00s"
        assert step.liveStatus == "Recording"
        assert step.speed == toBytes("1.55", "MBps")
        assert step.progress == 0

    def test_over_one_hour(self):
        step = makeStep()
        step._parseOutputLine(
            "Vid ━━━━━━ 02h10m00s/02h15m30s 5.12GB 9000/9500 Recording 30.00MBps"
        )
        assert step.liveElapsed == "02h10m00s"
        assert step.liveTotal == "02h15m30s"
        assert step.speed == toBytes("30.00", "MBps")

    def test_dash_speed(self):
        step = makeStep()
        step._parseOutputLine(
            "Vid ━━━━━━ 00m10s/00m30s 0.50MB 5/15 Recording -"
        )
        assert step.liveStatus == "Recording"
        assert step.speed == 0
