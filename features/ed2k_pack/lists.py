from __future__ import annotations

import struct
from pathlib import Path

from app.bootstrap_list import BootstrapList
from app.config.paths import APP_DATA_DIR

from .config import ed2kConfig

TAG_SIZES = {0x01: 16, 0x03: 4, 0x04: 4, 0x05: 1, 0x08: 2, 0x09: 1, 0x0B: 8}
TAG_LENGTH_FORMATS = {0x02: "<H", 0x07: "<I", 0x0A: "<B"}


def parseServerList(data: bytes) -> list[bytes]:
    if len(data) < 5 or data[0] not in (0xE0, 0x0E, 0x0F):
        raise ValueError("不是有效的 server.met")
    (count,) = struct.unpack_from("<I", data, 1)
    offset = 5
    endpoints = []
    try:
        for _ in range(count):
            endpoints.append(data[offset:offset + 6])
            (tagCount,) = struct.unpack_from("<I", data, offset + 6)
            offset += 10
            for _ in range(tagCount):
                head = data[offset]
                tagType = head & 0x7F
                offset += 2 if head & 0x80 else 3 + struct.unpack_from("<H", data, offset + 1)[0]
                if tagType in TAG_SIZES:
                    offset += TAG_SIZES[tagType]
                elif 0x11 <= tagType <= 0x20:
                    offset += tagType - 0x10
                elif tagType in TAG_LENGTH_FORMATS:
                    lengthFormat = TAG_LENGTH_FORMATS[tagType]
                    offset += struct.calcsize(lengthFormat) + struct.unpack_from(lengthFormat, data, offset)[0]
                elif tagType == 0x06:
                    offset += 3 + struct.unpack_from("<H", data, offset)[0] // 8
                else:
                    raise ValueError(f"server.met 中有未知的标签类型 {tagType:#x}")
    except (IndexError, struct.error):
        raise ValueError("server.met 不完整") from None
    if offset > len(data):
        raise ValueError("server.met 不完整")
    if not endpoints:
        raise ValueError("server.met 中没有服务器")
    return endpoints


def parseNodeList(data: bytes) -> list[bytes]:
    def readCount(offset: int) -> int:
        return int.from_bytes(data[offset:offset + 4], "little")

    headerSize = 4
    contactSize = 25
    count = readCount(0)
    if count == 0 and len(data) >= 12:
        version = readCount(4)
        if version == 3:
            headerSize = 16
            contactSize = 25 if readCount(8) == 1 else 34
        else:
            headerSize = 12
            contactSize = 34 if version == 2 else 25
        count = readCount(headerSize - 4)
    if count == 0 or len(data) < headerSize + count * contactSize:
        raise ValueError("不是有效的 nodes.dat")
    return [
        data[offset:offset + 16]
        for offset in range(headerSize, headerSize + count * contactSize, contactSize)
    ]


LISTS_FOLDER = Path(__file__).parent / "lists"

serverList = BootstrapList(
    APP_DATA_DIR / "ed2k" / "servers",
    LISTS_FOLDER / "server.met",
    lambda: list(ed2kConfig.serverListSources.value),
    parseServerList,
)
nodeList = BootstrapList(
    APP_DATA_DIR / "ed2k" / "nodes",
    LISTS_FOLDER / "nodes.dat",
    lambda: list(ed2kConfig.nodeListSources.value),
    parseNodeList,
)
