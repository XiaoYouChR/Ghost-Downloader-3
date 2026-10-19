from __future__ import annotations

from pathlib import Path

import pytest

from app.format import toBytes
from features.m3u8_pack.task import M3U8Task, M3U8TaskStep


def buildStep() -> M3U8TaskStep:
    task = M3U8Task(
        name="test.mp4",
        url="http://test",
        fileSize=1,
        outputFolder=Path("."),
    )
    step = M3U8TaskStep(stepIndex=1)
    task.addStep(step)
    return step


def test_parse_vod_progress_with_sizes():
    step = buildStep()
    step.parseOutputLine(
        "Vid 1280x720 | 2000 Kbps ━━━━━━ 6/6857 0.09% 3.12MB/3.48GB1.55MBps01:27:07"
    )
    assert step.progress == pytest.approx(0.09)
    assert step.speed == toBytes("1.55", "MBps")
    assert step.receivedBytes == toBytes("3.12", "MB")
    assert step.task.fileSize == toBytes("3.48", "GB")


def test_parse_vod_progress_with_speed_only():
    step = buildStep()
    step.parseOutputLine(
        "Vid 1280x720 | 2000 Kbps ━━━━━━ 0/6857 0.00% -191.58KBps --:--:--"
    )
    assert step.progress == pytest.approx(0.0)
    assert step.speed == toBytes("191.58", "KBps")


def test_parse_vod_progress_with_retries():
    step = buildStep()
    step.parseOutputLine(
        "Vid 1280x720 | 2000 Kbps ━━━━━━ 0/6857 0.00% -0.00Bps(9) --:--:--"
    )
    assert step.progress == pytest.approx(0.0)
    assert step.speed == 0


def test_parse_vod_progress_at_zero_speed():
    step = buildStep()
    step.parseOutputLine(
        "Vid 1920x1080 | 6221 Kbps ━━━━━━ 0/64 0.00% -0.00Bps --:--:--"
    )
    assert step.progress == pytest.approx(0.0)
    assert step.speed == 0


def test_parse_old_vod_progress():
    step = buildStep()
    step.parseOutputLine(
        "12/64 18.75% 12.34MB/56.78MB 1.23MBps 00:01:30"
    )
    assert step.progress == pytest.approx(18.75)
    assert step.speed == toBytes("1.23", "MBps")
    assert step.receivedBytes == toBytes("12.34", "MB")
    assert step.task.fileSize == toBytes("56.78", "MB")


def test_parse_glued_lines_uses_last():
    step = buildStep()
    blob = (
        "Vid 1280x720 | 1650 Kbps | 30 ━━━━━━ 3/155 1.94% -0.00Bps00:00:37"
        "Vid 1280x720 | 1650 Kbps | 30 ━━━━━━ 35/155 22.58% 30.99MB/137.26MB28.45MBps00:00:06"
        "Vid 1280x720 | 1650 Kbps | 30 ━━━━━━ 100/155 64.52% 71.82MB/148.43MB40.83MBps00:00:02"
    )
    step.parseOutputLine(blob)
    assert step.progress == pytest.approx(64.52)
    assert step.speed == toBytes("40.83", "MBps")
    assert step.receivedBytes == toBytes("71.82", "MB")
    assert step.task.fileSize == toBytes("148.43", "MB")


def test_parse_live_progress():
    step = buildStep()
    step.parseOutputLine(
        "Vid ━━━━━━ 01m30s/02m00s 125/250 Recording 50% 1.55MBps"
    )
    assert step.liveElapsed == "01m30s"
    assert step.liveTotal == "02m00s"
    assert step.liveStatus == "Recording"
    assert step.progress == pytest.approx(50)
    assert step.speed == toBytes("1.55", "MBps")


def test_parse_live_progress_over_an_hour():
    step = buildStep()
    step.parseOutputLine(
        "Vid ━━━━━━ 01h05m30s/01h30m00s 3000/4500 Recording 66% 2.10MBps"
    )
    assert step.liveElapsed == "01h05m30s"
    assert step.liveTotal == "01h30m00s"
    assert step.progress == pytest.approx(66)


def test_parse_live_progress_while_waiting():
    step = buildStep()
    step.parseOutputLine(
        "Vid ━━━━━━ 00m00s/00m00s 0/0 Waiting 0% -"
    )
    assert step.liveStatus == "Waiting"
    assert step.progress == pytest.approx(0)
    assert step.speed == 0


def test_parse_live_record_progress():
    step = buildStep()
    step.parseOutputLine(
        "Vid ━━━━━━ 01m30s/02m00s 130.00MB 125/250 Recording 1.55MBps"
    )
    assert step.liveElapsed == "01m30s"
    assert step.liveTotal == "02m00s"
    assert step.liveStatus == "Recording"
    assert step.speed == toBytes("1.55", "MBps")
    assert step.progress == 0


def test_parse_live_record_progress_over_an_hour():
    step = buildStep()
    step.parseOutputLine(
        "Vid ━━━━━━ 02h10m00s/02h15m30s 5.12GB 9000/9500 Recording 30.00MBps"
    )
    assert step.liveElapsed == "02h10m00s"
    assert step.liveTotal == "02h15m30s"
    assert step.speed == toBytes("30.00", "MBps")


def test_parse_live_record_progress_without_speed():
    step = buildStep()
    step.parseOutputLine(
        "Vid ━━━━━━ 00m10s/00m30s 0.50MB 5/15 Recording -"
    )
    assert step.liveStatus == "Recording"
    assert step.speed == 0
