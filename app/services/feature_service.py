import os
import sys
import importlib.util
from typing import TYPE_CHECKING, Dict, Any, Callable
from pathlib import Path

if TYPE_CHECKING:
    from app.view.windows.main_window import MainWindow


class FeatureService:
    """从 features 文件夹加载 features pack, 当 CoreService 询问时, 返回对应动态加载的函数"""

    def __init__(self):
        self.parseFunction: Dict[str, Callable] = {}
        self.availableTask: Dict[str, Any] = {}
        self.loadedPacks: Dict[str, Any] = {}
        self.featuresPath = Path(__file__).parent.parent.parent / "features"

    def getParseFunction(self, url: str):
        """返回对应 url 的解析函数"""
        # TODO: 实现 URL 匹配逻辑，返回对应的解析函数
        return None

    def getAvailableTask(self):
        # TODO: 实现获取可用任务类型的逻辑
        return self.availableTask

    def discoverFeaturePacks(self) -> list:
        """发现 features 文件夹中的所有 feature packs"""
        featurePacks = []
        
        if not self.featuresPath.exists():
            print(f"警告: features 文件夹不存在: {self.featuresPath}")
            return featurePacks
        
        # 遍历 features 目录下的所有子目录
        for item in self.featuresPath.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                packPath = item / "pack.py"
                if packPath.exists():
                    featurePacks.append({
                        'name': item.name,
                        'path': str(packPath),
                        'directory': str(item)
                    })
        
        return featurePacks

    def loadFeaturePack(self, packInfo: dict, mainWindow: "MainWindow"):
        """加载单个 feature pack"""
        try:
            # 动态导入 pack.py 模块
            spec = importlib.util.spec_from_file_location(
                f"feature_pack_{packInfo['name']}", 
                packInfo['path']
            )
            
            if spec is None or spec.loader is None:
                print(f"错误: 无法加载 feature pack: {packInfo['name']}")
                return False
            
            module = importlib.util.module_from_spec(spec)
            
            # 添加模块到 sys.path 以便相对导入
            sys.path.insert(0, packInfo['directory'])
            try:
                spec.loader.exec_module(module)
            finally:
                # 移除临时添加的路径
                if packInfo['directory'] in sys.path:
                    sys.path.remove(packInfo['directory'])
            
            # 查找 FeaturePackBase 的子类
            from app.bases.interfaces import FeaturePackBase
            
            featurePackClass = None
            for attrName in dir(module):
                attr = getattr(module, attrName)
                if (isinstance(attr, type) and 
                    issubclass(attr, FeaturePackBase) and 
                    attr != FeaturePackBase):
                    featurePackClass = attr
                    break
            
            if featurePackClass is None:
                print(f"警告: 在 {packInfo['name']} 中未找到 FeaturePackBase 的子类")
                return False
            
            # 实例化并加载 feature pack
            packInstance = featurePackClass()
            packInstance.load(mainWindow)
            
            # 保存加载的 pack 信息
            self.loadedPacks[packInfo['name']] = {
                'instance': packInstance,
                'module': module,
                'class': featurePackClass
            }
            
            print(f"✓ 成功加载 feature pack: {packInfo['name']}")
            return True
            
        except Exception as e:
            print(f"✗ 加载 feature pack 失败 {packInfo['name']}: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def loadFeatures(self, mainWindow: "MainWindow"):
        """从 ./features 文件夹自动发现并加载所有 feature packs"""
        print("开始加载 feature packs...")
        
        # 发现所有 feature packs
        featurePacks = self.discoverFeaturePacks()
        
        if not featurePacks:
            print("未发现任何 feature packs")
            return
        
        print(f"发现 {len(featurePacks)} 个 feature packs: {[pack['name'] for pack in featurePacks]}")
        
        # 加载每个 feature pack
        loadedCount = 0
        for packInfo in featurePacks:
            if self.loadFeaturePack(packInfo, mainWindow):
                loadedCount += 1
        
        print(f"feature packs 加载完成: {loadedCount}/{len(featurePacks)} 个成功加载")

featureService = FeatureService()
