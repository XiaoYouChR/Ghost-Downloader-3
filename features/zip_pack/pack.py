from __future__ import annotations

import asyncio
import zipfile
from bisect import bisect_right

from app.models.pack import FeaturePack, TaskParser
from app.models.task import ResourceTaskOptions, Task, TaskOptions
from app.platform.filesystem import toSafeFilename
from http_pack.pack import fetchRange
from .sparse import SparseView
from .task import ZipEntry, ZipExtractStep, ZipTask

TAIL_SIZE = (64 << 10) + 98
MAX_CENTRAL_SIZE = 4 << 20
ZIP_CONTENT_TYPES = {"application/zip", "application/x-zip-compressed"}
SUPPORTED_COMPRESSIONS = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA}
if hasattr(zipfile, "ZIP_ZSTANDARD"):
    SUPPORTED_COMPRESSIONS.add(zipfile.ZIP_ZSTANDARD)


def parseCentralOffset(tail: bytes, tailOffset: int) -> int:
    end = tail.rfind(b"PK\x05\x06")
    if end < 0:
        raise zipfile.BadZipFile("找不到中央目录结束记录")
    centralSize = int.from_bytes(tail[end + 12:end + 16], "little")
    locator = end - 20
    if locator >= 0 and tail[locator:locator + 4] == b"PK\x06\x07":
        end = locator - 56
        if end < 0 or tail[end:end + 4] != b"PK\x06\x06":
            raise zipfile.BadZipFile("找不到 ZIP64 中央目录结束记录")
        centralSize = int.from_bytes(tail[end + 40:end + 48], "little")
    return tailOffset + end - centralSize


def parseInfos(view: SparseView) -> tuple[str, list[zipfile.ZipInfo]]:
    try:
        with zipfile.ZipFile(view, metadata_encoding="gbk") as archive:
            return "gbk", archive.infolist()
    except UnicodeDecodeError:
        with zipfile.ZipFile(view) as archive:
            return "", archive.infolist()


def buildEntries(infos: list[zipfile.ZipInfo], centralOffset: int) -> list[ZipEntry]:
    starts = sorted({info.header_offset for info in infos if not info.is_dir()} | {centralOffset})
    entries: list[ZipEntry] = []
    relativePaths: set[str] = set()
    for info in sorted(infos, key=lambda info: info.header_offset):
        if info.is_dir():
            continue
        if info.flag_bits & 0x1 or info.compress_type not in SUPPORTED_COMPRESSIONS:
            raise zipfile.BadZipFile(f"不支持的条目 {info.filename}")
        parts = [part for part in info.filename.split("/") if part not in {"", "."}]
        if not parts or ".." in parts:
            raise zipfile.BadZipFile(f"不安全的路径 {info.filename}")
        relativePath = "/".join(toSafeFilename(part, fallback="_") for part in parts)
        if relativePath.lower() in relativePaths:
            raise zipfile.BadZipFile(f"重复的路径 {relativePath}")
        relativePaths.add(relativePath.lower())
        entries.append(ZipEntry(
            index=len(entries),
            relativePath=relativePath,
            size=info.file_size,
            innerPath=info.filename,
            localHeaderOffset=info.header_offset,
            windowEnd=starts[bisect_right(starts, info.header_offset)],
        ))
    if not entries:
        raise zipfile.BadZipFile("压缩包里没有文件")
    return entries


def buildZipTask(options: TaskOptions, entries: list[ZipEntry], tailOffset: int, metadataEncoding: str) -> ZipTask:
    name = options.name if isinstance(options, ResourceTaskOptions) and options.name else options.file.name
    return ZipTask(
        name=name,
        url=options.url,
        fileSize=options.file.fileSize,
        outputFolder=options.outputFolder,
        files=entries,
        steps=[options.template, ZipExtractStep(stepIndex=2)],
        tailOffset=tailOffset,
        metadataEncoding=metadataEncoding,
    )


class ZipParser(TaskParser):
    priority = 96

    def match(self, options: TaskOptions) -> bool:
        return (options.isProbed and options.file.canUseRangeRequests and options.file.fileSize > 0
                and options.file.matchType({".zip"}, ZIP_CONTENT_TYPES))

    async def parse(self, options: TaskOptions) -> Task:
        size = options.file.fileSize
        tailOffset = max(0, size - TAIL_SIZE)
        tail = await fetchRange(options.template, tailOffset, size - tailOffset)
        centralOffset = parseCentralOffset(tail, tailOffset)
        if size - centralOffset > MAX_CENTRAL_SIZE:
            raise zipfile.BadZipFile("中央目录过大")
        if centralOffset < tailOffset:
            tail = await fetchRange(options.template, centralOffset, tailOffset - centralOffset) + tail
            tailOffset = centralOffset
        view = SparseView(size)
        view.addSegment(tailOffset, tail)
        metadataEncoding, infos = await asyncio.to_thread(parseInfos, view)
        entries = await asyncio.to_thread(buildEntries, infos, centralOffset)
        return buildZipTask(options, entries, tailOffset, metadataEncoding)


class ZipPack(FeaturePack):
    packId = "zip"
    parsers = [ZipParser]

    def taskCardClass(self, task: Task) -> type | None:
        from .cards import ZipTaskCard
        return ZipTaskCard

    def draftCardClass(self, task: Task) -> type | None:
        from .cards import ZipDraftCard
        return ZipDraftCard

    def optionCards(self, task, parent=None):
        from http_pack.pack import HttpPack
        return HttpPack.optionCards(self, task, parent)

    def editCards(self, task, parent=None):
        from http_pack.pack import HttpPack
        return HttpPack.editCards(self, task, parent)
