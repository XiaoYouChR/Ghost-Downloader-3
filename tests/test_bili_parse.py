"""Bilibili URL and view → files.

Seam: parseBiliUrl, buildPages
"""
from __future__ import annotations

import pytest

from bili_pack.parse import BiliUrl, buildPages, parseBiliUrl
from bili_pack.stream import buildSize


class TestParseBiliUrl:

    def test_video_bvid(self):
        biliUrl = parseBiliUrl("https://www.bilibili.com/video/BV1eugW6DEYT/")
        assert biliUrl.videoId == "BV1eugW6DEYT"
        assert biliUrl.seasonId == 0
        assert biliUrl.selectedPages is None

    def test_video_page_spec(self):
        biliUrl = parseBiliUrl("https://www.bilibili.com/video/BV1eugW6DEYT/?p=1,3,5-7")
        assert biliUrl.videoId == "BV1eugW6DEYT"
        assert biliUrl.selectedPages == [1, 3, 5, 6, 7]

    def test_video_avid(self):
        biliUrl = parseBiliUrl("https://www.bilibili.com/video/av12345")
        assert biliUrl.videoId == "av12345"

    def test_space_lists(self):
        biliUrl = parseBiliUrl(
            "https://space.bilibili.com/1992978115/lists/4831253?type=season"
        )
        assert biliUrl.mid == 1992978115
        assert biliUrl.seasonId == 4831253
        assert biliUrl.videoId == ""
        assert biliUrl.selectedPages is None

    def test_space_collectiondetail(self):
        biliUrl = parseBiliUrl(
            "https://space.bilibili.com/1992978115/channel/collectiondetail?sid=4831253"
        )
        assert biliUrl.mid == 1992978115
        assert biliUrl.seasonId == 4831253

    def test_rejects_other_paths(self):
        with pytest.raises(ValueError):
            parseBiliUrl("https://live.bilibili.com/123")


def _page(cid: int, page: int, part: str, duration: int = 10) -> dict:
    return {"cid": cid, "page": page, "part": part, "duration": duration}


def _episode(bvid: str, title: str, pages: list[dict]) -> dict:
    return {
        "bvid": bvid,
        "title": title,
        "cid": pages[0]["cid"],
        "page": pages[0],
        "pages": pages,
        "arc": {"pic": f"http://i0.hdslb.com/bfs/{bvid}.jpg"},
    }


def _seasonView(currentBvid: str, extraSection: bool = False) -> dict:
    sections = [
        {
            "title": "正片",
            "episodes": [
                _episode("BV1aaa", "第一集", [_page(11, 1, "p1")]),
                _episode("BV2bbb", "第二集", [_page(21, 1, "上"), _page(22, 2, "下")]),
                _episode("BV3ccc", "第三集", [_page(31, 1, "p1")]),
            ],
        }
    ]
    if extraSection:
        sections.append({
            "title": "花絮",
            "episodes": [_episode("BV4ddd", "花絮1", [_page(41, 1, "p1")])],
        })
    current = next(e for s in sections for e in s["episodes"] if e["bvid"] == currentBvid)
    return {
        "title": current["title"],
        "pic": "http://i0.hdslb.com/bfs/video.jpg",
        "bvid": currentBvid,
        "pages": current["pages"],
        "ugc_season": {
            "id": 9,
            "title": "原神",
            "cover": "http://i0.hdslb.com/bfs/season.jpg",
            "sections": sections,
        },
    }


