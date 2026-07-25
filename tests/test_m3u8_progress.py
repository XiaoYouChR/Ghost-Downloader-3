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
