import importlib.util
import sys
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from loguru import logger

from app.bases.interfaces import FeaturePack, FileType
from app.bases.models import Task
from app.supports.paths import executableDir

if TYPE_CHECKING:
    from app.view.components.cards import ParseSettingCard
    from app.view.windows.main_window import MainWindow


class FeatureService:
    def __init__(self):
        self._packs: dict[str, FeaturePack] = {}
        self._featuresPath = executableDir / "features"

    def _sortedPacks(self) -> list[tuple[str, FeaturePack]]:
        items = list(self._packs.items())
        items.sort(key=lambda item: (item[1].priority, item[0]))
        return items

    def _discover(self) -> list[dict]:
        featurePacks = []

        if not self._featuresPath.exists():
            logger.warning("features 文件夹不存在: {}", self._featuresPath)
            return featurePacks

        for item in self._featuresPath.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                manifest = self._manifest(item)
                if manifest is None:
                    continue

                featurePacks.append(
                    {
                        "name": item.name,
                        "path": str(item / manifest["entry"]),
                        "directory": str(item),
                        "dependencies": manifest["dependencies"],
                    }
                )

        featurePacks.sort(key=lambda pack: pack["name"])
        return featurePacks

    def _manifest(self, packDirectory: Path) -> dict[str, Any] | None:
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

    def _loadOrder(self, featurePacks: list[dict]) -> list[dict]:
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

    def _loadPack(self, packInfo: dict, mainWindow: "MainWindow", withSetup: bool = True):
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

            packConfig = packInstance.config
            if packConfig is not None:
                settingPage = getattr(mainWindow, "settingPage", None)
                if settingPage is not None:
                    packConfig.setupSettings(settingPage)

            # setup 是 GUI 侧动作（加界面/文件关联）；engine 进程 headless，只要 matches/parse
            if withSetup:
                packInstance.setup(mainWindow)
            self._packs[packInfo["name"]] = packInstance

            logger.success("成功加载 FeaturePack: {}", packInfo["name"])
            return True

        except Exception as e:
            moduleName = packInfo["name"]
            if moduleName in sys.modules:
                del sys.modules[moduleName]
            logger.opt(exception=e).error("加载 FeaturePack 失败 {}", packInfo["name"])
            return False

    def _toUrl(self, url: str) -> str:
        url = url.strip()
        if not url:
            return url
        if not urlparse(url).scheme:
            return f"http://{url}"
        return url

    def matches(self, url: str) -> bool:
        normalizedUrl = self._toUrl(url)
        return self.matchPack(normalizedUrl) is not None

    def matchPack(self, url: str) -> tuple[str, FeaturePack] | None:
        for packName, packInstance in self._sortedPacks():
            try:
                if packInstance.matches(url):
                    return packName, packInstance
            except Exception as e:
                logger.opt(exception=e).error("FeaturePack.matches 失败 {}", packName)
        return None

    def packOf(self, task: Task) -> FeaturePack | None:
        for pack in self._packs.values():
            if pack.packId == task.packId:
                return pack
        return None

    async def parse(self, payload: dict) -> Task:
        url = str(payload.get("url", "")).strip()
        if not url:
            raise ValueError("URL 不能为空")

        normalizedUrl = self._toUrl(url)
        result = self.matchPack(normalizedUrl)
        if result is None:
            raise ValueError(f"未找到可处理该链接的 FeaturePack: {url}")

        packName, packInstance = result

        if payload.get("url") != normalizedUrl:
            payload = payload.copy()
            payload["url"] = normalizedUrl

        return await packInstance.parse(payload)

    def taskCard(self, task: Task, parent=None):
        packInstance = self.packOf(task)
        if packInstance is None:
            # 旧版本残留 packId 找不到 pack 时回落, 而不是 raise 把整张列表炸掉
            logger.warning("未找到 Task 对应的 FeaturePack, 回落到 UniversalTaskCard: {}", task.packId)
            from app.view.components.cards import UniversalTaskCard
            return UniversalTaskCard(task, parent)
        return packInstance.taskCard(task, parent)

    def resultCard(self, task: Task, parent=None):
        packInstance = self.packOf(task)
        if packInstance is None:
            raise ValueError(f"未找到 Task 对应的 FeaturePack: {task.packId}")
        return packInstance.resultCard(task, parent)

    def dialogCards(self, parent) -> list["ParseSettingCard"]:
        cards = []
        for packName, packInstance in self._sortedPacks():
            packConfig = packInstance.config
            if packConfig is None:
                continue

            try:
                cards.extend(packConfig.dialogCards(parent))
            except Exception as e:
                logger.opt(exception=e).error("获取 FeaturePack 对话框设置项失败 {}", packName)
        return cards

    def fileTypes(self) -> list[FileType]:
        types = []
        for packName, packInstance in self._sortedPacks():
            try:
                types.extend(packInstance.fileTypes())
            except Exception as e:
                logger.opt(exception=e).error("获取 FeaturePack 文件类型失败 {}", packName)
        return types

    def load(self, mainWindow: "MainWindow", withSetup: bool = True):
        logger.info("开始加载 FeaturePacks")

        featurePacks = self._discover()

        if not featurePacks:
            logger.warning("未发现任何 FeaturePack")
            return

        logger.info(
            "发现 {} 个 FeaturePack: {}",
            len(featurePacks),
            [pack["name"] for pack in featurePacks],
        )

        featurePacks = self._loadOrder(featurePacks)
        logger.info(
            "FeaturePack 加载顺序: {}",
            [pack["name"] for pack in featurePacks],
        )

        loadedCount = 0
        for packInfo in featurePacks:
            if self._loadPack(packInfo, mainWindow, withSetup):
                loadedCount += 1

        if loadedCount == len(featurePacks):
            logger.success("FeaturePack 加载完成: {}/{} 个成功加载", loadedCount, len(featurePacks))
            return

        logger.warning("FeaturePack 加载完成: {}/{} 个成功加载", loadedCount, len(featurePacks))


featureService = FeatureService()
