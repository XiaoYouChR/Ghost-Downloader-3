from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from urllib.parse import quote, unquote, urlparse

from app.client import buildClient
from app.i18n import N
from app.models.pack import FeaturePack, TaskParser
from app.models.task import Task, TaskError, TaskOptions
from app.platform.filesystem import toSafeFilename
from .config import huggingFaceConfig, selectedMirrorSite
from .task import (
    API_BASE, HuggingFaceFile, HuggingFaceTask,
    buildAuthHeaders, buildRepoUrl, probeSite, toAuthError, toSiteUrl,
)

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
    from app.view.cards.draft_cards import DraftCard
    from app.view.cards.task_cards import TaskCard
    from app.view.components.option_cards import OptionCard

REPO_PATTERN = re.compile(
    r"^/(?P<type>(?:datasets|spaces)/)?(?P<org>[^/]+)/(?P<repo>[^/]+)"
    r"(?:/(?:resolve|blob|tree)/(?P<rev>[^/]+)(?:/(?P<path>.+))?)?$"
)


def parseHuggingFaceUrl(url: str) -> dict[str, str] | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if host not in {"huggingface.co"}:
        mirrorSite = selectedMirrorSite()
        if mirrorSite:
            mirrorHost = (urlparse(mirrorSite).hostname or "").lower()
            if host != mirrorHost:
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
        "revision": unquote(m.group("rev") or "main"),
        "filePath": unquote(m.group("path") or ""),
    }


class HuggingFaceParser(TaskParser):
    priority = 85

    def match(self, options: TaskOptions) -> bool:
        return parseHuggingFaceUrl(options.url) is not None

    async def parse(self, options: TaskOptions) -> Task:
        info = parseHuggingFaceUrl(options.url)
        if info is None:
            raise TaskError("无法解析 HuggingFace 链接")

        repoId = f"{info['org']}/{info['repo']}"
        repoType = info["repoType"]
        revision = info["revision"]
        filePath = info["filePath"].strip("/")
        repoUrl = buildRepoUrl(repoType, repoId)
        token = huggingFaceConfig.accessToken.value

        apiPrefix = {"dataset": "datasets", "space": "spaces"}.get(repoType, "models")
        client = buildClient(headers=buildAuthHeaders(token))
        try:
            apiUrl = f"{API_BASE}/api/{apiPrefix}/{repoId}/revision/{quote(revision, safe='')}?blobs=true"
            site = await probeSite(apiUrl, token)
            response = await client.get(toSiteUrl(apiUrl, site))
            status = response.status.as_int()
            if authError := toAuthError(status, bool(token), repoUrl):
                raise authError
            if status >= 400:
                raise TaskError("无法访问仓库 {repo}（{status}）", repo=repoId, status=status)
            repo = await response.json()

            # 固定到提交，仓库中途更新时续传不会拼接两个版本
            commit = repo["sha"]
            siblings = [
                s for s in repo.get("siblings", [])
                if not filePath or s["rfilename"] == filePath or s["rfilename"].startswith(f"{filePath}/")
            ]
            if not siblings:
                raise TaskError("仓库 {repo} 中没有 {path}", repo=repoId, path=filePath or "/")

            files = [
                HuggingFaceFile(
                    index=i,
                    relativePath=s["rfilename"],
                    size=s.get("size", 0),
                    downloadUrl=f"{repoUrl}/resolve/{commit}/{quote(s['rfilename'])}",
                )
                for i, s in enumerate(siblings)
            ]

            # Gated Repo 的列表公开，下载时才鉴权，所以添加时先试一个 LFS 文件
            if repo.get("gated"):
                lfsFile = next((f for f, s in zip(files, siblings) if s.get("lfs")), None)
                if lfsFile is not None:
                    response = await client.head(toSiteUrl(lfsFile.downloadUrl, site))
                    if authError := toAuthError(response.status.as_int(), bool(token), repoUrl):
                        raise authError
        finally:
            client.close()

        if len(files) == 1:
            name = toSafeFilename(PurePosixPath(files[0].relativePath).name, fallback="huggingface")
        else:
            name = toSafeFilename(repoId.replace("/", "_"), fallback="huggingface")

        task = HuggingFaceTask(
            name=name,
            url=options.url,
            fileSize=sum(f.size for f in files),
            outputFolder=options.outputFolder,
            repoId=repoId,
            repoType=repoType,
            revision=revision,
            files=files,
        )
        task.setOptions({"subworkerCount": options.subworkerCount})
        return task


class HuggingFacePack(FeaturePack):
    packId = "huggingface"
    capturedLinks = N("HuggingFacePack", "Hugging Face 模型与数据集文件")
    config = huggingFaceConfig
    parsers = [HuggingFaceParser]

    def taskCardClass(self, task: Task) -> type[TaskCard] | None:
        from .cards import HuggingFaceTaskCard
        return HuggingFaceTaskCard

    def draftCardClass(self, task: Task) -> type[DraftCard] | None:
        from .cards import HuggingFaceDraftCard
        return HuggingFaceDraftCard

    def optionCards(self, task: Task, parent: QWidget | None = None) -> list[OptionCard]:
        from app.view.components.option_cards import OutputFolderCard
        return [OutputFolderCard(parent, initial=task.outputFolder)]
