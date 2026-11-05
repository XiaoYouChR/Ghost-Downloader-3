from __future__ import annotations

import io
import zipfile
from datetime import datetime

import pytest
from aiohttp import web

import zip_pack.pack
from app.models.pack import PackServices
from app.models.task import TaskOptions, TaskStatus
from http_pack.pack import HttpPack
from http_pack.task import HttpTask
from tests.helpers import buildFileContent, buildRangeHandler, waitUntil
from zip_pack.pack import ZipPack
from zip_pack.task import ZipTask

FILES = {
    "bin/tool.dll": buildFileContent(300_000),
    "readme.txt": b"hello " * 1000,
    "empty.txt": b"",
}
MODIFIED_AT = (2024, 5, 6, 7, 8, 10)


@pytest.fixture(params=["desktop", "android"])
def engine(startEngine, request):
    return startEngine(request.param)


@pytest.fixture
def features(engine):
    services = PackServices(coroutineRunner=engine.coroutineRunner, speedMeter=engine.speedMeter)
    for pack in (HttpPack(services), ZipPack(services)):
        engine.featureService.register(pack)
    return engine.featureService


def buildArchive(files: dict[str, bytes] = FILES, compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(zipfile.ZipInfo("bin/", date_time=MODIFIED_AT), b"")
        for name, data in files.items():
            info = zipfile.ZipInfo(name, date_time=MODIFIED_AT)
            info.compress_type = compression
            archive.writestr(info, data)
    return buffer.getvalue()


def buildNamedHandler(content: bytes, name: str):
    rangeHandler = buildRangeHandler(content)

    async def handler(request: web.Request) -> web.Response:
        response = await rangeHandler(request)
        response.headers["Content-Disposition"] = f'attachment; filename="{name}"'
        return response
    return handler


async def startArchive(startServer, archive: bytes) -> str:
    return await startServer(buildNamedHandler(archive, "a.zip"))


async def runToCompletion(engine, task) -> None:
    engine.taskService.add(task)
    await waitUntil(lambda: task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}, timeout=20)
    assert task.status == TaskStatus.COMPLETED


async def test_parse_archive_lists_its_files(features, startServer):
    task = await features.parse(TaskOptions(url=await startArchive(startServer, buildArchive())))

    assert isinstance(task, ZipTask)
    assert task.name == "a"
    assert [file.relativePath for file in task.files] == ["bin/tool.dll", "readme.txt", "empty.txt"]
    assert [file.size for file in task.files] == [len(data) for data in FILES.values()]


async def test_parse_link_without_suffix_reads_name_from_server(features, startServer):
    url = await startArchive(startServer, buildArchive())

    task = await features.parse(TaskOptions(url=f"{url}?id=1"))

    assert isinstance(task, ZipTask)


@pytest.mark.parametrize("compression", [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2,
                                         zipfile.ZIP_LZMA])
async def test_run_selected_files_extracts_only_them(engine, features, startServer, downloadFolder, compression):
    task = await features.parse(TaskOptions(url=await startArchive(startServer, buildArchive(compression=compression))))
    task.setSelection([0, 2])

    await runToCompletion(engine, task)

    tool = downloadFolder / "a" / "bin" / "tool.dll"
    assert tool.read_bytes() == FILES["bin/tool.dll"]
    assert (downloadFolder / "a" / "empty.txt").read_bytes() == b""
    assert datetime.fromtimestamp(tool.stat().st_mtime).timetuple()[:6] == MODIFIED_AT
    assert sorted(path.relative_to(downloadFolder).as_posix() for path in downloadFolder.rglob("*")) == [
        "a", "a/bin", "a/bin/tool.dll", "a/empty.txt"]


async def test_run_all_selected_downloads_archive_itself(engine, features, startServer, downloadFolder):
    archive = buildArchive()
    task = await features.parse(TaskOptions(url=await startArchive(startServer, archive)))

    await runToCompletion(engine, task)

    assert [path.name for path in downloadFolder.iterdir()] == ["a.zip"]
    assert (downloadFolder / "a.zip").read_bytes() == archive


async def test_parse_archive_from_chinese_windows_reads_names(features, startServer):
    archive = buildArchive({"abcd.txt": b"x"}).replace(b"abcd.txt", "中文.txt".encode("gbk"))

    task = await features.parse(TaskOptions(url=await startArchive(startServer, archive)))

    assert [file.relativePath for file in task.files] == ["中文.txt"]


async def test_parse_zip64_archive_lists_its_files(features, startServer, monkeypatch):
    monkeypatch.setattr(zipfile, "ZIP_FILECOUNT_LIMIT", 1)
    archive = buildArchive()
    assert b"PK\x06\x06" in archive

    task = await features.parse(TaskOptions(url=await startArchive(startServer, archive)))

    assert [file.relativePath for file in task.files] == ["bin/tool.dll", "readme.txt", "empty.txt"]


def encrypt(archive: bytes) -> bytes:
    data = bytearray(archive)
    central = data.find(b"PK\x01\x02")
    while central >= 0:
        data[central + 8] |= 0x1
        central = data.find(b"PK\x01\x02", central + 1)
    return bytes(data)


@pytest.mark.parametrize("archive", [
    pytest.param(encrypt(buildArchive()), id="encrypted"),
    pytest.param(buildArchive({"../evil.txt": b"x", "ok.txt": b"y"}), id="unsafe-path"),
    pytest.param(b"not a zip" * 100, id="not-zip"),
])
async def test_parse_unpreviewable_archive_adds_plain_file(features, startServer, archive):
    task = await features.parse(TaskOptions(url=await startArchive(startServer, archive)))

    assert isinstance(task, HttpTask)
    assert task.name == "a.zip"


async def test_parse_huge_central_directory_adds_plain_file(features, startServer, monkeypatch):
    monkeypatch.setattr(zip_pack.pack, "MAX_CENTRAL_SIZE", 10)

    task = await features.parse(TaskOptions(url=await startArchive(startServer, buildArchive())))

    assert isinstance(task, HttpTask)


async def test_relink_same_archive_keeps_selection(engine, features, startServer, downloadFolder):
    archive = buildArchive()
    task = await features.parse(TaskOptions(url=await startArchive(startServer, archive)))
    task.setSelection([1])
    engine.taskService.add(task, autoStart=False)
    newUrl = await startArchive(startServer, archive)

    probed = await features.probe(TaskOptions(url=newUrl))
    assert task.canReuseProgress(probed)
    engine.taskService.edit(task, {}, probed)
    engine.taskService.start(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED, timeout=20)

    assert task.url == newUrl
    assert (downloadFolder / "a" / "readme.txt").read_bytes() == FILES["readme.txt"]
