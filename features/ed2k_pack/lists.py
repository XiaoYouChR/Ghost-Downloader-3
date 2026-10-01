from __future__ import annotations

from pathlib import Path

from app.bootstrap_list import BootstrapList
from app.config.paths import APP_DATA_DIR

from .config import ed2kConfig

CONTACT_SIZE = 25


def countServers(data: bytes) -> int:
    if len(data) < 5 or data[0] not in (0xE0, 0x0E):
        raise ValueError("不是有效的 server.met")
    count = int.from_bytes(data[1:5], "little")
    if count == 0:
        raise ValueError("server.met 中没有服务器")
    return count


def countNodes(data: bytes) -> int:
    def readCount(offset: int) -> int:
        return int.from_bytes(data[offset:offset + 4], "little")

    headerSize = 4
    count = readCount(0)
    if count == 0 and len(data) >= 12:
        headerSize = 16 if readCount(4) == 3 else 12
        count = readCount(headerSize - 4)
    if count == 0 or len(data) < headerSize + count * CONTACT_SIZE:
        raise ValueError("不是有效的 nodes.dat")
    return count


LISTS_FOLDER = Path(__file__).parent / "lists"

serverList = BootstrapList(
    APP_DATA_DIR / "ed2k" / "servers",
    LISTS_FOLDER / "server.met",
    lambda: list(ed2kConfig.serverListSources.value),
    countServers,
)
nodeList = BootstrapList(
    APP_DATA_DIR / "ed2k" / "nodes",
    LISTS_FOLDER / "nodes.dat",
    lambda: list(ed2kConfig.nodeListSources.value),
    countNodes,
)
