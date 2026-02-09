class FeatureService:
    def __init__(self):
        self.parseFunction = {}
        self.availableTask = {}

    """从 features 文件夹加载 features pack, 当 CoreService 询问时, 返回对应动态加载的函数"""
    def getParseFunction(self, url: str):
        """返回对应 url 的解析函数"""
        return None

    def getAvailableTask(self):
        ...

    def reloadFeatures(self):
        """从 ./features 文件夹加载 feature pack"""
        ...

featuresService = FeatureService()