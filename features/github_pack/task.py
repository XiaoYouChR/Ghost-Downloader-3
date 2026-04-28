# pyright: reportAny=false, reportExplicitAny=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportUnannotatedClassAttribute=false, reportUnnecessaryCast=false, reportImplicitOverride=false, reportInconsistentConstructor=false, reportUntypedBaseClass=false

from __future__ import annotations

import importlib
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any
from typing import cast
from uuid import uuid4

from app.feature_pack.api import SpecialFileSize
from app.feature_pack.api import FormField
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskForm
from app.feature_pack.api import TaskStage

from .config import getSelectedProxySite


_GITHUB_PACK_ID = "github_pack"
_GITHUB_TASK_KIND = "github_download"
_GITHUB_TASK_VERSION = 1
_HTTP_STAGE_KIND = "http_download"
_HTTP_STAGE_VERSION = 1


def _importPackModule(packId: str, moduleName: str) -> Any:
    lastError: ImportError | None = None
    candidates = (
        f"_ghost_feature_pack_{packId}.{moduleName}",
        f"{packId}.{moduleName}",
        f"features.{packId}.{moduleName}",
    )
    for candidate in candidates:
        try:
            return importlib.import_module(candidate)
        except ImportError as error:
            lastError = error

    if lastError is not None:
        raise lastError
    raise ImportError(f"无法导入 Pack 模块: {packId}.{moduleName}")


_httpPackModule = _importPackModule("http_pack", "pack")
_httpTaskModule = _importPackModule("http_pack", "task")
HttpPack = _httpPackModule.HttpPack
HttpTask = _httpTaskModule.HttpTask
HttpTaskStage = _httpTaskModule.HttpTaskStage


def buildProxyUrl(source: str) -> str:
    proxySite = str(getSelectedProxySite()).strip()
    if not proxySite:
        raise ValueError("GitHub Pack 缺少可用的代理站")
    return f"{proxySite.rstrip('/')}/{source.strip().lstrip('/')}"


