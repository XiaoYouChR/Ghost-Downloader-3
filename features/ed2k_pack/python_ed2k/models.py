from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class TransferState(StrEnum):
    LOADING_RESUME_DATA = "LOADING_RESUME_DATA"
    DOWNLOADING = "DOWNLOADING"
    PAUSED = "PAUSED"
    VERIFYING = "VERIFYING"
    FINISHED = "FINISHED"


@dataclass(frozen=True, slots=True)
class Settings:
    servers: tuple[str, ...] = ()
    serverMetSource: str | None = None
    dhtNodes: tuple[str, ...] = ()
    nodesDatSource: str | None = None
    listenPort: int = 0
    udpPort: int = 0
    enableDht: bool = True
    enableUpnp: bool = True
    reconnectToServer: bool = True


@dataclass(frozen=True, slots=True)
class Transfer:
    hash: str
    name: str
    path: Path
    size: int
    state: TransferState
    done: int
    received: int
    downloadRate: int
    uploadRate: int
    peers: int


@dataclass(frozen=True, slots=True)
class Snapshot:
    transfers: tuple[Transfer, ...]
