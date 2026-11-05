from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, replace
from html import unescape
from urllib.parse import urlparse

from loguru import logger

from app.client import buildClient, toEmulation
from app.config.cfg import cfg
from app.i18n import N
from app.models.pack import FeaturePack, TaskParser
from app.models.task import Task, TaskOptions
from app.platform.filesystem import splitStemExt
from http_pack.pack import RemoteFile, probe
from http_pack.task import HttpTaskStep
from .config import arxivConfig
from .task import ArxivBibtexStep, ArxivSourceStep, ArxivTask

ARXIV_ORIGIN = "https://arxiv.org"
ARXIV_HOSTS = {"arxiv.org", "export.arxiv.org"}
MONTH = r"(?:0[1-9]|1[0-2])"
# 新式编号 1706.03762，旧式编号 hep-th/9901001；math.GT/0309136 的学科子类不属于编号，arXiv 自己也写作 math/0309136
ID = (rf"(?:(?P<new>\d\d{MONTH}\.\d{{4,5}})|(?P<archive>[a-z]+(?:-[a-z]+)*)(?:\.[A-Z]{{2}})?/(?P<serial>\d\d{MONTH}\d{{3}}))"
      rf"(?P<version>v\d+)?")
BARE_PATTERN = re.compile(rf"(?i:arxiv:)?{ID}")
ARXIV_PATH_PATTERN = re.compile(rf"/(?:abs|pdf|html)/{ID}(?:\.pdf)?(?:/.*)?")
ALPHAXIV_PATH_PATTERN = re.compile(rf"(?:.*/)?{ID}(?:\.pdf)?(?:/.*)?")
HF_PAPERS_PATH_PATTERN = re.compile(rf"/papers/{ID}/?")
TITLE_PATTERN = re.compile(r'<meta\s+name="citation_title"\s+content="(?P<title>[^"]*)"')
PDF_VERSION_PATTERN = re.compile(r"(v\d+)\.pdf$")


@dataclass(frozen=True)
class ArxivId:
    number: str
    version: str = ""

    def __str__(self) -> str:
        return f"{self.number}{self.version}"


def parseArxivId(text: str) -> ArxivId | None:
    text = text.strip()
    parsedUrl = urlparse(text)
    if parsedUrl.scheme.lower() not in {"http", "https"}:
        m = BARE_PATTERN.fullmatch(text)
    else:
        host = (parsedUrl.hostname or "").lower().removeprefix("www.")
        if host in ARXIV_HOSTS:
            m = ARXIV_PATH_PATTERN.fullmatch(parsedUrl.path)
        elif host == "alphaxiv.org":
            m = ALPHAXIV_PATH_PATTERN.fullmatch(parsedUrl.path)
        elif host == "huggingface.co":
            m = HF_PAPERS_PATH_PATTERN.fullmatch(parsedUrl.path)
        else:
            return None
    if m is None:
        return None
    return ArxivId(m["new"] or f"{m['archive']}/{m['serial']}", m["version"] or "")


def buildName(arxivId: ArxivId, version: str, title: str) -> str:
    stem = arxivId.number.replace("/", "") + version
    if not title:
        return f"{stem}.pdf"
    # 冒号在 Windows 文件名里非法，"BERT: Pre-training" 写作 "BERT - Pre-training" 比写成下划线易读
    title = re.sub(r"\s*:\s*", " - ", title)
    return f"{stem} {title}.pdf"


def buildStep(stepType: type[HttpTaskStep], stepIndex: int, url: str, options: TaskOptions,
              file: RemoteFile | None = None, **kwargs) -> HttpTaskStep:
    return stepType(
        stepIndex=stepIndex,
        url=url,
        fileSize=file.fileSize if file else 0,
        headers=dict(options.headers),
        clientProfile=options.clientProfile,
        userAgent=options.userAgent,
        subworkerCount=options.subworkerCount,
        canUseRangeRequests=file.canUseRangeRequests if file else False,
        lastModified=file.lastModified if file else "",
        **kwargs,
    )


