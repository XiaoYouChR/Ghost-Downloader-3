from __future__ import annotations

import re
from dataclasses import replace
from urllib.parse import urlparse

from app.client import buildClient
from app.models.pack import FeaturePack, TaskParser
from app.models.task import Task, TaskFile, TaskOptions
from app.platform.filesystem import toSafeFilename
from .config import accessToken, huggingFaceConfig, selectedProxySite
from .task import HuggingFaceFile, HuggingFaceStep, HuggingFaceTask

from features.http_pack.task import HttpTaskStep

HF_HOSTS = {"huggingface.co", "www.huggingface.co"}
REPO_PATTERN = re.compile(
    r"^/(?P<type>(?:datasets|spaces)/)?(?P<org>[^/]+)/(?P<repo>[^/]+)"
    r"(?:/(?:resolve|blob|tree)/(?P<rev>[^/]+)(?:/(?P<path>.+))?)?$"
)
API_BASE = "https://huggingface.co"


def parseHuggingFaceUrl(url: str) -> dict | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if host not in {"huggingface.co"}:
        proxySite = selectedProxySite()
        if proxySite:
            proxyHost = (urlparse(proxySite).hostname or "").lower()
            if host != proxyHost:
                return None
        else:
            return None

    m = REPO_PATTERN.match(parsed.path)
    if m is None:
        return None

    repoType = "model"
    typePrefix = m.group("type") or ""
    if typePrefix.startswith("datasets"):
        repoType = "dataset"
    elif typePrefix.startswith("spaces"):
        repoType = "space"

    return {
        "org": m.group("org"),
        "repo": m.group("repo"),
        "repoType": repoType,
        "revision": m.group("rev") or "main",
        "filePath": m.group("path") or "",
    }


class HuggingFaceParser(TaskParser):
    priority = 85

    def match(self, options: TaskOptions) -> bool:
        return parseHuggingFaceUrl(options.url) is not None

    async def parse(self, options: TaskOptions) -> Task:
        info = parseHuggingFaceUrl(options.url)
        if info is None:
            raise ValueError("无法解析 HuggingFace 链接")

        repoId = f"{info['org']}/{info['repo']}"
        repoType = info["repoType"]
        revision = info["revision"]
        filePath = info["filePath"]

        headers: dict[str, str] = {}
        token = accessToken()
        if token:
            headers["authorization"] = f"Bearer {token}"

        from app.config.cfg import cfg

        if filePath:
            downloadUrl = self._fileUrl(repoId, repoType, revision, filePath)
            name = toSafeFilename(filePath.rsplit("/", 1)[-1], fallback="download")

            client = buildClient(headers=headers)
            try:
                response = await client.head(downloadUrl)
                fileSize = 0
                cl = response.headers.get("content-length")
                if cl:
                    fileSize = int(cl.decode() if isinstance(cl, bytes) else cl)
                canUseRange = response.headers.contains_key("accept-ranges")
            finally:
                client.close()

            task = HuggingFaceTask(
                name=name,
                url=options.url,
                fileSize=fileSize,
                outputFolder=options.outputFolder,
                repoId=repoId,
                repoType=repoType,
                revision=revision,
            )
            task.addStep(HttpTaskStep(
                stepIndex=1,
                url=downloadUrl,
                fileSize=fileSize,
                headers=headers,
                subworkerCount=cfg.preBlockNum.value,
                canUseRangeRequests=canUseRange,
            ))
            return task

        apiPrefix = {"dataset": "datasets", "space": "spaces"}.get(repoType, "models")
        base = selectedProxySite() or API_BASE
        apiUrl = f"{base}/api/{apiPrefix}/{repoId}/tree/{revision}"

        client = buildClient(headers=headers)
        try:
            entries = await self._fetchTree(client, apiUrl)
        finally:
            client.close()

        if not entries:
            raise ValueError(f"仓库 {repoId} 为空或无法访问")

        files: list[HuggingFaceFile] = []
        for i, entry in enumerate(entries):
            path = entry.get("path", "")
            size = entry.get("size", 0)
            lfs = entry.get("lfs")
            if lfs and isinstance(lfs, dict):
                size = lfs.get("size", size)
            files.append(HuggingFaceFile(
                index=i,
                relativePath=path,
                size=size,
                downloadUrl=self._fileUrl(repoId, repoType, revision, path),
            ))

        repoName = toSafeFilename(repoId.replace("/", "_"), fallback="huggingface")

        steps = [
            HuggingFaceStep(
                stepIndex=file.index + 1,
                url=file.downloadUrl,
                fileSize=file.size,
                headers=headers,
                subworkerCount=cfg.preBlockNum.value,
                canUseRangeRequests=file.size > 0,
                fileIndex=file.index,
            )
            for file in files
        ]

        return HuggingFaceTask(
            name=repoName,
            url=options.url,
            fileSize=sum(f.size for f in files),
            outputFolder=options.outputFolder,
            repoId=repoId,
            repoType=repoType,
            revision=revision,
            files=files,
            steps=steps,
        )

    async def _fetchTree(self, client, apiUrl: str) -> list[dict]:
        entries: list[dict] = []
        url = apiUrl
        while url:
            response = await client.get(url)
            if response.status.as_int() == 401:
                raise PermissionError("该仓库需要授权，请在设置中配置 HuggingFace Access Token")
            response.raise_for_status()
            page = await response.json()
            if isinstance(page, list):
                for entry in page:
                    if entry.get("type") == "file":
                        entries.append(entry)
                    elif entry.get("type") == "directory":
                        dirName = entry['path'].rsplit('/', 1)[-1]
                        subUrl = f"{apiUrl}/{dirName}"
                        subEntries = await self._fetchTree(client, subUrl)
                        entries.extend(subEntries)
                break
            else:
                break
        return entries

    def _fileUrl(self, repoId: str, repoType: str, revision: str, filePath: str) -> str:
        base = selectedProxySite() or API_BASE
        typePrefix = {"dataset": "datasets/", "space": "spaces/"}.get(repoType, "")
        return f"{base}/{typePrefix}{repoId}/resolve/{revision}/{filePath}"


class HuggingFacePack(FeaturePack):
    packId = "huggingface"
    config = huggingFaceConfig

    def parsers(self) -> list[TaskParser]:
        return [HuggingFaceParser()]

    def draftCard(self, task, parent=None):
        from .cards import HuggingFaceDraftCard
        return HuggingFaceDraftCard(task, parent)

    def taskCard(self, task, parent=None):
        from .cards import HuggingFaceTaskCard
        return HuggingFaceTaskCard(task, parent)

    def optionCards(self, task, parent=None):
        from app.view.components.option_cards import OutputFolderCard
        return [OutputFolderCard(parent, initial=task.outputFolder)]
