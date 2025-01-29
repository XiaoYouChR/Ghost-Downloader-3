import json
from abc import ABC, abstractmethod
from copy import deepcopy
from pathlib import Path
from re import compile

from PySide6.QtCore import QObject
from PySide6.QtGui import QPixmap
from qfluentwidgets import ConfigItem, exceptionHandler

from app.common.config import cfg


class PluginConfigBase(QObject):
    """ Config of Plugins """

    def __init__(self, pluginName):
        super().__init__()
        print(f'{cfg.appPath}plugins/{pluginName}_config.json')
        self.file = Path(f'{cfg.appPath}plugins/{pluginName}_config.json')
        self.load()

    def get(self, item):
        """ get the value of config item """
        return item.value

    def set(self, item, value, save=True, copy=True):
        """ set the value of config item

        Parameters
        ----------
        item: ConfigItem
            config item

        value:
            the new value of config item

        save: bool
            whether to save the change to config file

        copy: bool
            whether to deep copy the new value
        """
        if item.value == value:
            return

        # deepcopy new value
        try:
            item.value = deepcopy(value) if copy else value
        except:
            item.value = value

        if save:
            self.save()

        if item.restart:
            cfg.appRestartSig.emit()

    def toDict(self, serialize=True):
        """ convert config items to `dict` """
        items = {}
        for name in dir(self._cfg.__class__):
            item = getattr(self._cfg.__class__, name)
            if not isinstance(item, ConfigItem):
                continue

            value = item.serialize() if serialize else item.value
            if not items.get(item.group):
                if not item.name:
                    items[item.group] = value
                else:
                    items[item.group] = {}

            if item.name:
                items[item.group][item.name] = value

        return items

    def save(self):
        """ save config """
        print("save")
        self._cfg.file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._cfg.file, "w", encoding="utf-8") as f:
            json.dump(self._cfg.toDict(), f, ensure_ascii=False, indent=4)
            print("save success")

    @exceptionHandler()
    def load(self, file=None, config=None):
        """ load config

        Parameters
        ----------
        file: str or Path
            the path of json config file

        config: Config
            config object to be initialized
        """
        if isinstance(config, PluginConfigBase):
            self._cfg = config

        if isinstance(file, (str, Path)):
            self._cfg.file = Path(file)

        try:
            with open(self._cfg.file, encoding="utf-8") as f:
                cfg = json.load(f)
        except:
            cfg = {}

        # map config items'key to item
        items = {}
        for name in dir(self._cfg.__class__):
            item = getattr(self._cfg.__class__, name)
            if isinstance(item, ConfigItem):
                items[item.key] = item

        # update the value of config item
        for k, v in cfg.items():
            if not isinstance(v, dict) and items.get(k) is not None:
                items[k].deserializeFrom(v)
            elif isinstance(v, dict):
                for key, value in v.items():
                    key = k + "." + key
                    if items.get(key) is not None:
                        items[key].deserializeFrom(value)


class PluginBase(ABC):

    @abstractmethod
    def __init__(self, name:str, version:str, author:str, icon:QPixmap, description:str, mainWindow, registerUrlRegularExpression:compile = None):
        """
        插件基类
        用于给用户提供插件的基础信息
        """

        self.name: str = name
        self.version: str = version
        self.author: str = author
        self.icon: QPixmap = icon
        self.description: str = description

        self.registerUrlRegularExpression: compile = registerUrlRegularExpression

        # If you need
        # self.config = PluginConfigBase(name)

        self.mainWindow = mainWindow


    def parseUrl(self, url: str) -> tuple[str, str, int]:
        """
        解析链接, 用于代替默认的 getLinkInfo
        返回 URL, FileName, FileSize
        """
        pass

    @abstractmethod
    def load(self):
        """
        插件加载
        """
        pass

    @abstractmethod
    def unload(self):
        """
        插件卸载
        """
        pass

    @abstractmethod
    def uninstall(self):
        """
        插件删除
        """
        pass
