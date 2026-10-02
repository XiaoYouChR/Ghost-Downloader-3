import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote

from .errors import Error, ErrorCode

HASH_PATTERN = re.compile(r"[0-9A-Fa-f]{32}")
SIZE_PATTERN = re.compile(r"[0-9]+")
SCHEME = "ed2k://"
# eMule's MAX_EMULE_FILE_SIZE
MAX_SIZE = 256 << 30


@dataclass(frozen=True, slots=True)
class Link:
    name: str
    size: int
    hash: str

    @staticmethod
    def parse(text: str) -> "Link":
        text = text.strip()
        if text[: len(SCHEME)].lower() != SCHEME:
            raise Error(ErrorCode.INVALID_LINK, f"not an eD2k link: {text}")
        body = text[len(SCHEME) :]
        # Browsers may encode every separator, as aMule's TextClient.cpp:537-540
        # repairs. Only such a link is decoded: in a plain link %7C is part of
        # the name.
        if body[:3].lower() == "%7c":
            body = body.replace("%7C", "|").replace("%7c", "|")
        fields = body.split("|")
        if len(fields) < 5 or fields[0] != "" or fields[1].lower() != "file":
            raise Error(ErrorCode.INVALID_LINK, f"not an eD2k file link: {text}")
        name, size, hash = unquote(fields[2]), fields[3], fields[4]
        if not name:
            raise Error(ErrorCode.INVALID_LINK, f"link has no name: {text}")
        if not SIZE_PATTERN.fullmatch(size) or not 0 < int(size) <= MAX_SIZE:
            raise Error(ErrorCode.INVALID_LINK, f"link has an invalid size: {text}")
        if not HASH_PATTERN.fullmatch(hash):
            raise Error(ErrorCode.INVALID_LINK, f"link has an invalid hash: {text}")
        return Link(name, int(size), hash.upper())

    def __str__(self) -> str:
        return f"ed2k://|file|{quote(self.name, safe='')}|{self.size}|{self.hash}|/"


@dataclass(frozen=True, slots=True)
class Settings:
    port: int = 0
    enableKad: bool = True
    enableUpnp: bool = True
    serverLists: tuple[Path, ...] = ()
    nodeLists: tuple[Path, ...] = ()
    traceFile: Path | None = None
    downloadRateLimit: int = 0
    uploadRateLimit: int = 0


@dataclass(frozen=True, slots=True)
class Source:
    """One source in Progress.sources; docs/protocol.md "progress" describes the fields."""

    address: str
    software: str
    status: str
    rank: int
    downloadRate: int
    channel: str


@dataclass(frozen=True, slots=True)
class Progress:
    hash: str
    size: int
    received: int
    downloadRate: int
    uploadRate: int
    uploaded: int
    peers: int
    activePeers: int
    heldSources: int
    heldUntil: int
    sources: tuple[Source, ...]


@dataclass(frozen=True, slots=True)
class Network:
    isServerConnected: bool
    isHighId: bool
    isKadFirewalled: bool
    kadNodes: int
    isBehindCarrierNat: bool
