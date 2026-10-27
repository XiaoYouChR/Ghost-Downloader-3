from __future__ import annotations

import json
from pathlib import Path

import pytest

from bili_pack.parse import BiliUrl, buildFavoritePages, buildPages, parseBiliUrl

FAVORITE_SAMPLE = Path(__file__).parent.parent / "samples" / "bilibili_favorite.json"


def test_parse_bvid_link():
    biliUrl = parseBiliUrl("https://www.bilibili.com/video/BV1eugW6DEYT/")
    assert biliUrl.videoId == "BV1eugW6DEYT"
    assert biliUrl.seasonId == 0
    assert biliUrl.selectedPages is None


def test_parse_link_with_page_list():
    biliUrl = parseBiliUrl("https://www.bilibili.com/video/BV1eugW6DEYT/?p=1,3,5-7")
    assert biliUrl.videoId == "BV1eugW6DEYT"
    assert biliUrl.selectedPages == [1, 3, 5, 6, 7]


def test_parse_avid_link():
    biliUrl = parseBiliUrl("https://www.bilibili.com/video/av12345")
    assert biliUrl.videoId == "av12345"


def test_parse_favorite_links():
    assert parseBiliUrl("https://space.bilibili.com/437313511/favlist?fid=478029911").favoriteId == 478029911
    assert parseBiliUrl("https://www.bilibili.com/list/ml478029911").favoriteId == 478029911
    assert parseBiliUrl("https://www.bilibili.com/medialist/detail/ml478029911").favoriteId == 478029911
    collected = parseBiliUrl("https://space.bilibili.com/437313511/favlist?fid=1094155&ctype=21")
    assert (collected.favoriteId, collected.seasonId) == (0, 1094155)


def test_build_favorite_pages_skips_invalid_and_expands_pages():
    sample = json.loads(FAVORITE_SAMPLE.read_text(encoding="utf-8"))
    pages = buildFavoritePages(sample["medias"], sample["pageLists"])
    assert [p.bvid for p in pages] == ["BV1p3ivB8EZA", "BV1PW4y1G7WG"] + ["BV1sx411N7ms"] * 14
    assert pages[0].cid == 35163146510
    assert pages[0].episodeTitle == "【中配】为什么Rust教程总喜欢自我吹嘘？ Tsoding - Tsoding Highlights"
    assert [p.pagePart for p in pages[2:5]] == ["至少还有你", "好久不见", "隐形的翅膀"]
    assert all(p.selected for p in pages)


def test_parse_space_list_link():
    biliUrl = parseBiliUrl(
        "https://space.bilibili.com/1992978115/lists/4831253?type=season"
    )
    assert biliUrl.mid == 1992978115
    assert biliUrl.seasonId == 4831253
    assert biliUrl.videoId == ""
    assert biliUrl.selectedPages is None


def test_parse_space_collection_link():
    biliUrl = parseBiliUrl(
        "https://space.bilibili.com/1992978115/channel/collectiondetail?sid=4831253"
    )
    assert biliUrl.mid == 1992978115
    assert biliUrl.seasonId == 4831253


def test_parse_rejects_other_links():
    with pytest.raises(ValueError):
        parseBiliUrl("https://live.bilibili.com/123")


def buildPage(cid: int, page: int, part: str, duration: int = 10) -> dict:
    return {"cid": cid, "page": page, "part": part, "duration": duration}


def buildEpisode(bvid: str, title: str, pages: list[dict]) -> dict:
    return {
        "bvid": bvid,
        "title": title,
        "cid": pages[0]["cid"],
        "page": pages[0],
        "pages": pages,
        "arc": {"pic": f"http://i0.hdslb.com/bfs/{bvid}.jpg"},
    }


