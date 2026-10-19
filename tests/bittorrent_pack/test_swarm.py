from __future__ import annotations

from types import SimpleNamespace

import libtorrent as lt

from features.bittorrent_pack.swarm import (
    TrackerStatus, toEndpointText, toErrorText, toPeerFlags, toSourceTrackers, toTorrentMeta, toTracker,
)

NO_ERROR = {"category": "system", "value": 0}


def buildEntry(fails=0, startSent=False, updating=False, complete=-1, incomplete=-1, message="", error=NO_ERROR):
    return {"fails": fails, "start_sent": startSent, "updating": updating, "scrape_complete": complete,
            "scrape_incomplete": incomplete, "message": message, "last_error": error}


def buildTracker(*endpoints):
    return {"url": "udp://tracker.example:1337", "fails": 2, "scrape_complete": -1,
            "endpoints": [{"info_hashes": [entry, buildEntry()]} for entry in endpoints]}


def test_to_tracker_works_when_one_endpoint_works():
    tracker = buildTracker(
        buildEntry(fails=2, error={"category": "libtorrent", "value": 180}),
        buildEntry(startSent=True, complete=285, incomplete=36),
        buildEntry(fails=2, error={"category": "system", "value": 49}),
    )

    info = toTracker(tracker)

    assert (info.status, info.seeds, info.leeches, info.message) == (TrackerStatus.WORKING, 285, 36, "")


def test_to_tracker_shows_first_error():
    tracker = buildTracker(buildEntry(fails=2, error={"category": "libtorrent", "value": 180}))

    info = toTracker(tracker)

    assert info.status == TrackerStatus.ERROR
    assert info.message == "skipping tracker announce (unreachable)"


def test_to_tracker_prefers_message_over_error_code():
    tracker = buildTracker(buildEntry(fails=1, message="Operation canceled", error={"category": "system", "value": 89}))

    assert toTracker(tracker).message == "Operation canceled"


def test_to_tracker_updating_and_not_contacted():
    assert toTracker(buildTracker(buildEntry(updating=True))).status == TrackerStatus.UPDATING
    assert toTracker(buildTracker(buildEntry())).status == TrackerStatus.NOT_CONTACTED


def test_to_error_text_for_unknown_category():
    assert toErrorText({"category": "asio.netdb", "value": 1}) == "asio.netdb 1"


def test_to_peer_flags_like_qbittorrent():
    assert toPeerFlags(144435, source=3) == "D S H"
    assert toPeerFlags(170, source=4) == "X"


def test_to_endpoint_brackets_ipv6():
    assert toEndpointText(("2001:db8::1", 6881)) == "[2001:db8::1]:6881"
    assert toEndpointText(("1.2.3.4", 6881)) == "1.2.3.4:6881"


def test_to_sources_counts_peers_and_respects_private():
    peers = [SimpleNamespace(source=lt.peer_info.dht), SimpleNamespace(source=lt.peer_info.dht | lt.peer_info.pex)]

    dht, pex, lsd = toSourceTrackers(peers, isDhtEnabled=True, isLsdEnabled=False, isPrivate=False)
    assert (dht.status, dht.peers) == (TrackerStatus.WORKING, 2)
    assert (pex.status, pex.peers) == (TrackerStatus.WORKING, 1)
    assert lsd.status == TrackerStatus.DISABLED

    assert all(row.status == TrackerStatus.DISABLED
               for row in toSourceTrackers(peers, isDhtEnabled=True, isLsdEnabled=True, isPrivate=True))


def test_to_torrent_details(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"x" * 40000)
    torrent = lt.create_torrent(lt.list_files(str(tmp_path / "a.bin")), piece_size=16384)
    torrent.set_comment("hello")
    torrent.set_creator("ghost")
    torrent.set_priv(True)
    lt.set_piece_hashes(torrent, str(tmp_path))

    meta = toTorrentMeta(lt.bencode(torrent.generate()))

    assert (meta.comment, meta.creator, meta.pieceCount, meta.pieceSize, meta.isPrivate) == ("hello", "ghost", 3, 16384, True)
    assert len(meta.infoHashV1) == 40
