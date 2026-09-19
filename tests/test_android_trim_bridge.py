from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field

import pytest

from features.bili_pack.task import BiliPage
from features.yt_dlp_pack.task import YouTubeFile


def loadAdapter(pack: str):
    return importlib.import_module(f"features.{pack}.android")


@dataclass(kw_only=True)
class StubTask:
    packId: str
    files: list = field(default_factory=list)

    def update(self):
        pass


@pytest.fixture(scope="module")
def bili():
    return loadAdapter("bili_pack")


@pytest.fixture(scope="module")
def ytdlp():
    return loadAdapter("yt_dlp_pack")


def test_bili_file_fields_expose_the_trim_range(bili):
    task = StubTask(packId="bili", files=[BiliPage(index=1, relativePath="P1", startTime=30, endTime=90)])

    assert bili.fileFields(task) == {1: {"startTime": 30, "endTime": 90}}


def test_bili_trim_edits_land_on_the_page(bili):
    page = BiliPage(index=1, relativePath="P1", pagePart="P1")
    task = StubTask(packId="bili", files=[page])

    bili.applyFileEdits(task, {"trim": {"1": [30, 90]}})

    assert (page.startTime, page.endTime) == (30, 90)


def test_bili_title_edit_renames_the_page(bili):
    page = BiliPage(index=1, relativePath="P1", pagePart="P1")
    task = StubTask(packId="bili", files=[page])

    bili.applyFileEdits(task, {"titles": {"1": "新名字"}})

    assert page.pagePart == "新名字"


def test_bili_edits_without_trim_leave_the_range_alone(bili):
    page = BiliPage(index=1, relativePath="P1", startTime=30, endTime=90)
    task = StubTask(packId="bili", files=[page])

    bili.applyFileEdits(task, {"selected": ["1"]})

    assert (page.startTime, page.endTime) == (30, 90)


def test_ytdlp_trim_edits_land_on_the_file(ytdlp):
    file = YouTubeFile(index=1, relativePath="a.mp4")
    task = StubTask(packId="yt_dlp", files=[file])

    ytdlp.applyFileEdits(task, {"trim": {"1": [12, 34]}})

    assert (file.startTime, file.endTime) == (12, 34)


def test_packs_without_trim_fields_are_not_offered_trim():
    for pack in ("http_pack", "github_pack", "huggingface_pack", "bittorrent_pack"):
        module = loadAdapter(pack)
        assert getattr(module, "fileFields", None) is None, pack