def buildSeasonView(currentBvid: str, extraSection: bool = False) -> dict:
    sections = [
        {
            "title": "正片",
            "episodes": [
                buildEpisode("BV1aaa", "第一集", [buildPage(11, 1, "p1")]),
                buildEpisode("BV2bbb", "第二集", [buildPage(21, 1, "上"), buildPage(22, 2, "下")]),
                buildEpisode("BV3ccc", "第三集", [buildPage(31, 1, "p1")]),
            ],
        }
    ]
    if extraSection:
        sections.append({
            "title": "花絮",
            "episodes": [buildEpisode("BV4ddd", "花絮1", [buildPage(41, 1, "p1")])],
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


def test_parse_video_selects_every_page():
    viewData = {
        "title": "三P稿件",
        "pic": "http://i0.hdslb.com/bfs/cover.jpg",
        "bvid": "BV1xxx",
        "pages": [
            buildPage(11, 1, "开场"),
            buildPage(12, 2, "正片"),
            buildPage(13, 3, "彩蛋"),
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


def test_parse_video_selects_linked_page():
    viewData = {
        "title": "三P稿件",
        "bvid": "BV1xxx",
        "pages": [buildPage(11, 1, "开场"), buildPage(12, 2, "正片"), buildPage(13, 3, "彩蛋")],
    }
    pages, _, _ = buildPages(viewData, BiliUrl(videoId="BV1xxx", selectedPages=[2]))
    assert [p.selected for p in pages] == [False, True, False]


def test_parse_season_selects_current_episode():
    viewData = buildSeasonView("BV2bbb")
    pages, title, coverUrl = buildPages(viewData, BiliUrl(videoId="BV2bbb"))
    assert title == "原神"
    assert coverUrl == "https://i0.hdslb.com/bfs/season.jpg"
    assert [p.bvid for p in pages] == ["BV1aaa", "BV2bbb", "BV2bbb", "BV3ccc"]
    assert [p.pageNumber for p in pages] == [1, 1, 2, 1]
    assert [p.index for p in pages] == [0, 1, 2, 3]
    assert [p.episodeTitle for p in pages] == ["第一集", "第二集", "第二集", "第三集"]
    assert [p.selected for p in pages] == [False, True, True, False]
    assert all(p.sectionTitle == "" for p in pages)
    assert pages[0].coverUrl == "https://i0.hdslb.com/bfs/BV1aaa.jpg"
    assert pages[1].coverUrl == pages[2].coverUrl == "https://i0.hdslb.com/bfs/BV2bbb.jpg"


def test_parse_season_selects_linked_page():
    viewData = buildSeasonView("BV2bbb")
    pages, _, _ = buildPages(viewData, BiliUrl(videoId="BV2bbb", selectedPages=[2]))
    assert [p.selected for p in pages] == [False, False, True, False]


def test_parse_season_link_selects_every_episode():
    viewData = buildSeasonView("BV1aaa")
    pages, _, _ = buildPages(viewData, BiliUrl(mid=1, seasonId=9))
    assert len(pages) == 4
    assert all(p.selected for p in pages)


def test_parse_season_names_its_sections():
    viewData = buildSeasonView("BV1aaa", extraSection=True)
    pages, _, _ = buildPages(viewData, BiliUrl(videoId="BV1aaa"))
    assert [p.sectionTitle for p in pages] == ["正片", "正片", "正片", "正片", "花絮"]


def test_parse_stream_url_in_either_key_style():
    from bili_pack.stream import toStreamUrl
    assert toStreamUrl({"base_url": "https://cdn.example/v"}) == "https://cdn.example/v"
    assert toStreamUrl({"baseUrl": "https://cdn.example/v"}) == "https://cdn.example/v"


def test_parse_video_without_audio():
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


def test_parse_uses_chosen_audio_quality():
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


def test_set_audio_quality_picks_dolby_and_hires_tracks():
    from pathlib import Path
    from bili_pack.stream import parseDash
    from bili_pack.task import BiliPage, BilibiliTask

    page = BiliPage(index=0, relativePath="p", _duration=10)
    parseDash(page, {
        "video": [{"id": 126, "codecid": 12, "bandwidth": 8000, "baseUrl": "https://dv"}],
        "audio": [{"id": 30280, "bandwidth": 192000, "baseUrl": "https://a192"}],
        "dolby": {"type": 2, "audio": [{"id": 30250, "bandwidth": 448000, "baseUrl": "https://atmos"}]},
        "flac": {"display": True, "audio": {"id": 30251, "bandwidth": 1000000, "baseUrl": "https://flac"}},
    }, qn=126, acceptQuality=[126])
    task = BilibiliTask(name="v.mp4", url="u", outputFolder=Path("."), files=[page], _baseName="v")
    assert page.audioUrl == "https://a192"

    def audioStepUrl():
        return next(s.url for s in task.steps if type(s).__name__ == "BilibiliAudioStep")

    task.setAudioQuality(30250)
    assert audioStepUrl() == "https://atmos"
    task.setAudioQuality(30251)
    assert audioStepUrl() == "https://flac"


async def test_probe_size_from_content_range(startServer):
    from aiohttp import web
    from bili_pack.stream import probeSize

    async def handler(request):
        return web.Response(
            status=206,
            body=b"x",
            headers={"Content-Range": "bytes 0-0/415000000", "Content-Length": "1"},
        )

    url = await startServer(handler)
    assert await probeSize(url, {}) == 415000000


async def test_probe_size_unknown_without_content_range(startServer):
    from aiohttp import web
    from bili_pack.stream import probeSize

    async def handler(request):
        return web.Response(status=200, body=b"x", headers={"Content-Length": "1"})

    url = await startServer(handler)
    assert await probeSize(url, {}) == 0