class TestBuildPages:

    def test_video_pages_all_selected(self):
        viewData = {
            "title": "三P稿件",
            "pic": "http://i0.hdslb.com/bfs/cover.jpg",
            "bvid": "BV1xxx",
            "pages": [
                _page(11, 1, "开场"),
                _page(12, 2, "正片"),
                _page(13, 3, "彩蛋"),
            ],
        }
        pages, title, coverUrl = buildPages(viewData, BiliUrl(videoId="BV1xxx"))
        assert title == "三P稿件"
        assert coverUrl == "https://i0.hdslb.com/bfs/cover.jpg"
        assert [p.pageNumber for p in pages] == [1, 2, 3]
        assert [p.cid for p in pages] == [11, 12, 13]
        assert [p.pagePart for p in pages] == ["开场", "正片", "彩蛋"]
        assert [p.index for p in pages] == [0, 1, 2]
        assert all(p.selected for p in pages)
        assert all(p.bvid == "BV1xxx" for p in pages)
        assert all(p.episodeTitle == "" for p in pages)

    def test_video_pages_honors_p(self):
        viewData = {
            "title": "三P稿件",
            "bvid": "BV1xxx",
            "pages": [_page(11, 1, "开场"), _page(12, 2, "正片"), _page(13, 3, "彩蛋")],
        }
        pages, _, _ = buildPages(viewData, BiliUrl(videoId="BV1xxx", selectedPages=[2]))
        assert [p.selected for p in pages] == [False, True, False]

    def test_season_selects_current_episode(self):
        viewData = _seasonView("BV2bbb")
        pages, title, coverUrl = buildPages(viewData, BiliUrl(videoId="BV2bbb"))
        assert title == "原神"
        assert coverUrl == "https://i0.hdslb.com/bfs/season.jpg"
        assert [p.bvid for p in pages] == ["BV1aaa", "BV2bbb", "BV2bbb", "BV3ccc"]
        assert [p.pageNumber for p in pages] == [1, 1, 2, 1]
        assert [p.index for p in pages] == [0, 1, 2, 3]
        assert [p.episodeTitle for p in pages] == ["第一集", "第二集", "第二集", "第三集"]
        assert [p.selected for p in pages] == [False, True, True, False]
        assert all(p.sectionTitle == "" for p in pages)
        assert pages[1].relativePath == "第二集 - P1"
        assert pages[2].relativePath == "第二集 - P2"
        assert pages[0].coverUrl == "https://i0.hdslb.com/bfs/BV1aaa.jpg"
        assert pages[1].coverUrl == pages[2].coverUrl == "https://i0.hdslb.com/bfs/BV2bbb.jpg"

    def test_season_honors_p_on_current_episode(self):
        viewData = _seasonView("BV2bbb")
        pages, _, _ = buildPages(viewData, BiliUrl(videoId="BV2bbb", selectedPages=[2]))
        assert [p.selected for p in pages] == [False, False, True, False]

    def test_season_url_selects_all(self):
        viewData = _seasonView("BV1aaa")
        pages, _, _ = buildPages(viewData, BiliUrl(mid=1, seasonId=9))
        assert len(pages) == 4
        assert all(p.selected for p in pages)

    def test_season_section_labels_when_multiple(self):
        viewData = _seasonView("BV1aaa", extraSection=True)
        pages, _, _ = buildPages(viewData, BiliUrl(videoId="BV1aaa"))
        assert [p.sectionTitle for p in pages] == ["正片", "正片", "正片", "正片", "花絮"]


def test_toStreamUrl_accepts_snake_case():
    from bili_pack.stream import toStreamUrl
    assert toStreamUrl({"base_url": "https://cdn.example/v"}) == "https://cdn.example/v"
    assert toStreamUrl({"baseUrl": "https://cdn.example/v"}) == "https://cdn.example/v"


def test_parseDash_allows_video_only():
    from bili_pack.stream import parseDash
    from bili_pack.task import BiliPage

    page = BiliPage(index=0, relativePath="p", _duration=10)
    parseDash(page, {
        "video": [{"id": 80, "codecid": 7, "bandwidth": 8000, "base_url": "https://v"}],
        "audio": None,
    }, qn=80, acceptQuality=[80])
    assert page.videoUrl == "https://v"
    assert page.audioUrl == ""
    assert page.audioSize == 0

    from pathlib import Path
    from bili_pack.task import BilibiliTask
    task = BilibiliTask(
        name="v.mp4", url="u", outputFolder=Path("."),
        files=[page], _baseName="v",
    )
    assert task.hasAudio is False
    task.update()
    assert not any(type(s).__name__ == "BilibiliAudioStep" for s in task.steps)


