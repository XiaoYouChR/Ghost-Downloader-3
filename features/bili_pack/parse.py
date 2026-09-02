from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from .task import BiliPage


@dataclass(frozen=True)
class BiliUrl:
    videoId: str = ""
    mid: int = 0
    seasonId: int = 0
    selectedPages: list[int] | None = None


def parseBiliUrl(url: str) -> BiliUrl:
    parsed = urlparse(url)
    videoIdMatch = re.match(r"/video/(BV[a-zA-Z0-9]+|av\d+)", parsed.path)
    if videoIdMatch:
        return BiliUrl(videoId=videoIdMatch.group(1), selectedPages=parsePageSpec(parsed.query))

    listsMatch = re.match(r"/(\d+)/lists/(\d+)", parsed.path)
    if listsMatch:
        return BiliUrl(mid=int(listsMatch.group(1)), seasonId=int(listsMatch.group(2)))

    detailMatch = re.match(r"/(\d+)/channel/collectiondetail", parsed.path)
    if detailMatch:
        sid = parse_qs(parsed.query).get("sid", [""])[0]
        if sid.isdigit():
            return BiliUrl(mid=int(detailMatch.group(1)), seasonId=int(sid))

    raise ValueError("不是有效的 Bilibili 视频链接")


def buildPages(viewData: dict, biliUrl: BiliUrl) -> tuple[list[BiliPage], str, str]:
    season = viewData.get("ugc_season") or None
    if season:
        title = str(season.get("title") or "").strip() or "bilibili_video"
        coverUrl = toHttps(season.get("cover") or viewData.get("pic") or "")
        pages = buildSeasonPages(season)
        setSeasonSelection(pages, biliUrl, str(viewData.get("bvid") or biliUrl.videoId))
    else:
        title = str(viewData.get("title", "")).strip() or "bilibili_video"
        coverUrl = toHttps(viewData.get("pic") or "")
        bvid = str(viewData.get("bvid") or biliUrl.videoId)
        pages = [buildPage(index, raw, bvid=bvid) for index, raw in enumerate(viewData.get("pages") or [])]
        setVideoSelection(pages, biliUrl.selectedPages)

    return pages, title, coverUrl


def toHttps(url: str) -> str:
    url = str(url or "").strip()
    if url.startswith("http://"):
        return "https://" + url[7:]
    return url


def buildSeasonPages(season: dict) -> list[BiliPage]:
    sections = list(season.get("sections") or [])
    hasManySections = len(sections) > 1
    pages: list[BiliPage] = []
    for section in sections:
        sectionTitle = str(section.get("title") or "").strip() if hasManySections else ""
        for episode in section.get("episodes") or []:
            bvid = str(episode.get("bvid") or "")
            episodeTitle = str(episode.get("title") or "").strip()
            rawPages = list(episode.get("pages") or [])
            if not rawPages and episode.get("page"):
                rawPages = [episode["page"]]
            coverUrl = episodeCover(episode)
            for raw in rawPages:
                pages.append(buildPage(
                    len(pages), raw, bvid=bvid,
                    episodeTitle=episodeTitle, sectionTitle=sectionTitle,
                    coverUrl=coverUrl,
                ))
    byBvid: dict[str, list[BiliPage]] = {}
    for page in pages:
        byBvid.setdefault(page.bvid, []).append(page)
    for group in byBvid.values():
        multi = len(group) > 1
        for page in group:
            if not page.episodeTitle:
                continue
            page.relativePath = (
                f"{page.episodeTitle} - P{page.pageNumber}" if multi else page.episodeTitle
            )
    return pages


def setVideoSelection(pages: list[BiliPage], selectedPages: list[int] | None) -> None:
    if selectedPages is None:
        selectedPages = [page.pageNumber for page in pages]
    selectedSet = set(selectedPages)
    for page in pages:
        page.selected = page.pageNumber in selectedSet


def setSeasonSelection(pages: list[BiliPage], biliUrl: BiliUrl, currentBvid: str) -> None:
    if biliUrl.seasonId:
        for page in pages:
            page.selected = True
        return
    wanted = set(biliUrl.selectedPages) if biliUrl.selectedPages is not None else None
    for page in pages:
        if page.bvid != currentBvid:
            page.selected = False
        elif wanted is None:
            page.selected = True
        else:
            page.selected = page.pageNumber in wanted


def episodeCover(episode: dict) -> str:
    arc = episode.get("arc") or {}
    return toHttps(str(arc.get("pic") or episode.get("cover") or episode.get("pic") or ""))


def buildPage(
    index: int, raw: dict, *, bvid: str, episodeTitle: str = "",
    sectionTitle: str = "", coverUrl: str = "",
) -> BiliPage:
    pageNumber = int(raw.get("page") or index + 1)
    pagePart = str(raw.get("part", "")).strip()
    return BiliPage(
        index=index,
        relativePath=pagePart or f"P{pageNumber}",
        cid=int(raw["cid"]),
        pagePart=pagePart,
        pageNumber=pageNumber,
        bvid=bvid,
        episodeTitle=episodeTitle,
        sectionTitle=sectionTitle,
        coverUrl=coverUrl,
        _duration=int(raw.get("duration") or 0),
    )


def parsePageSpec(query: str) -> list[int] | None:
    pageParam = parse_qs(query).get("p", [""])[0].strip()
    if not pageParam:
        return None
    selected: list[int] = []
    for part in pageParam.split(","):
        part = part.strip()
        if "-" in part:
            start, end = map(int, part.split("-", 1))
            if start > end:
                start, end = end, start
            selected.extend(range(start, end + 1))
        else:
            selected.append(int(part))
    return selected