def _normalizeSize(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return SpecialFileSize.UNKNOWN
    if value <= 0:
        return SpecialFileSize.UNKNOWN
    return value


class GitHubHttpTaskStage(HttpTaskStage):
    recordTaskPackId = _GITHUB_PACK_ID
    recordTaskKind = _GITHUB_TASK_KIND
    recordTaskVersion = _GITHUB_TASK_VERSION
    recordKind = _HTTP_STAGE_KIND
    recordVersion = _HTTP_STAGE_VERSION

    async def run(self) -> None:
        await super().run()

    def reset(self, notifyTask: bool = True) -> None:
        super().reset(notifyTask=notifyTask)

    def snapshot(self):  # type: ignore[override]
        return super().snapshot()


class GitHubDownloadTask(HttpTask):
    recordPackId = _GITHUB_PACK_ID
    recordKind = _GITHUB_TASK_KIND
    recordVersion = _GITHUB_TASK_VERSION

    originalSource: str
    proxySource: str

    def __init__(
        self,
        *,
        id: str | None = None,
        config: TaskConfig,
        proxySource: str | None = None,
        stages: list[TaskStage] | None = None,
        totalBytes: int | None = None,
        supportsRange: bool = True,
        createdAt: int | None = None,
    ) -> None:
        normalizedConfig = self._normalizeConfig(config)
        self.originalSource = normalizedConfig.source
        self.proxySource = str(proxySource or buildProxyUrl(self.originalSource)).strip()
        proxiedConfig = replace(normalizedConfig, source=self.proxySource)
        resolvedStages = stages or [
            GitHubHttpTaskStage(
                id=f"github-http-stage-{uuid4().hex}",
                stageIndex=1,
                url=self.proxySource,
                fileSize=_normalizeSize(totalBytes),
                headers=proxiedConfig.headers,
                proxies=proxiedConfig.proxies,
                resolvePath="",
                blockNum=proxiedConfig.chunks,
                supportsRange=supportsRange,
                kind=_HTTP_STAGE_KIND,
                version=_HTTP_STAGE_VERSION,
                name="GitHub 下载",
            )
        ]

        super().__init__(
            id=id or f"github-task-{uuid4().hex}",
            config=proxiedConfig,
            stages=resolvedStages,
            totalBytes=totalBytes,
            supportsRange=supportsRange,
            createdAt=createdAt,
        )
        self.packId = _GITHUB_PACK_ID
        self.kind = _GITHUB_TASK_KIND
        self.version = _GITHUB_TASK_VERSION
        self.config = normalizedConfig
        self.url = self.originalSource
        self.syncOutput()

    @classmethod
    def fromHttpTask(
        cls,
        *,
        originalSource: str,
        httpTask: Task,
    ) -> "GitHubDownloadTask":
        if not isinstance(httpTask, HttpTask):
            raise TypeError(f"GitHub Pack 需要 HttpTask，实际为 {type(httpTask).__name__}")

        httpConfig = cast(TaskConfig, httpTask.config)
        originalConfig = TaskConfig(
            source=originalSource,
            folder=Path(httpConfig.folder),
            name=httpConfig.name,
            headers=dict(httpConfig.headers),
            proxies=None if httpConfig.proxies is None else dict(httpConfig.proxies),
            chunks=httpConfig.chunks,
        )
        return cls(
            config=originalConfig,
            proxySource=httpConfig.source,
            totalBytes=cast(int, getattr(httpTask, "totalBytes", SpecialFileSize.UNKNOWN)),
            supportsRange=bool(getattr(httpTask, "supportsRange", True)),
        )

    def configure(self, config: TaskConfig) -> None:
        normalizedConfig = self._normalizeConfig(config)
        proxySource = buildProxyUrl(normalizedConfig.source)
        shouldRefreshDownloadInfo = (
            proxySource != self.proxySource
            or normalizedConfig.headers != self.config.headers
            or normalizedConfig.proxies != self.config.proxies
        )

        self.originalSource = normalizedConfig.source
        self.proxySource = proxySource
        self.url = self.originalSource
        self._refreshDownloadInfoOnNextRun = (
            self._refreshDownloadInfoOnNextRun or shouldRefreshDownloadInfo
        )
        self.config = normalizedConfig
        self.syncOutput()
        _ = self.dispatchToStages("configure", replace(normalizedConfig, source=proxySource))

    def syncOutput(self) -> None:
        super().syncOutput()

    def reset(self) -> None:
        super().reset()

    def snapshot(self):  # type: ignore[override]
        return super().snapshot()

    def editForm(self, _mode: str) -> TaskForm | None:
        return TaskForm(
            title="编辑 GitHub 下载任务",
            fields=(
                FormField(
                    key="source",
                    label="GitHub 链接",
                    kind="text",
                    placeholder="输入 GitHub 文件链接",
                ),
                FormField(
                    key="name",
                    label="文件名",
                    kind="text",
                    placeholder="输入输出文件名",
                ),
                FormField(
                    key="folder",
                    label="下载目录",
                    kind="folder",
                    placeholder="选择输出目录",
                ),
                FormField(
                    key="headers",
                    label="请求头",
                    kind="headers",
                    note="使用 key: value 的格式，每行一项",
                ),
                FormField(
                    key="proxies",
                    label="代理",
                    kind="proxy",
                    note="使用 key: value 的格式，每行一项；留空表示不使用代理",
                ),
                FormField(
                    key="chunks",
                    label="分块数",
                    kind="int",
                    min=1,
                    max=256,
                ),
            ),
        )

    def persistenceState(self) -> dict[str, object]:
        state = super().persistenceState()
        state["proxySource"] = self.proxySource
        return state

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        rawProxySource = state.get("proxySource")
        if isinstance(rawProxySource, str) and rawProxySource.strip():
            self.proxySource = rawProxySource.strip()
        else:
            self.proxySource = buildProxyUrl(self.config.source)

        super().restorePersistentState(state)
        self.originalSource = self.config.source
        self.url = self.originalSource
        _ = self.dispatchToStages("configure", replace(self.config, source=self.proxySource))
        self.syncOutput()


__all__ = [
    "GitHubDownloadTask",
    "GitHubHttpTaskStage",
    "HttpPack",
    "HttpTask",
    "HttpTaskStage",
    "buildProxyUrl",
]
