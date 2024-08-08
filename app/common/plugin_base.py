from abc import ABC, abstractmethod


class PluginBase(ABC):

    @abstractmethod
    def __init__(self, mainWindow):
        """
        插件基类
        """

        self.name: str = "PluginBase"
        self.version: str = "1.0.0"
        self.author: str = "Author"
        self.icon: str = ":/plugins/example.png"
        self.description: str = "PluginBaseDescription"

        self.mainWindow = mainWindow

    @abstractmethod
    def load(self):
        """
        插件加载
        """

        pass
