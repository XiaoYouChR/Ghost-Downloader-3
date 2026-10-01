from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import libtorrent as lt

class TrackerStatus(StrEnum):
    WORKING = "working"
    UPDATING = "updating"
    NOT_CONTACTED = "notContacted"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass(frozen=True)
class TorrentMeta:
    infoHashV1: str
    infoHashV2: str
    comment: str
    creator: str
    createdAt: int
    pieceCount: int
    pieceSize: int
    isPrivate: bool


@dataclass(frozen=True)
class SwarmInfo:
    seeds: int
    totalSeeds: int
    peers: int
    totalPeers: int
    distributedCopies: float
    totalUpload: int
    totalDownload: int
    nextAnnounceSeconds: int


@dataclass(frozen=True)
class PeerInfo:
    host: str
    port: int
    client: str
    flags: str
    progress: float
    downloadRate: int
    uploadRate: int


@dataclass(frozen=True)
class TrackerInfo:
    url: str
    status: TrackerStatus
    seeds: int
    leeches: int
    peers: int
    message: str


def toTorrentMeta(torrentData: bytes) -> TorrentMeta:
    info = lt.torrent_info(torrentData)
    hashes = info.info_hashes()
    return TorrentMeta(
        infoHashV1=str(hashes.v1) if hashes.has_v1() else "",
        infoHashV2=str(hashes.v2) if hashes.has_v2() else "",
        comment=info.comment(),
        creator=info.creator(),
        createdAt=info.creation_date(),
        pieceCount=info.num_pieces(),
        pieceSize=info.piece_length(),
        isPrivate=info.priv(),
    )


def toSwarmInfo(status) -> SwarmInfo:
    return SwarmInfo(
        seeds=status.num_seeds,
        totalSeeds=status.num_complete if status.num_complete >= 0 else status.list_seeds,
        peers=status.num_peers - status.num_seeds,
        totalPeers=status.num_incomplete if status.num_incomplete >= 0 else status.list_peers - status.list_seeds,
        distributedCopies=status.distributed_copies,
        totalUpload=status.all_time_upload,
        totalDownload=status.all_time_download,
        nextAnnounceSeconds=int(status.next_announce.total_seconds()),
    )


def toEndpointText(ip: tuple[str, int]) -> str:
    host, port = ip
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


def toPeerFlags(flags: int, source: int) -> str:
    info = lt.peer_info
    isInteresting = flags & info.interesting
    isChoked = flags & info.choked
    isRemoteInterested = flags & info.remote_interested
    isRemoteChoked = flags & info.remote_choked
    letters = []
    if isInteresting:
        letters.append("d" if isRemoteChoked else "D")
    if isRemoteInterested:
        letters.append("u" if isChoked else "U")
    if not isRemoteChoked and not isInteresting:
        letters.append("K")
    if not isChoked and not isRemoteInterested:
        letters.append("?")
    if flags & info.optimistic_unchoke:
        letters.append("O")
    if flags & info.snubbed:
        letters.append("S")
    if not flags & info.outgoing_connection:
        letters.append("I")
    if source & info.dht:
        letters.append("H")
    if source & info.pex:
        letters.append("X")
    if source & info.lsd:
        letters.append("L")
    if flags & (info.rc4_encrypted | info.plaintext_encrypted):
        letters.append("E")
    return " ".join(letters)


def toPeers(rawPeers) -> tuple[PeerInfo, ...]:
    return tuple(
        PeerInfo(
            host=peer.ip[0],
            port=peer.ip[1],
            client=peer.client.decode("utf-8", "replace"),
            flags=toPeerFlags(peer.flags, peer.source),
            progress=peer.progress,
            downloadRate=peer.down_speed,
            uploadRate=peer.up_speed,
        )
        for peer in rawPeers
    )


ERROR_CATEGORIES = {
    category.name(): category
    for category in (
        lt.libtorrent_category(), lt.system_category(), lt.generic_category(), lt.http_category(),
        lt.upnp_category(), lt.bdecode_category(), lt.socks_category(), lt.i2p_category(),
    )
}


def toErrorText(error: dict) -> str:
    category = ERROR_CATEGORIES.get(error["category"])
    return category.message(error["value"]) if category else f"{error['category']} {error['value']}"


def toTracker(rawTracker: dict) -> TrackerInfo:
    entries = [entry for endpoint in rawTracker["endpoints"] for entry in endpoint["info_hashes"]]
    working = [entry for entry in entries if entry["start_sent"] and entry["fails"] == 0]
    failed = [entry for entry in entries if entry["fails"] > 0]
    if any(entry["updating"] for entry in entries):
        status = TrackerStatus.UPDATING
    elif working:
        status = TrackerStatus.WORKING
    elif failed:
        status = TrackerStatus.ERROR
    else:
        status = TrackerStatus.NOT_CONTACTED
    if working:
        message = next((entry["message"] for entry in working if entry["message"]), "")
    elif failed:
        entry = failed[0]
        message = entry["message"] or toErrorText(entry["last_error"])
    else:
        message = ""
    return TrackerInfo(
        url=rawTracker["url"],
        status=status,
        seeds=max((entry["scrape_complete"] for entry in entries), default=-1),
        leeches=max((entry["scrape_incomplete"] for entry in entries), default=-1),
        peers=-1,
        message=message,
    )


def toSourceTrackers(rawPeers, isDhtEnabled: bool, isLsdEnabled: bool, isPrivate: bool) -> tuple[TrackerInfo, ...]:
    sources = [peer.source for peer in rawPeers]

    def build(name: str, flag: int, isEnabled: bool) -> TrackerInfo:
        status = TrackerStatus.WORKING if isEnabled and not isPrivate else TrackerStatus.DISABLED
        return TrackerInfo(name, status, -1, -1, sum(1 for source in sources if source & flag), "")

    return (
        build("[DHT]", lt.peer_info.dht, isDhtEnabled),
        build("[PeX]", lt.peer_info.pex, True),
        build("[LSD]", lt.peer_info.lsd, isLsdEnabled),
    )
