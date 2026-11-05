from __future__ import annotations

import zipfile
from copy import deepcopy

from loguru import logger

from app.config.cfg import cfg
from app.models.pack import FeaturePack, TaskParser
from app.models.task import ResourceTaskOptions, Task, TaskOptions
from app.platform.filesystem import toSafeFilename
from http_pack.pack import buildTask, fetchRange
from .sparse import SparseView
from .task import ZipEntry, ZipExtractStep, ZipTask

TAIL_SIZE = (64 << 10) + 98
MAX_CENTRAL_SIZE = 4 << 20
ZIP_CONTENT_TYPES = {"application/zip", "application/x-zip-compressed"}
SUPPORTED_COMPRESSIONS = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA}
if hasattr(zipfile, "ZIP_ZSTANDARD"):
    SUPPORTED_COMPRESSIONS.add(zipfile.ZIP_ZSTANDARD)


def findCentralOffset(tail: bytes, tailOffset: int) -> int:
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


def loadInfos(view: SparseView) -> tuple[str, list[zipfile.ZipInfo]]:
    try:
        with zipfile.ZipFile(view, metadata_encoding="gbk") as archive:
            return "gbk", archive.infolist()
    except UnicodeDecodeError:
        with zipfile.ZipFile(view) as archive:
            return "", archive.infolist()


def buildEntries(infos: list[zipfile.ZipInfo], centralOffset: int) -> list[ZipEntry]:
    starts = sorted({info.header_offset for info in infos} | {centralOffset})
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
            name=info.filename,
            localHeaderOffset=info.header_offset,
            windowEnd=next(start for start in starts if start > info.header_offset),
        ))
    if not entries:
        raise zipfile.BadZipFile("压缩包里没有文件")
    return entries


def buildZipTask(options: TaskOptions, entries: list[ZipEntry], tailOffset: int, metadataEncoding: str) -> ZipTask:
    name = options.name if isinstance(options, ResourceTaskOptions) and options.name else options.file.name
    if name.lower().endswith(".zip"):
        name = name[:-4]
    whole = deepcopy(options.template)
    steps = [whole]
    for entry in entries:
        window = deepcopy(options.template)
        window.stepIndex = 2 * entry.index + 2
        window.fileIndex = entry.index
        window.httpByteOffset = entry.localHeaderOffset
        window.fileSize = entry.windowEnd - entry.localHeaderOffset
        window.lastModified = ""
        if window.fileSize < cfg.maxReassignSize.value * 1024:
            window.subworkerCount = 1
        steps.append(window)
        steps.append(ZipExtractStep(stepIndex=2 * entry.index + 3, fileIndex=entry.index))
    return ZipTask(
        name=toSafeFilename(name, fallback="archive"),
        url=options.url,
        fileSize=options.file.fileSize,
        outputFolder=options.outputFolder,
        files=entries,
        steps=steps,
        archiveSize=options.file.fileSize,
        tailOffset=tailOffset,
        metadataEncoding=metadataEncoding,
    )


class ZipParser(TaskParser):
    priority = 96

    def match(self, options: TaskOptions) -> bool:
        if not options.isProbed or not options.file.canUseRangeRequests or options.file.fileSize <= 0:
            return False
        return options.file.name.lower().endswith(".zip") or options.file.contentType in ZIP_CONTENT_TYPES

    async def parse(self, options: TaskOptions) -> Task:
        size = options.file.fileSize
        try:
            tailOffset = max(0, size - TAIL_SIZE)
            tail = await fetchRange(options.template, tailOffset, size - tailOffset)
            centralOffset = findCentralOffset(tail, tailOffset)
            if size - centralOffset > MAX_CENTRAL_SIZE:
                raise zipfile.BadZipFile("中央目录过大")
            if centralOffset < tailOffset:
                tail = await fetchRange(options.template, centralOffset, tailOffset - centralOffset) + tail
                tailOffset = centralOffset
            metadataEncoding, infos = loadInfos(SparseView(size, [(tailOffset, tail)]))
            return buildZipTask(options, buildEntries(infos, centralOffset), tailOffset, metadataEncoding)
        except Exception as e:
            logger.opt(exception=e).warning("无法预览压缩包，按普通文件下载 {}", options.url)
            return buildTask(options)


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