def test_parseDash_honors_audioQn():
    from bili_pack.stream import parseDash
    from bili_pack.task import BiliPage

    page = BiliPage(index=0, relativePath="p", _duration=10)
    parseDash(page, {
        "video": [{"id": 80, "codecid": 7, "bandwidth": 8000, "baseUrl": "https://v"}],
        "audio": [
            {"id": 30216, "bandwidth": 64000, "baseUrl": "https://a64"},
            {"id": 30280, "bandwidth": 192000, "baseUrl": "https://a192"},
        ],
    }, qn=80, acceptQuality=[80], audioQn=30280)
    assert page.audioUrl == "https://a192"


def test_buildSize_from_bandwidth_and_duration():
    assert buildSize({"bandwidth": 8000}, 10) == 10000
    assert buildSize(None, 10) == 0
    assert buildSize({"bandwidth": 8000}, 0) == 0


async def test_probeSize_reads_content_range(server):
    from aiohttp import web
    from bili_pack.stream import probeSize

    async def handler(request):
        return web.Response(
            status=206,
            body=b"x",
            headers={"Content-Range": "bytes 0-0/415000000", "Content-Length": "1"},
        )

    url = await server(handler)
    assert await probeSize(url, {}) == 415000000


async def test_probeSize_returns_zero_without_range(server):
    from aiohttp import web
    from bili_pack.stream import probeSize

    async def handler(request):
        return web.Response(status=200, body=b"x", headers={"Content-Length": "1"})

    url = await server(handler)
    assert await probeSize(url, {}) == 0


async def test_audio_step_binds_url_already_on_page(tmp_path, monkeypatch):
    from bili_pack.task import BiliPage, BilibiliAudioStep, BilibiliTask, HttpTaskStep

    page = BiliPage(
        index=0,
        relativePath="ep",
        audioUrl="https://example.com/a.m4s",
        videoUrl="https://example.com/v.m4s",
        audioSize=8,
        headers={"referer": "https://www.bilibili.com"},
    )
    task = BilibiliTask(
        name="合集.mp4",
        url="https://www.bilibili.com/video/BV1",
        outputFolder=tmp_path,
        files=[page],
        _baseName="合集",
    )
    step = BilibiliAudioStep(stepIndex=1, fileIndex=0, url="", fileSize=0)
    step._bindTask(task)

    async def fakeProbe(url, headers=None):
        assert url == "https://example.com/a.m4s"
        return 8

    async def fakeRun(self, reportSpeed, waitForSpeedLimit):
        assert self.url == "https://example.com/a.m4s"

    monkeypatch.setattr("bili_pack.task.probeSize", fakeProbe)
    monkeypatch.setattr(HttpTaskStep, "run", fakeRun)
    await step.run(lambda n: None, lambda: None)
    assert step.url == "https://example.com/a.m4s"


def test_update_only_for_selected():
    from pathlib import Path
    from bili_pack.task import BiliPage, BilibiliTask

    files = [
        BiliPage(
            index=i,
            relativePath=f"p{i}",
            episodeTitle=f"集{i // 2}",
            bvid=f"BV{i // 2}",
            selected=i < 2,
        )
        for i in range(4)
    ]
    task = BilibiliTask(
        name="合集.mp4",
        url="https://www.bilibili.com/video/BV1",
        outputFolder=Path("."),
        files=files,
        _baseName="合集",
    )
    task.update()
    assert {s.fileIndex for s in task.steps if s.fileIndex is not None} == {0, 1}

    task.setSelection({0, 1, 2})
    assert {s.fileIndex for s in task.steps if s.fileIndex is not None} == {0, 1, 2}

    task.setSelection({0})
    assert {s.fileIndex for s in task.steps if s.fileIndex is not None} == {0, 1, 2}

    task.update()
    assert {s.fileIndex for s in task.steps if s.fileIndex is not None} == {0}


def test_seasonSummary_one_episode():
    from pathlib import Path
    from bili_pack.task import BiliPage, BilibiliTask

    files = [
        BiliPage(index=0, relativePath="a", episodeTitle="游戏王5DS", bvid="BV1", selected=True),
        BiliPage(index=1, relativePath="b", episodeTitle="棋魂", bvid="BV2", selected=False),
    ]
    task = BilibiliTask(
        name="各种番.mp4",
        url="u",
        outputFolder=Path("."),
        files=files,
        _baseName="各种番",
    )
    assert [[p.bvid for p in g] for g in task.episodeGroups()] == [["BV1"], ["BV2"]]
    assert task.seasonSummary() == "1/2 集"

    files[0].selected = False
    assert task.seasonSummary() == "0/2 集"

    files[0].selected = True
    files[1].selected = True
    assert task.seasonSummary() == "2/2 集"


