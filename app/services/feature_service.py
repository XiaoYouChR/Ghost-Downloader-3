# pyright: reportImportCycles=false, reportDeprecated=false, reportExplicitAny=false, reportUnannotatedClassAttribute=false, reportUnknownParameterType=false, reportMissingTypeArgument=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportAny=false, reportMissingParameterType=false, reportUnusedImport=false, reportGeneralTypeIssues=false, reportArgumentType=false, reportUnusedCallResult=false, reportUnknownLambdaType=false

from __future__ import annotations

import importlib.util
import sys
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Any
from collections.abc import Mapping
from urllib.parse import urlparse

from loguru import logger

from app.feature_pack.api import DefaultFeatureService
from app.feature_pack.api import FeaturePack as V1FeaturePack
from app.feature_pack.api import Task as V1Task
from app.feature_pack.api import TaskInput
from app.feature_pack.internal.add_task import buildAddTaskInput
from app.bases.interfaces import FeaturePack
from app.bases.models import Task
from app.supports.config import cfg
from app.supports.utils import getProxies

if TYPE_CHECKING:
    from app.view.components.cards import ParseSettingCard

    from app.view.windows.main_window import MainWindow


class FeatureService:
    """从 features 文件夹加载 features pack, 当 CoreService 询问时, 返回对应动态加载的函数"""

    def __init__(self):
        self.loadedPacks: Dict[str, Any] = {}
        self.featuresPath = Path(__file__).parent.parent.parent / "features"
        self.sortedPacksCache: list[tuple[str, FeaturePack]] = []

    def discoverFeaturePacks(self) -> list:
        """发现 features 文件夹中的所有 feature packs"""
        featurePacks = []

        if not self.featuresPath.exists():
            logger.warning("features 文件夹不存在: {}", self.featuresPath)
            return featurePacks

        for item in self.featuresPath.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                manifest = self._loadPackManifest(item)
                if manifest is None:
                    continue

                featurePacks.append(
                    {
                        "name": item.name,
                        "path": str(item / manifest["entry"]),
                        "directory": str(item),
                        "dependencies": manifest["dependencies"],
                        "manifestPath": str(item / "manifest.toml"),
                    }
                )

        featurePacks.sort(key=lambda pack: pack["name"])
        return featurePacks

    def _loadPackManifest(self, packDirectory: Path) -> dict[str, Any] | None:
        manifestPath = packDirectory / "manifest.toml"
        if not manifestPath.exists():
            logger.warning("FeaturePack 缺少 manifest.toml: {}", packDirectory)
            return None

        try:
            manifest = tomllib.loads(manifestPath.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("无法读取 FeaturePack manifest {}: {}", manifestPath, repr(e))
            return None

        packConfig = manifest.get("pack")
        if not isinstance(packConfig, dict):
            logger.warning("FeaturePack manifest 缺少 [pack] 节: {}", manifestPath)
            return None

        entry = packConfig.get("entry", "pack.py")
        if not isinstance(entry, str) or not entry.strip():
            logger.warning("FeaturePack manifest 的 entry 无效: {}", manifestPath)
            return None

        packPath = packDirectory / entry
        if not packPath.exists():
            logger.warning("FeaturePack 入口文件不存在: {}", packPath)
            return None

        dependencies = packConfig.get("dependencies", [])
        if not isinstance(dependencies, list) or any(
            not isinstance(dependency, str) or not dependency
            for dependency in dependencies
        ):
            logger.warning("FeaturePack manifest 的 dependencies 无效: {}", manifestPath)
            return None

        return {
            "entry": entry,
            "dependencies": tuple(dependencies),
        }

    def _sortFeaturePacksByDependencies(self, featurePacks: list[dict]) -> list[dict]:
        packInfoByName = {pack["name"]: pack for pack in featurePacks}
        visiting: list[str] = []
        visited: set[str] = set()
        ordered: list[dict] = []
        skipped: set[str] = set()

        def visit(packName: str):
            if packName in visited:
                return
            if packName in skipped:
                raise ValueError(f"{packName} 依赖的 FeaturePack 已被跳过")
            if packName in visiting:
                cycleStart = visiting.index(packName)
                cyclePath = visiting[cycleStart:] + [packName]
                raise ValueError(f"检测到 FeaturePack 循环依赖: {' -> '.join(cyclePath)}")

            visiting.append(packName)
            packInfo = packInfoByName[packName]

            for dependency in packInfo.get("dependencies", ()):
                if dependency not in packInfoByName:
                    raise ValueError(f"{packName} 依赖未找到的 FeaturePack: {dependency}")
                visit(dependency)

            visiting.pop()
            visited.add(packName)
            ordered.append(packInfo)

        for packInfo in featurePacks:
            packName = packInfo["name"]
            try:
                visit(packName)
            except Exception as e:
                skipped.add(packName)
                visiting.clear()
                logger.opt(exception=e).error("跳过 FeaturePack {}", packName)

        return [pack for pack in ordered if pack["name"] not in skipped]

    def _refreshSortedPacksCache(self):
        self.sortedPacksCache = [
            (name, info["instance"])
            for name, info in self.loadedPacks.items()
            if isinstance(info.get("instance"), FeaturePack)
        ]
        self.sortedPacksCache.sort(key=lambda item: (item[1].priority, item[0]))

    def _loadPackConfig(self, packInstance: FeaturePack, mainWindow: "MainWindow"):
        packConfig = packInstance.config
        if packConfig is None:
            return

        settingPage = getattr(mainWindow, "settingPage", None)
        if settingPage is None:
            return

        packConfig.loadSettingCards(settingPage)

    def getDialogCards(self, parent) -> list["ParseSettingCard"]:
        cards = []
        for packName, packInstance in self.sortedPacksCache:
            packConfig = packInstance.config
            if packConfig is None:
                continue

            try:
                cards.extend(packConfig.getDialogCards(parent))
            except Exception as e:
                logger.opt(exception=e).error("获取 FeaturePack 对话框设置项失败 {}", packName)
        return cards

    def loadFeaturePack(
        self,
        packInfo: dict,
        mainWindow: "MainWindow",
        refreshCache: bool = True,
    ):
        """加载单个 feature pack"""
        try:
            packageName = packInfo["name"]
            moduleName = packageName

            spec = importlib.util.spec_from_file_location(
                moduleName,
                packInfo["path"],
                submodule_search_locations=[packInfo["directory"]],
            )

            if spec is None or spec.loader is None:
                e = RuntimeError("无法创建模块规格")
                logger.opt(exception=e).error("无法加载 FeaturePack {}", packInfo["name"])
                return False

            module = importlib.util.module_from_spec(spec)

            try:
                sys.modules[moduleName] = module
                spec.loader.exec_module(module)
            except Exception as e:
                if moduleName in sys.modules:
                    del sys.modules[moduleName]
                raise e

            featurePackClass = None
            for attrName in dir(module):
                attr = getattr(module, attrName)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, FeaturePack)
                    and attr != FeaturePack
                    and attr.__module__ == moduleName
                ):
                    featurePackClass = attr
                    break

            if featurePackClass is None:
                logger.warning("在 {} 中未找到 FeaturePack 子类", packInfo["name"])
                return False

            packInstance = featurePackClass()
            self._loadPackConfig(packInstance, mainWindow)
            packInstance.load(mainWindow)

            self.loadedPacks[packInfo["name"]] = {
                "instance": packInstance,
                "module": module,
                "class": featurePackClass,
            }
            if refreshCache:
                self._refreshSortedPacksCache()

            logger.success("成功加载 FeaturePack: {}", packInfo["name"])
            return True

        except Exception as e:
            moduleName = packInfo["name"]
            if moduleName in sys.modules:
                del sys.modules[moduleName]
            logger.opt(exception=e).error("加载 FeaturePack 失败 {}", packInfo["name"])
            return False

    def _matchPackForUrl(self, url: str) -> tuple[str, FeaturePack] | tuple[None, None]:
        for packName, packInstance in self.sortedPacksCache:
            try:
                if packInstance.canHandle(url):
                    return packName, packInstance
            except Exception as e:
                logger.opt(exception=e).error("FeaturePack.canHandle 失败 {}", packName)
        return None, None

    def getPackForUrl(
        self,
        url: str,
    ) -> tuple[str, str | None, FeaturePack | None]:
        url = str(url).strip()
        if not url:
            return "", None, None

        packName, packInstance = self._matchPackForUrl(url)
        if packInstance is not None:
            return url, packName, packInstance

        if urlparse(url).scheme:
            return url, None, None

        implicitUrl = f"http://{url}"
        packName, packInstance = self._matchPackForUrl(implicitUrl)
        if packInstance is None:
            return url, None, None

        return implicitUrl, packName, packInstance

    def canHandle(self, url: str) -> bool:
        _, _, packInstance = self.getPackForUrl(url)
        return packInstance is not None

    def canCreateTaskFromPayload(self, url: str) -> bool:
        _, _, packInstance = self.getPackForUrl(url)
        if packInstance is None:
            return False

        return type(packInstance).createTaskFromPayload is not FeaturePack.createTaskFromPayload

    def getPackForTask(self, task: Task) -> tuple[str, FeaturePack] | tuple[None, None]:
        cachedPackName = getattr(task, "_featurePackName", None)
        if (
            isinstance(cachedPackName, str)
            and cachedPackName in self.loadedPacks
            and isinstance(self.loadedPacks[cachedPackName]["instance"], FeaturePack)
        ):
            return cachedPackName, self.loadedPacks[cachedPackName]["instance"]

        for packName, packInstance in self.sortedPacksCache:
            try:
                if packInstance.canHandleTask(task):
                    return packName, packInstance
            except Exception as e:
                logger.opt(exception=e).error("FeaturePack.canHandleTask 失败 {}", packName)
        return None, None

    async def parse(self, payload: dict) -> Task:
        url = str(payload.get("url", "")).strip()
        if not url:
            raise ValueError("URL 不能为空")

        resolvedUrl, packName, packInstance = self.getPackForUrl(url)
        if packInstance is None:
            raise ValueError(f"未找到可处理该链接的 FeaturePack: {url}")

        if payload.get("url") != resolvedUrl:
            payload = payload.copy()
            payload["url"] = resolvedUrl

        task = await packInstance.parse(payload)
        setattr(task, "_featurePackName", packName)
        return task

    async def createTaskFromPayload(self, payload: dict) -> Task:
        url = str(payload.get("url", "")).strip()
        if not url:
            raise ValueError("URL 不能为空")

        resolvedUrl, packName, packInstance = self.getPackForUrl(url)
        if packInstance is None:
            raise ValueError(f"未找到可处理该链接的 FeaturePack: {url}")

        if payload.get("url") != resolvedUrl:
            payload = payload.copy()
            payload["url"] = resolvedUrl

        task = await packInstance.createTaskFromPayload(payload)
        if task is None:
            raise ValueError(f"FeaturePack 不支持从已有 Payload 直接创建任务: {resolvedUrl}")
        setattr(task, "_featurePackName", packName)
        return task

    def createTaskCard(self, task: Task, parent=None):
        packName, packInstance = self.getPackForTask(task)
        if packInstance is None:
            raise ValueError(f"未找到 Task 对应的 FeaturePack: {task.taskId}")

        card = packInstance.createTaskCard(task, parent)
        if card is None:
            raise ValueError(f"FeaturePack 未提供 TaskCard: {packName}")
        return card

    def createResultCard(self, task: Task, parent=None):
        packName, packInstance = self.getPackForTask(task)
        if packInstance is None:
            raise ValueError(f"未找到 Task 对应的 FeaturePack: {task.taskId}")

        card = packInstance.createResultCard(task, parent)
        if card is None:
            raise ValueError(f"FeaturePack 未提供 ResultCard: {packName}")
        return card

    def loadFeatures(self, mainWindow: "MainWindow"):
        """从 ./features 文件夹自动发现并加载所有 feature packs"""
        logger.info("开始加载 FeaturePacks")
        self.sortedPacksCache = []

        featurePacks = self.discoverFeaturePacks()

        if not featurePacks:
            logger.warning("未发现任何 FeaturePack")
            return

        logger.info(
            "发现 {} 个 FeaturePack: {}",
            len(featurePacks),
            [pack["name"] for pack in featurePacks],
        )

        featurePacks = self._sortFeaturePacksByDependencies(featurePacks)
        logger.info(
            "FeaturePack 加载顺序: {}",
            [pack["name"] for pack in featurePacks],
        )

        loadedCount = 0
        for packInfo in featurePacks:
            if self.loadFeaturePack(packInfo, mainWindow, refreshCache=False):
                loadedCount += 1
        self._refreshSortedPacksCache()

        if loadedCount == len(featurePacks):
            logger.success("FeaturePack 加载完成: {}/{} 个成功加载", loadedCount, len(featurePacks))
            return

        logger.warning("FeaturePack 加载完成: {}/{} 个成功加载", loadedCount, len(featurePacks))


