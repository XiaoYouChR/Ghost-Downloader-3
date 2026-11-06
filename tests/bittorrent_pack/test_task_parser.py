from __future__ import annotations

import libtorrent as lt
import pytest
from aiohttp import web

from app.models.pack import PackServices
from app.models.task import TaskError, TaskOptions
from bittorrent_pack.config import bittorrentConfig
from bittorrent_pack.pack import BitTorrentPack
from bittorrent_pack.session import btSession
from bittorrent_pack.task import BTTask
from http_pack.pack import HttpPack
from http_pack.task import HttpTask
from tests.helpers import buildRangeHandler


@pytest.fixture(params=["desktop", "android"])
def engine(startEngine, request):
    return startEngine(request.param)


@pytest.fixture
def features(engine, monkeypatch):
    monkeypatch.setattr(bittorrentConfig.autoRefreshWebTrackers, "value", False)
    services = PackServices(coroutineRunner=engine.coroutineRunner, speedMeter=engine.speedMeter)
    for pack in (HttpPack(services), BitTorrentPack(services)):
        engine.featureService.register(pack)
    return engine.featureService


def buildTorrent(folder) -> bytes:
    (folder / "movie.mkv").write_bytes(b"x" * 40_000)
    torrent = lt.create_torrent(lt.list_files(str(folder / "movie.mkv")), piece_size=16384)
    lt.set_piece_hashes(torrent, str(folder))
    return lt.bencode(torrent.generate())


def buildNamedHandler(content: bytes, name: str):
    rangeHandler = buildRangeHandler(content)

    async def handler(request: web.Request) -> web.Response:
        response = await rangeHandler(request)
        response.headers["Content-Disposition"] = f'attachment; filename="{name}"'
        return response
    return handler


async def test_parse_online_torrent_adds_its_files(features, startServer, tmp_path):
    url = await startServer(buildNamedHandler(buildTorrent(tmp_path), "movie.torrent"))

    task = await features.parse(TaskOptions(url=f"{url}?id=1"))

    assert isinstance(task, BTTask)
    assert task.name == "movie.mkv"
    assert task.url == f"{url}?id=1"


async def test_parse_invalid_online_torrent_adds_plain_file(features, startServer):
    url = await startServer(buildNamedHandler(b"not a torrent" * 10, "movie.torrent"))

    task = await features.parse(TaskOptions(url=url))

    assert isinstance(task, HttpTask)
    assert task.name == "movie.torrent"


async def test_relink_torrent_to_http_task_rejects(engine, features, startServer, tmp_path):
    task = await features.parse(TaskOptions(url=await startServer(buildRangeHandler(b"x" * 100))))
    btTask = await features.parse(TaskOptions(url=await startServer(buildNamedHandler(buildTorrent(tmp_path), "movie.torrent"))))

    with pytest.raises(TaskError):
        engine.taskService.edit(task, {}, btTask)


@pytest.mark.parametrize("infoHash", ["ab" * 20, "AB" * 20, "abcdefgh234567ab" * 2, "ABCDEFGH234567AB" * 2])
def test_match_bare_info_hash(features, infoHash):
    assert features.match(f"  {infoHash} ")


@pytest.mark.parametrize("text", ["ab" * 19, "ab" * 21, "g" + "a" * 39, "abcdefgh234567ab" * 2 + "c", "ab" * 32])
def test_match_rejects_text_that_is_not_info_hash(features, text):
    assert not features.match(text)


async def test_parse_bare_info_hash_as_magnet_link(features, monkeypatch, tmp_path):
    infoHash = "AB" * 20
    torrentBytes = buildTorrent(tmp_path)
    fetchedUrls = []

    async def fetchMetadata(magnetUri, trackers):
        fetchedUrls.append(magnetUri)
        return torrentBytes
    monkeypatch.setattr(btSession, "fetchMetadata", fetchMetadata)

    task = await features.parse(TaskOptions(url=f" {infoHash} "))

    assert isinstance(task, BTTask)
    assert task.url == f"magnet:?xt=urn:btih:{infoHash}"
    assert task.sourceType == "magnet"
    assert fetchedUrls == [task.url]