def test_cover_steps_season_and_selected_episodes():
    from pathlib import Path
    from bili_pack.task import BiliPage, BilibiliTask

    files = [
        BiliPage(
            index=0, relativePath="a", episodeTitle="游戏王5DS", bvid="BV1",
            selected=True, coverUrl="https://i0.hdslb.com/bfs/ep1.jpg",
        ),
        BiliPage(
            index=1, relativePath="b", episodeTitle="棋魂", bvid="BV2",
            selected=False, coverUrl="https://i0.hdslb.com/bfs/ep2.jpg",
        ),
    ]
    task = BilibiliTask(
        name="各种番.mp4",
        url="u",
        outputFolder=Path("."),
        files=files,
        _baseName="各种番",
        coverUrl="https://i0.hdslb.com/bfs/season.jpg",
        isCoverEnabled=True,
    )
    task.update()
    coverFiles = [getattr(s, "outputFile", "") for s in task.steps if getattr(s, "outputFile", "")]
    assert any(p.endswith("各种番.jpg") for p in coverFiles)
    assert any(p.endswith("各种番 - 游戏王5DS.jpg") for p in coverFiles)
    assert not any("棋魂" in p for p in coverFiles)

    task.setSelection({0, 1})
    coverFiles = [getattr(s, "outputFile", "") for s in task.steps if getattr(s, "outputFile", "")]
    assert any(p.endswith("各种番 - 棋魂.jpg") for p in coverFiles)


def test_setEpisodeTitle_updates_relativePath():
    from bili_pack.task import BiliPage, setEpisodeTitle, setPagePart

    pages = [
        BiliPage(index=0, relativePath="旧 - P1", episodeTitle="旧",
                 bvid="BV1", pageNumber=1, pagePart="上"),
        BiliPage(index=1, relativePath="旧 - P2", episodeTitle="旧",
                 bvid="BV1", pageNumber=2, pagePart="下"),
    ]
    setEpisodeTitle(pages, "游戏王")
    assert [p.episodeTitle for p in pages] == ["游戏王", "游戏王"]
    assert [p.relativePath for p in pages] == ["游戏王 - P1", "游戏王 - P2"]

    setPagePart(pages[0], "第1话")
    assert pages[0].pagePart == "第1话"
    assert pages[0].relativePath == "游戏王 - P1"


def test_updateSuffixes_after_rename_and_trim():
    from pathlib import Path
    from bili_pack.task import BiliPage, BilibiliTask

    files = [
        BiliPage(index=0, relativePath="a", episodeTitle="旧名", bvid="BV1", selected=True),
        BiliPage(index=1, relativePath="b", episodeTitle="另一集", bvid="BV2", selected=False),
    ]
    task = BilibiliTask(
        name="各种番.mp4", url="u", outputFolder=Path("."),
        files=files, _baseName="各种番",
    )
    task.update()
    suffixes = {s.pageSuffix for s in task.steps if getattr(s, "pageSuffix", None)}
    assert suffixes == {" - 旧名"}

    files[0].episodeTitle = "新名"
    files[0].startTime = 10
    files[0].endTime = 20
    task.updateSuffixes()
    suffixes = {s.pageSuffix for s in task.steps if getattr(s, "pageSuffix", None)}
    assert suffixes == {" - 新名 [00m10s-00m20s]"}


def test_setTimeRanges_only_touches_listed_pages():
    from bili_pack.task import BiliPage, setTimeRanges

    pages = [
        BiliPage(index=0, relativePath="a", startTime=1, endTime=2),
        BiliPage(index=1, relativePath="b", startTime=3, endTime=4),
        BiliPage(index=2, relativePath="c", startTime=5, endTime=6),
    ]
    setTimeRanges(pages, {0: (10, 20), 1: (0, 0)})
    assert (pages[0].startTime, pages[0].endTime) == (10, 20)
    assert (pages[1].startTime, pages[1].endTime) == (0, 0)
    assert (pages[2].startTime, pages[2].endTime) == (5, 6)