class HostFeatureService(DefaultFeatureService):
    """
    V1-backed host service exposed through the historical service module.

    The main window, CoreService, BrowserService and add-task dialog now call
    the V1 service surface directly. A few legacy helper names remain here only
    for the final V0 removal task.
    """

    def loadFeatures(self, mainWindow: "MainWindow") -> None:
        self.loadPacks(mainWindow)
        settingPage = getattr(mainWindow, "settingPage", None)
        if settingPage is not None:
            self.installSettings(settingPage)

    def getDialogCards(self, _parent: object) -> list["ParseSettingCard"]:
        return []

    def canHandle(self, source: str) -> bool:
        _resolvedSource, pack = self._resolveSource(source)
        return pack is not None

    def canCreateTaskFromPayload(self, source: str) -> bool:
        _resolvedSource, pack = self._resolveSource(source)
        if pack is None:
            return False

        return callable(getattr(pack, "createTaskFromPayload", None))

    def getPackForUrl(
        self,
        source: str,
    ) -> tuple[str, str | None, V1FeaturePack | None]:
        resolvedSource, pack = self._resolveSource(source)
        if pack is None:
            return str(source).strip(), None, None

        return resolvedSource, pack.manifest.id, pack

    async def parse(self, payload: Mapping[str, object]) -> V1Task:
        source = self._readPayloadSource(payload)
        resolvedSource, pack = self._resolveSource(source)
        if pack is None:
            raise ValueError(f"未找到可处理该链接的 FeaturePack: {source}")

        legacyParse = getattr(pack, "parse", None)
        if callable(legacyParse):
            task = await legacyParse(self._payloadWithResolvedSource(payload, resolvedSource))
            if isinstance(task, V1Task):
                self._rememberTask(task)
                return task

        return await self.createTask(self._buildInput(payload, resolvedSource))

    async def createTaskFromPayload(self, payload: Mapping[str, object]) -> V1Task:
        source = self._readPayloadSource(payload)
        resolvedSource, pack = self._resolveSource(source)
        if pack is None:
            raise ValueError(f"未找到可处理该链接的 FeaturePack: {source}")

        legacyCreate = getattr(pack, "createTaskFromPayload", None)
        if callable(legacyCreate):
            task = await legacyCreate(self._payloadWithResolvedSource(payload, resolvedSource))
            if task is None:
                raise ValueError(f"FeaturePack 不支持从已有 Payload 直接创建任务: {resolvedSource}")
            if not isinstance(task, V1Task):
                raise TypeError("FeaturePack.createTaskFromPayload() 必须返回新版 Task")
            self._rememberTask(task)
            return task

        return await self.createTask(self._buildInput(payload, resolvedSource))

    def _resolveSource(self, source: str) -> tuple[str, V1FeaturePack | None]:
        normalizedSource = str(source).strip()
        if not normalizedSource:
            return "", None

        pack = self.packForSource(normalizedSource)
        if pack is not None:
            return normalizedSource, pack

        if urlparse(normalizedSource).scheme:
            return normalizedSource, None

        implicitSource = f"http://{normalizedSource}"
        return implicitSource, self.packForSource(implicitSource)

    def _readPayloadSource(self, payload: Mapping[str, object]) -> str:
        source = payload.get("url")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("URL 不能为空")
        return source.strip()

    def _payloadWithResolvedSource(
        self,
        payload: Mapping[str, object],
        resolvedSource: str,
    ) -> dict[str, object]:
        resolvedPayload = dict(payload)
        resolvedPayload["url"] = resolvedSource
        return resolvedPayload

    def _buildInput(
        self,
        payload: Mapping[str, object],
        resolvedSource: str,
    ) -> TaskInput:
        rawFolder = payload.get("path")
        folder = (
            Path(rawFolder)
            if isinstance(rawFolder, (str, Path))
            else Path(cfg.downloadFolder.value)
        )
        rawHeaders = payload.get("headers")
        rawProxies = payload.get("proxies")
        rawChunks = payload.get("preBlockNum")
        rawName = payload.get("filename")
        rawSize = payload.get("size")

        return buildAddTaskInput(
            source=resolvedSource,
            folder=folder,
            headers=rawHeaders if isinstance(rawHeaders, Mapping) else None,
            proxies=(
                rawProxies
                if isinstance(rawProxies, Mapping)
                else getProxies()
            ),
            chunks=rawChunks if isinstance(rawChunks, int) else 1,
            name=rawName if isinstance(rawName, str) else "",
            size=rawSize if isinstance(rawSize, int) else 0,
            hints=(
                {
                    key: value
                    for key, value in payload.items()
                    if key not in {"url", "path", "filename", "headers", "proxies", "preBlockNum", "size"}
                },
            ),
        )


featureService = HostFeatureService()
