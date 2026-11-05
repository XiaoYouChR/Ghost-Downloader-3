from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp import web

from app.models.pack import PackServices
from app.models.task import RemoteFile, TaskOptions, TaskStatus
from arxiv_pack.pack import ArxivPack, ArxivParser, buildName, parseArxivId
from arxiv_pack.task import ArxivBibtexStep, ArxivSourceStep, ArxivTask
from http_pack.pack import HttpPack, buildStep
from http_pack.task import HttpTaskStep
from huggingface_pack.pack import HuggingFacePack
from tests.helpers import buildRangeHandler, waitUntil

NAME = "1706.03762v7 Attention Is All You Need.pdf"
PDF = b"%PDF-1.5 paper"
SOURCE = b"\x1f\x8b source"
BIBTEX = b"@misc{vaswani2023attention}"


async def startArxiv(startServer) -> str:
    handlers = {"pdf": buildRangeHandler(PDF), "src": buildRangeHandler(SOURCE)}

    async def handle(request: web.Request) -> web.Response:
        kind = request.path.split("/")[1]
        if kind == "bibtex":
            return web.Response(body=BIBTEX, content_type="text/plain")
        return await handlers[kind](request)

    return (await startServer(handle)).removesuffix("/file")


@pytest.fixture(params=["desktop", "android"])
def engine(request, startEngine):
    return startEngine(request.param)


def buildTask(origin: str, *, isSourceEnabled: bool = False, isBibtexEnabled: bool = False) -> ArxivTask:
    options = TaskOptions(url=f"{origin}/abs/1706.03762")
    task = ArxivTask(name=NAME, url=options.url)
    task.addStep(buildStep(HttpTaskStep, 1, f"{origin}/pdf/1706.03762", options,
                           RemoteFile(name="", fileSize=len(PDF), canUseRangeRequests=True)))
    task.addStep(buildStep(ArxivSourceStep, 2, f"{origin}/src/1706.03762", options,
                           RemoteFile(name="", fileSize=len(SOURCE), canUseRangeRequests=True)))
    task.addStep(buildStep(ArxivBibtexStep, 3, f"{origin}/bibtex/1706.03762", options))
    task.setOptions({"isSourceEnabled": isSourceEnabled, "isBibtexEnabled": isBibtexEnabled})
    return task


def namesIn(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


@pytest.mark.parametrize("text", [
    "https://arxiv.org/abs/1706.03762",
    "https://arxiv.org/pdf/1706.03762v7",
    "https://arxiv.org/pdf/1706.03762.pdf",
    "https://arxiv.org/html/2401.00001v1/#S2",
    "https://export.arxiv.org/abs/hep-th/9901001v3",
    "https://www.alphaxiv.org/abs/2312.16682v2",
    "https://huggingface.co/papers/2401.00002",
    "arXiv:1706.03762",
    "1706.03762v7",
    "hep-th/9901001",
    "math.GT/0309136",
])
def test_match_paper_link_or_id(config, text):
    assert ArxivParser().match(TaskOptions(url=text))


@pytest.mark.parametrize("text", [
    "https://arxiv.org/src/1706.03762",
    "https://arxiv.org/list/cs.AI/recent",
    "https://huggingface.co/org/repo",
    "https://example.com/1706.03762",
    "1234.5678",
])
def test_match_skips_other_link(config, text):
    assert not ArxivParser().match(TaskOptions(url=text))


def test_parse_legacy_id_drops_subject_class():
    arxivId = parseArxivId("https://arxiv.org/abs/math.GT/0309136v1")

    assert buildName(arxivId, "v1", "Regular points") == "math0309136v1 Regular points.pdf"


def test_match_passive_skips_bare_id(engine):
    services = PackServices(coroutineRunner=engine.coroutineRunner, speedMeter=engine.speedMeter)
    for pack in (ArxivPack(services), HuggingFacePack(services), HttpPack(services)):
        engine.featureService.register(pack)

    assert engine.featureService.matchPassive("https://arxiv.org/abs/1706.03762")
    assert engine.featureService.match("1706.03762")
    assert not engine.featureService.matchPassive("1706.03762")


async def test_add_holds_enabled_side_file_beside_pdf(engine, startServer, downloadFolder):
    task = buildTask(await startArxiv(startServer), isBibtexEnabled=True)

    engine.taskService.add(task, autoStart=False)

    assert namesIn(downloadFolder) == ["1706.03762v7 Attention Is All You Need.bib", NAME]


async def test_run_downloads_pdf_with_enabled_side_files(engine, startServer, downloadFolder):
    task = buildTask(await startArxiv(startServer), isSourceEnabled=True, isBibtexEnabled=True)

    engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)

    assert (downloadFolder / NAME).read_bytes() == PDF
    assert (downloadFolder / "1706.03762v7 Attention Is All You Need.tar.gz").read_bytes() == SOURCE
    assert (downloadFolder / "1706.03762v7 Attention Is All You Need.bib").read_bytes() == BIBTEX


async def test_edit_enable_side_file_after_completed_downloads_it(engine, startServer, downloadFolder):
    task = buildTask(await startArxiv(startServer))
    engine.taskService.add(task)
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)
    assert namesIn(downloadFolder) == [NAME]

    engine.taskService.edit(task, {"isBibtexEnabled": True})

    await waitUntil(lambda: task.status == TaskStatus.COMPLETED
                    and (downloadFolder / "1706.03762v7 Attention Is All You Need.bib").read_bytes() == BIBTEX)
    assert (downloadFolder / NAME).read_bytes() == PDF


async def test_edit_disable_side_file_releases_its_name(engine, startServer, downloadFolder):
    task = buildTask(await startArxiv(startServer), isSourceEnabled=True)
    engine.taskService.add(task, autoStart=False)

    engine.taskService.edit(task, {"isSourceEnabled": False})
    await waitUntil(lambda: task.status == TaskStatus.COMPLETED)

    assert namesIn(downloadFolder) == [NAME]
