from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

INFO = {"formats": [
    {"acodec": "mp4a", "vcodec": "none", "protocol": "https", "language": "ja",
     "language_preference": -1, "format_note": "Japanese"},
    {"acodec": "mp4a", "vcodec": "none", "protocol": "https", "language": "en",
     "language_preference": 10, "format_note": "English"},
]}


def loadAdapter(pack: str):
    return importlib.import_module(f"features.{pack}.android")


def makeTask(name="视频.mp4", isVideoEnabled=True, isAudioEnabled=True, isCoverEnabled=False, coverUrl=""):
    from features.yt_dlp_pack.task import YouTubeTask
    return YouTubeTask(name=name, url="https://www.youtube.com/watch?v=x", packId="yt_dlp", outputFolder=Path("/tmp"),
                       isVideoEnabled=isVideoEnabled, isAudioEnabled=isAudioEnabled,
                       isCoverEnabled=isCoverEnabled, coverUrl=coverUrl)


@pytest.fixture
def ytdlp(monkeypatch):
    adapter = loadAdapter("yt_dlp_pack")
    monkeypatch.setattr(adapter, "probeFormats", lambda url: INFO)
    monkeypatch.setattr(adapter, "updateSize", lambda task: None)
    return adapter


def test_probe_pins_the_first_audio_language_like_desktop(ytdlp):
    task = makeTask()

    ytdlp.probe(task, "https://example.test/v", "media")

    assert task.audioLanguages == "en"


def test_probe_keeps_an_existing_choice(ytdlp):
    task = makeTask()
    task.audioLanguages = "ja"

    ytdlp.probe(task, "https://example.test/v", "media")

    assert task.audioLanguages == "ja"


def test_single_language_media_is_left_unpinned(ytdlp, monkeypatch):
    monkeypatch.setattr(ytdlp, "probeFormats", lambda url: {"formats": [INFO["formats"][1]]})
    task = makeTask()

    ytdlp.probe(task, "https://example.test/v", "media")

    assert task.audioLanguages == ""


def test_probe_keeps_the_cover_when_media_has_no_thumbnail(ytdlp):
    task = makeTask(coverUrl="https://example.test/old.jpg")

    ytdlp.probe(task, "https://example.test/v", "media")

    assert task.coverUrl == "https://example.test/old.jpg"


def test_probe_takes_the_cover_from_the_thumbnail(ytdlp, monkeypatch):
    monkeypatch.setattr(ytdlp, "probeFormats",
                        lambda url: {**INFO, "thumbnail": "https://example.test/new.jpg"})
    task = makeTask()

    ytdlp.probe(task, "https://example.test/v", "media")

    assert task.coverUrl == "https://example.test/new.jpg"


def test_quality_change_keeps_the_task_name(ytdlp):
    task = makeTask(name="自定义名字")

    ytdlp.setControl(task, "video", "1080")

    assert task.name == "自定义名字"


def test_language_change_keeps_the_task_name(ytdlp):
    task = makeTask(name="自定义名字")

    ytdlp.setControl(task, "language", "ja")

    assert task.name == "自定义名字"


def test_track_toggle_rewrites_the_extension(ytdlp):
    task = makeTask(name="自定义名字", isVideoEnabled=False)

    ytdlp.setControl(task, "video", "720")

    assert task.name == "自定义名字.mp4"


def test_cover_toggle_rewrites_the_extension_like_desktop(ytdlp):
    task = makeTask(name="自定义名字")

    ytdlp.setControl(task, "cover", "1")

    assert task.name == "自定义名字.mp4"


def test_cover_toggle_with_audio_only_rewrites_to_m4a(ytdlp):
    task = makeTask(name="自定义名字", isVideoEnabled=False)

    ytdlp.setControl(task, "cover", "1")

    assert task.name == "自定义名字.m4a"


def test_flag_change_rewrites_even_when_the_extension_is_unchanged(ytdlp):
    task = makeTask(name="自定义名字")

    ytdlp.setControl(task, "audio", "")

    assert task.name == "自定义名字.mp4"
