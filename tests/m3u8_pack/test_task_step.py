from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.config.cfg import cfg
from app.format import toBytes
from features.m3u8_pack.task import M3U8SubtitleStep, M3U8Task, M3U8TaskStep


def buildStep(name: str = "test.mp4", outputFolder: Path = Path("."), *, isLive: bool = False) -> M3U8TaskStep:
    task = M3U8Task(
        name=name,
        url="http://test",
        fileSize=1,
        outputFolder=outputFolder,
        isLive=isLive,
    )
    step = M3U8TaskStep(stepIndex=1)
    task.addStep(step)
    return step


def saveNameOf(step: M3U8TaskStep) -> str:
    return next(a.removeprefix("--save-name=") for a in step.buildCommand("http://test") if a.startswith("--save-name="))


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
    assert step.liveStatus == "Recording"
    assert step.progress == pytest.approx(50)
    assert step.speed == toBytes("1.55", "MBps")


def test_parse_live_progress_over_an_hour():
    step = buildStep()
    step.parseOutputLine(
        "Vid ━━━━━━ 01h05m30s/01h30m00s 3000/4500 Recording 66% 2.10MBps"
    )
    assert step.liveElapsed == "01h05m30s"
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
    assert step.liveStatus == "Recording"
    assert step.speed == toBytes("1.55", "MBps")
    assert step.progress == 0


def test_parse_live_record_progress_over_an_hour():
    step = buildStep()
    step.parseOutputLine(
        "Vid ━━━━━━ 02h10m00s/02h15m30s 5.12GB 9000/9500 Recording 30.00MBps"
    )
    assert step.liveElapsed == "02h10m00s"
    assert step.speed == toBytes("30.00", "MBps")


def test_parse_live_record_progress_without_speed():
    step = buildStep()
    step.parseOutputLine(
        "Vid ━━━━━━ 00m10s/00m30s 0.50MB 5/15 Recording -"
    )
    assert step.liveStatus == "Recording"
    assert step.speed == 0


def test_build_command_converts_global_speed_limit(monkeypatch):
    monkeypatch.setattr(cfg.isSpeedLimitEnabled, "value", True)
    monkeypatch.setattr(cfg.speedLimitation, "value", 1150976)
    args = buildStep().buildCommand("http://test")
    assert "--max-speed=1124K" in args


@pytest.mark.parametrize("name", [
    "(1) X 上的 Alexey Fateev：“https t.co FkpOOsDFNI shipped GLM-5.4”.mp4",
    "clip....mp4",
    ".hidden.mp4",
    "trailing space .mp4",
])
def test_build_command_uses_safe_save_name(tmp_path: Path, name: str):
    step = buildStep(name=name, outputFolder=tmp_path)
    saveName = saveNameOf(step)
    assert saveName.isascii()
    assert len(saveName) <= 16
    assert saveName == saveName.strip(". ")
    assert Path(name).stem not in saveName


def test_build_subtitle_command_uses_safe_save_name(tmp_path: Path):
    task = M3U8Task(
        name="(3) X 上的 BBC News 中文：“在北京郊外”.mp4",
        url="http://test",
        fileSize=1,
        outputFolder=tmp_path,
        subtitleLanguages=["zh"],
    )
    step = M3U8SubtitleStep(stepIndex=2, language="zh", name="zh")
    task.addStep(step)

    args = step.buildCommand("http://test")
    saveName = saveNameOf(step)
    assert saveName.isascii()
    assert len(saveName) <= 16
    assert "--sub-only" in args


def test_move_output_prefers_target_suffix_and_updates_file_size(tmp_path: Path):
    step = buildStep(name="clip....mp4", outputFolder=tmp_path)
    target = Path(step.outputPath)
    target.write_bytes(b"")

    part = step.task.partPath
    part.mkdir()
    saveName = saveNameOf(step)
    tsFile = part / f"{saveName}.ts"
    mp4File = part / f"{saveName}.mp4"
    tsFile.write_bytes(b"raw-ts")
    mp4File.write_bytes(b"muxed-mp4-data")
    os.utime(mp4File, (100, 100))
    os.utime(tsFile, (200, 200))

    assert step.moveOutput() is True
    assert target.read_bytes() == b"muxed-mp4-data"
    assert step.task.fileSize == len(b"muxed-mp4-data")
    assert not mp4File.exists()


def test_move_output_falls_back_to_newest_file(tmp_path: Path):
    step = buildStep(name="clip.mp4", outputFolder=tmp_path)
    target = Path(step.outputPath)
    target.write_bytes(b"")

    part = step.task.partPath
    part.mkdir()
    saveName = saveNameOf(step)
    (part / f"{saveName}.log").write_text("log")
    (part / "stale.mp4").write_bytes(b"stale")
    older = part / f"{saveName}.m4a"
    newer = part / f"{saveName}.ts"
    older.write_bytes(b"old")
    newer.write_bytes(b"new-ts")
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))

    assert step.moveOutput() is True
    assert target.read_bytes() == b"new-ts"


def test_move_output_keeps_existing_file(tmp_path: Path):
    step = buildStep(name="clip.mp4", outputFolder=tmp_path)
    target = Path(step.outputPath)
    target.write_bytes(b"already-final")

    assert step.moveOutput() is True
    assert target.read_bytes() == b"already-final"
    assert step.task.fileSize == len(b"already-final")


def test_move_output_fails_when_part_missing(tmp_path: Path):
    step = buildStep(name="clip.mp4", outputFolder=tmp_path)
    Path(step.outputPath).write_bytes(b"")

    assert step.moveOutput() is False

    step.task.partPath.mkdir()
    (step.task.partPath / "other.mp4").write_bytes(b"wrong-prefix")
    assert step.moveOutput() is False


def test_move_subtitle_replaces_placeholder(tmp_path: Path):
    task = M3U8Task(
        name="clip.mp4",
        url="http://test",
        fileSize=1,
        outputFolder=tmp_path,
        subtitleLanguages=["zh"],
    )
    step = M3U8SubtitleStep(stepIndex=2, language="zh", name="zh")
    task.addStep(step)

    target = Path(step.outputPath)
    target.write_bytes(b"")

    saveDir = task.partPath / "subtitle2"
    saveDir.mkdir(parents=True)
    saveName = saveNameOf(step)
    (saveDir / f"{saveName}.zh.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")

    assert step.moveOutput() is True
    assert "hi" in target.read_text(encoding="utf-8")


def test_move_missing_subtitle_deletes_placeholder(tmp_path: Path):
    task = M3U8Task(
        name="clip.mp4",
        url="http://test",
        fileSize=1,
        outputFolder=tmp_path,
        subtitleLanguages=["en"],
    )
    step = M3U8SubtitleStep(stepIndex=2, language="en", name="en")
    task.addStep(step)

    target = Path(step.outputPath)
    target.write_bytes(b"")

    assert step.moveOutput() is True
    assert not target.exists()
