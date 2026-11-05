from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from app.client import buildClient
from app.models.task import Task, TaskError, TaskFile, TaskStep
from .config import huggingFaceConfig, selectedMirrorSite

from http_pack.task import HttpTaskStep
from wreq.redirect import Policy

API_BASE = "https://huggingface.co"


def buildAuthHeaders(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"} if token else {}


def buildRepoUrl(repoType: str, repoId: str) -> str:
    typePrefix = {"dataset": "datasets/", "space": "spaces/"}.get(repoType, "")
    return f"{API_BASE}/{typePrefix}{repoId}"


def toAuthError(status: int, hasToken: bool, repoUrl: str) -> TaskError | None:
    """没有 Token 时 Mirror Site 返回 403、官方站返回 401，所以先看 Token 再看状态码。"""
    if status not in (401, 403):
        return None
    if not hasToken:
        return TaskError("该仓库需要授权，请在设置中填写 HuggingFace Access Token")
    if status == 401:
        return TaskError("HuggingFace Access Token 无效或已过期，请在设置中更新")
    return TaskError(
        "尚未获得该仓库的访问权限，请先在 {url} 申请；若已获批，请确认 Access Token 有读取 Gated Repo 的权限",
        url=repoUrl,
    )


def toSiteUrl(url: str, site: str) -> str:
    parts = urlsplit(url)
    return f"{site}{parts.path}" + (f"?{parts.query}" if parts.query else "")


async def probeSite(url: str, token: str) -> str:
    """返回这次应请求的站点。Mirror Site 把请求跳回官方站时直接用官方站，否则跳转会丢掉 Token。"""
    site = selectedMirrorSite()
    if not site:
        return API_BASE
    if not token:
        return site

    client = buildClient(headers=buildAuthHeaders(token))
    try:
        response = await client.head(toSiteUrl(url, site), redirect=Policy.none())
        location = bytes(response.headers.get("location") or b"").decode()
        response.close()
    finally:
        client.close()
    return API_BASE if location.startswith(f"{API_BASE}/") else site


@dataclass(kw_only=True)
class HuggingFaceFile(TaskFile):
    downloadUrl: str = ""


@dataclass(kw_only=True)
class HuggingFaceStep(HttpTaskStep):
    @property
    def outputPath(self) -> str:
        return str(self.task.toFilePath(self.fileIndex))

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        # Task.run 记录 Step 的错误，所以鉴权提示须在这里换上
        try:
            await super().run(reportSpeed, waitForSpeedLimit)
        except TaskError as e:
            repoUrl = buildRepoUrl(self.task.repoType, self.task.repoId)
            authError = toAuthError(e.params.get("status"), "authorization" in self.headers, repoUrl)
            if authError is None:
                raise
            raise authError from e

    @classmethod
    def fromFile(cls, file: TaskFile, task: Task) -> TaskStep:
        from app.config.cfg import cfg
        hfFile: HuggingFaceFile = file
        return cls(
            stepIndex=file.index + 1,
            url=hfFile.downloadUrl,
            fileSize=file.size,
            subworkerCount=cfg.preBlockNum.value,
            canUseRangeRequests=file.size > 0,
            fileIndex=file.index,
        )


@dataclass(kw_only=True, eq=False)
class HuggingFaceTask(Task):
    packId: str = "huggingface"
    canEdit = True
    fileType = HuggingFaceFile
    repoId: str = ""
    repoType: str = "model"
    revision: str = "main"

    def __post_init__(self):
        super().__post_init__()
        # 旧存档中被取消勾选的文件没有 Step，按 files 补建
        if self.files:
            existing = {s.fileIndex for s in self.steps}
            for file in self.files:
                if file.index not in existing:
                    self.addStep(HuggingFaceStep.fromFile(file, self))

    @property
    def countSelected(self) -> int:
        return sum(1 for f in self.files if f.selected) if self.files else 0

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        # 按当前设置刷新 Step，修改 Token 或 Mirror Site 后重试即可生效
        steps = list(self.pendingSteps())
        if steps:
            token = huggingFaceConfig.accessToken.value
            site = await probeSite(steps[0].url, token)
            for step in steps:
                step.url = toSiteUrl(step.url, site)
                step.headers = buildAuthHeaders(token)
        await super().run(reportSpeed, waitForSpeedLimit)
