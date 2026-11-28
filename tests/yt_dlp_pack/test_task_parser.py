from __future__ import annotations

import pytest

from app.models.task import TaskOptions
from yt_dlp_pack.pack import YouTubeParser
from yt_dlp_pack.task import YouTubeTask

PLAYLIST_URLS = [
    "https://www.youtube.com/playlist?list=PL123",
    "https://www.youtube.com/watch?v=abc&list=PL123",
    "https://www.youtube.com/@channel",
    "https://www.youtube.com/@channel/videos",
    "https://www.youtube.com/@channel/shorts",
    "https://www.youtube.com/@channel/streams",
    "https://www.youtube.com/c/ChannelName/videos",
    "https://www.youtube.com/user/ChannelName/videos",
    "https://www.youtube.com/channel/UC123/videos",
]

VIDEO_URLS = [
    "https://www.youtube.com/watch?v=abc",
    "https://youtu.be/abc",
    "https://www.youtube.com/@channel/about",
    "https://www.youtube.com/@channel/playlists",
]


async def parseTask(url: str, tmp_path, monkeypatch) -> YouTubeTask:
    async def fakeFetchTitle(self, _url: str) -> str:
        return ""

    monkeypatch.setattr(YouTubeParser, "_fetchTitle", fakeFetchTitle)
    task = await YouTubeParser().parse(
        TaskOptions(url=url, outputFolder=tmp_path, headers={})
    )
    assert isinstance(task, YouTubeTask)
    return task


@pytest.mark.parametrize("url", PLAYLIST_URLS)
async def test_parse_playlist_link_creates_playlist_task(url, tmp_path, monkeypatch):
    task = await parseTask(url, tmp_path, monkeypatch)

    assert task.isPlaylist


@pytest.mark.parametrize("url", VIDEO_URLS)
async def test_parse_video_link_keeps_single_task(url, tmp_path, monkeypatch):
    task = await parseTask(url, tmp_path, monkeypatch)

    assert not task.isPlaylist


def test_probe_playlist_reads_channel_entries(monkeypatch):
    from yt_dlp_pack import task as ytDlpTask

    seen: dict = {}

    def fakeExtract(url: str, opts: dict) -> dict:
        seen["url"] = url
        seen["opts"] = opts
        return {
            "entries": [
                {"id": "aaa", "title": "First", "duration": 10},
                {"id": "bbb", "title": "Second"},
            ],
        }

    monkeypatch.setattr(ytDlpTask, "extractInfo", fakeExtract)
    videos = ytDlpTask.probePlaylist("https://www.youtube.com/@channel/videos")

    assert seen["url"] == "https://www.youtube.com/@channel/videos"
    assert seen["opts"]["extract_flat"] is True
    assert "noplaylist" not in seen["opts"]
    assert videos == [
        {"id": "aaa", "title": "First", "duration": 10},
        {"id": "bbb", "title": "Second", "duration": 0},
    ]
