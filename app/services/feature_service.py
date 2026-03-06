import importlib.util
import sys
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Any

from app.bases.interfaces import FeaturePack
from app.bases.models import Task

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
            print(f"警告: features 文件夹不存在: {self.featuresPath}")
            return featurePacks

        for item in self.featuresPath.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                packPath = item / "pack.py"
                if not packPath.exists():
                    continue

                featurePacks.append(
                    {
                        "name": item.name,
                        "path": str(packPath),
                        "directory": str(item),
                    }
                )

        return featurePacks

    def _refreshSortedPacksCache(self):
        self.sortedPacksCache = [
            (name, info["instance"])
            for name, info in self.loadedPacks.items()
            if isinstance(info.get("instance"), FeaturePack)
        ]
        self.sortedPacksCache.sort(key=lambda item: (-item[1].priority, item[0]))

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
                print(
                    f"✗ 获取 FeaturePack 对话框设置项失败 {packName}: {repr(e)}\n{traceback.format_exc()}"
                )
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
            moduleName = f"{packageName}.pack"

            spec = importlib.util.spec_from_file_location(
                moduleName,
                packInfo["path"],
                submodule_search_locations=[packInfo["directory"]],
            )

            if spec is None or spec.loader is None:
                print(f"错误: 无法加载 feature pack: {packInfo['name']}")
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
                print(f"警告: 在 {packInfo['name']} 中未找到 FeaturePack 的子类")
                return False

            packInstance = featurePackClass()
            packInstance.load(mainWindow)

            self._loadPackConfig(packInstance, mainWindow)

            self.loadedPacks[packInfo["name"]] = {
                "instance": packInstance,
                "module": module,
                "class": featurePackClass,
            }
            if refreshCache:
                self._refreshSortedPacksCache()

            print(f"✓ 成功加载 feature pack: {packInfo['name']}")
            return True

        except Exception as e:
            moduleName = f"{packInfo['name']}.pack"
            if moduleName in sys.modules:
                del sys.modules[moduleName]
            print(f"✗ 加载 feature pack 失败 {packInfo['name']}: {str(e)}")
            traceback.print_exc()
            return False

    def getPackForUrl(self, url: str) -> tuple[str, FeaturePack] | tuple[None, None]:
        for packName, packInstance in self.sortedPacksCache:
            try:
                if packInstance.canHandle(url):
                    return packName, packInstance
            except Exception as e:
                print(
                    f"✗ FeaturePack.canHandle 失败 {packName}: {repr(e)}\n{traceback.format_exc()}"
                )
        return None, None

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
                print(
                    f"✗ FeaturePack.canHandleTask 失败 {packName}: {repr(e)}\n{traceback.format_exc()}"
                )
        return None, None

    async def parse(self, payload: dict) -> Task:
        url = str(payload.get("url", "")).strip()
        if not url:
            raise ValueError("URL 不能为空")

        packName, packInstance = self.getPackForUrl(url)
        if packInstance is None:
            raise ValueError(f"未找到可处理该链接的 FeaturePack: {url}")

        task = await packInstance.parse(payload)
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
        print("开始加载 feature packs...")
        self.sortedPacksCache = []

        featurePacks = self.discoverFeaturePacks()

        if not featurePacks:
            print("未发现任何 feature packs")
            return

        print(
            f"发现 {len(featurePacks)} 个 feature packs: {[pack['name'] for pack in featurePacks]}"
        )

        loadedCount = 0
        for packInfo in featurePacks:
            if self.loadFeaturePack(packInfo, mainWindow, refreshCache=False):
                loadedCount += 1
        self._refreshSortedPacksCache()

        print(f"feature packs 加载完成: {loadedCount}/{len(featurePacks)} 个成功加载")


featureService = FeatureService()