async def fetchTitle(options: TaskOptions) -> str:
    client = buildClient(
        emulation=toEmulation(options.clientProfile or cfg.clientProfile.value, options.sourceUserAgent),
        headers=dict(options.headers),
        userAgent=options.userAgent or None,
        timeout=30,
    )
    try:
        response = await client.get(options.url)
        response.raise_for_status()
        page = await response.text()
    finally:
        client.close()
    m = TITLE_PATTERN.search(page)
    return " ".join(unescape(m["title"]).split()) if m else ""


class ArxivParser(TaskParser):
    # 先于 HuggingFace（85），否则 huggingface.co/papers/{编号} 会被当成模型仓库
    priority = 80

    def match(self, options: TaskOptions) -> bool:
        return arxivConfig.isEnabled.value and parseArxivId(options.url) is not None

    def matchPassive(self, options: TaskOptions) -> bool:
        return urlparse(options.url).scheme.lower() in {"http", "https"}

    async def parse(self, options: TaskOptions) -> Task:
        arxivId = parseArxivId(options.url)
        absUrl = f"{ARXIV_ORIGIN}/abs/{arxivId}"
        title, pdf, source = await asyncio.gather(
            fetchTitle(replace(options, url=absUrl)),
            probe(replace(options, url=f"{ARXIV_ORIGIN}/pdf/{arxivId}")),
            probe(replace(options, url=f"{ARXIV_ORIGIN}/src/{arxivId}")),
            return_exceptions=True,
        )
        if isinstance(pdf, BaseException):
            raise pdf
        if isinstance(title, BaseException):
            logger.opt(exception=title).warning("arXiv 标题获取失败 {}", arxivId)
            title = ""
        version = arxivId.version or (m[1] if (m := PDF_VERSION_PATTERN.search(pdf.name)) else "")
        name = buildName(arxivId, version, title) if version else pdf.name

        task = ArxivTask(name=name, url=absUrl, outputFolder=options.outputFolder)
        task.addStep(buildStep(HttpTaskStep, 1, f"{ARXIV_ORIGIN}/pdf/{arxivId}", options, pdf))
        # 只投了 PDF 的论文，src 返回的就是那份 PDF
        if isinstance(source, RemoteFile) and source.contentType != "application/pdf":
            suffix = splitStemExt(source.name)[1].lstrip(".") or "tar.gz"
            task.addStep(buildStep(ArxivSourceStep, 2, f"{ARXIV_ORIGIN}/src/{arxivId}", options, source, suffix=suffix))
        task.addStep(buildStep(ArxivBibtexStep, 3, f"{ARXIV_ORIGIN}/bibtex/{arxivId}", options))
        task.setOptions({
            "isSourceEnabled": task.hasSource and arxivConfig.shouldDownloadSource.value,
            "isBibtexEnabled": arxivConfig.shouldDownloadBibtex.value,
        })
        return task


class ArxivPack(FeaturePack):
    packId = "arxiv"
    capturedLinks = N("ArxivPack", "arXiv 论文")
    config = arxivConfig
    parsers = [ArxivParser]

    def taskCardClass(self, task: Task) -> type | None:
        from http_pack.cards import HttpTaskCard
        return HttpTaskCard

    def draftCardClass(self, task: Task) -> type | None:
        from .cards import ArxivDraftCard
        return ArxivDraftCard

    def optionCards(self, task, parent=None):
        from http_pack.pack import HttpPack
        return HttpPack.optionCards(self, task, parent)

    def editCards(self, task, parent=None):
        from app.view.components.option_cards import UrlEditCard
        from .cards import SideFileCard
        return [
            UrlEditCard(parent, initial=task.url),
            *self.optionCards(task, parent),
            SideFileCard(parent, task=task),
        ]
