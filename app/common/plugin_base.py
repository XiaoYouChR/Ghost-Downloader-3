import json
from abc import ABC, abstractmethod
from copy import deepcopy
from pathlib import Path
import re

from PySide6.QtCore import QObject
from PySide6.QtGui import QPixmap
from qfluentwidgets import ConfigItem, exceptionHandler, SettingCard, FluentIconBase, SwitchButton, IndicatorPosition, \
    Slider, HyperlinkButton, ColorDialog, isDarkTheme, ComboBox, OptionsConfigItem

from app.common.config import cfg, registerContentsByPlugins

from typing import Union

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QPushButton

class PluginConfigBase(QObject):
    """ Config of Plugins """

    def __init__(self, pluginName):
        super().__init__()
        print(f'{cfg.appPath}plugins/{pluginName}/config.json')
        self.file = Path(f'{cfg.appPath}plugins/{pluginName}/config.json')
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
    def load(self, file=None):
        """ load config

        Parameters
        ----------
        file: str or Path
            the path of json config file

        config: Config
            config object to be initialized
        """
        self._cfg = self

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


class SwitchSettingCard(SettingCard):
    """ Setting card with switch button """

    checkedChanged = Signal(bool)

    def __init__(self, config: PluginConfigBase, icon: Union[str, QIcon, FluentIconBase], title, content=None,
                 configItem: ConfigItem = None, parent=None):
        """
        Parameters
        ----------
        icon: str | QIcon | FluentIconBase
            the icon to be drawn

        title: str
            the title of card

        content: str
            the content of card

        configItem: ConfigItem
            configuration item operated by the card

        parent: QWidget
            parent widget
        """
        super().__init__(icon, title, content, parent)
        self.config = config
        self.configItem = configItem
        self.switchButton = SwitchButton(
            self.tr('Off'), self, IndicatorPosition.RIGHT)

        if configItem:
            self.setValue(self.config.get(configItem))
            configItem.valueChanged.connect(self.setValue)

        # add switch button to layout
        self.hBoxLayout.addWidget(self.switchButton, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.switchButton.checkedChanged.connect(self.__onCheckedChanged)

    def __onCheckedChanged(self, isChecked: bool):
        """ switch button checked state changed slot """
        self.setValue(isChecked)
        self.checkedChanged.emit(isChecked)

    def setValue(self, isChecked: bool):
        if self.configItem:
            self.config.set(self.configItem, isChecked)

        self.switchButton.setChecked(isChecked)
        self.switchButton.setText(
            self.tr('On') if isChecked else self.tr('Off'))

    def setChecked(self, isChecked: bool):
        self.setValue(isChecked)

    def isChecked(self):
        return self.switchButton.isChecked()


class RangeSettingCard(SettingCard):
    """ Setting card with a slider """

    valueChanged = Signal(int)

    def __init__(self, config: PluginConfigBase, configItem, icon: Union[str, QIcon, FluentIconBase], title, content=None, parent=None):
        """
        Parameters
        ----------
        configItem: RangeConfigItem
            configuration item operated by the card

        icon: str | QIcon | FluentIconBase
            the icon to be drawn

        title: str
            the title of card

        content: str
            the content of card

        parent: QWidget
            parent widget
        """
        super().__init__(icon, title, content, parent)
        self.config = config
        self.configItem = configItem
        self.slider = Slider(Qt.Horizontal, self)
        self.valueLabel = QLabel(self)
        self.slider.setMinimumWidth(268)

        self.slider.setSingleStep(1)
        self.slider.setRange(*configItem.range)
        self.slider.setValue(configItem.value)
        self.valueLabel.setNum(configItem.value)

        self.hBoxLayout.addStretch(1)
        self.hBoxLayout.addWidget(self.valueLabel, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(6)
        self.hBoxLayout.addWidget(self.slider, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.valueLabel.setObjectName('valueLabel')
        configItem.valueChanged.connect(self.setValue)
        self.slider.valueChanged.connect(self.__onValueChanged)

    def __onValueChanged(self, value: int):
        """ slider value changed slot """
        self.setValue(value)
        self.valueChanged.emit(value)

    def setValue(self, value):
        self.config.set(self.configItem, value)
        self.valueLabel.setNum(value)
        self.valueLabel.adjustSize()
        self.slider.setValue(value)


class PushSettingCard(SettingCard):
    """ Setting card with a push button """

    clicked = Signal()

    def __init__(self, config: PluginConfigBase, text, icon: Union[str, QIcon, FluentIconBase], title, content=None, parent=None):
        """
        Parameters
        ----------
        text: str
            the text of push button

        icon: str | QIcon | FluentIconBase
            the icon to be drawn

        title: str
            the title of card

        content: str
            the content of card

        parent: QWidget
            parent widget
        """
        super().__init__(icon, title, content, parent)
        self.config = config
        self.button = QPushButton(text, self)
        self.hBoxLayout.addWidget(self.button, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.button.clicked.connect(self.clicked)


class PrimaryPushSettingCard(PushSettingCard):
    """ Push setting card with primary color """

    def __init__(self, config: PluginConfigBase, text, icon, title, content=None, parent=None):
        super().__init__(config, text, icon, title, content, parent)
        self.button.setObjectName('primaryButton')


class HyperlinkCard(SettingCard):
    """ Hyperlink card """

    def __init__(self, config: PluginConfigBase, url, text, icon: Union[str, QIcon, FluentIconBase], title, content=None, parent=None):
        """
        Parameters
        ----------
        url: str
            the url to be opened

        text: str
            text of url

        icon: str | QIcon | FluentIconBase
            the icon to be drawn

        title: str
            the title of card

        content: str
            the content of card

        text: str
            the text of push button

        parent: QWidget
            parent widget
        """
        super().__init__(icon, title, content, parent)
        self.config = config
        self.linkButton = HyperlinkButton(url, text, self)
        self.hBoxLayout.addWidget(self.linkButton, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)


class ColorPickerButton(QToolButton):
    """ Color picker button """

    colorChanged = Signal(QColor)

    def __init__(self, config: PluginConfigBase, color: QColor, title: str, parent=None, enableAlpha=False):
        super().__init__(parent=parent)
        self.config = config
        self.title = title
        self.enableAlpha = enableAlpha
        self.setFixedSize(96, 32)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.setColor(color)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self.__showColorDialog)

    def __showColorDialog(self):
        """ show color dialog """
        w = ColorDialog(self.color, self.tr(
            'Choose ')+self.title, self.window(), self.enableAlpha)
        w.colorChanged.connect(self.__onColorChanged)
        w.exec()

    def __onColorChanged(self, color):
        """ color changed slot """
        self.setColor(color)
        self.colorChanged.emit(color)

    def setColor(self, color):
        """ set color """
        self.color = QColor(color)
        self.update()

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing)
        pc = QColor(255, 255, 255, 10) if isDarkTheme() else QColor(234, 234, 234)
        painter.setPen(pc)

        color = QColor(self.color)
        if not self.enableAlpha:
            color.setAlpha(255)

        painter.setBrush(color)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 5, 5)


class ColorSettingCard(SettingCard):
    """ Setting card with color picker """

    colorChanged = Signal(QColor)

    def __init__(self, config: PluginConfigBase, configItem, icon: Union[str, QIcon, FluentIconBase],
                 title: str, content: str = None, parent=None, enableAlpha=False):
        """
        Parameters
        ----------
        configItem: RangeConfigItem
            configuration item operated by the card

        icon: str | QIcon | FluentIconBase
            the icon to be drawn

        title: str
            the title of card

        content: str
            the content of card

        parent: QWidget
            parent widget

        enableAlpha: bool
            whether to enable the alpha channel
        """
        super().__init__(icon, title, content, parent)
        self.config = config
        self.configItem = configItem
        self.colorPicker = ColorPickerButton(
            self.config.get(configItem), title, self, enableAlpha)
        self.hBoxLayout.addWidget(self.colorPicker, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.colorPicker.colorChanged.connect(self.__onColorChanged)
        configItem.valueChanged.connect(self.setValue)

    def __onColorChanged(self, color: QColor):
        self.config.set(self.configItem, color)
        self.colorChanged.emit(color)

    def setValue(self, color: QColor):
        self.colorPicker.setColor(color)
        self.config.set(self.configItem, color)


class ComboBoxSettingCard(SettingCard):
    """ Setting card with a combo box """

    def __init__(self, config: PluginConfigBase, configItem: OptionsConfigItem, icon: Union[str, QIcon, FluentIconBase], title, content=None, texts=None, parent=None):
        """
        Parameters
        ----------
        configItem: OptionsConfigItem
            configuration item operated by the card

        icon: str | QIcon | FluentIconBase
            the icon to be drawn

        title: str
            the title of card

        content: str
            the content of card

        texts: List[str]
            the text of items

        parent: QWidget
            parent widget
        """
        super().__init__(icon, title, content, parent)
        self.config = config
        self.configItem = configItem
        self.comboBox = ComboBox(self)
        self.hBoxLayout.addWidget(self.comboBox, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.optionToText = {o: t for o, t in zip(configItem.options, texts)}
        for text, option in zip(texts, configItem.options):
            self.comboBox.addItem(text, userData=option)

        self.comboBox.setCurrentText(self.optionToText[self.config.get(configItem)])
        self.comboBox.currentIndexChanged.connect(self._onCurrentIndexChanged)
        configItem.valueChanged.connect(self.setValue)

    def _onCurrentIndexChanged(self, index: int):

        self.config.set(self.configItem, self.comboBox.itemData(index))

    def setValue(self, value):
        if value not in self.optionToText:
            return

        self.comboBox.setCurrentText(self.optionToText[value])
        self.config.set(self.configItem, value)


class PluginBase(ABC):

    @abstractmethod
    def __init__(self, name:str, version:str, author:str, icon:QPixmap, description:str, mainWindow):
        """
        插件基类
        用于给用户提供插件的基础信息, 逻辑信息请写到 load()
        """

        self.name: str = name
        self.version: str = version
        self.author: str = author
        self.icon: QPixmap = icon
        self.description: str = description
        self.mainWindow = mainWindow

    def loadConfig(self):
        """
        初始化配置项, 设置卡片

        QFluentWidgets 仅能实例化一个 qconfig,
        所以必须使用 cfg 来增加设置项才能使用默认的 SettingCard,
        注意使用 group 跟官方设置项进行区分.
        """
        pass

    def unloadConfig(self):
        """
        卸载配置项, 配置卡片
        """
        pass

    def parseUrl(self, url: str, headers:dict) -> tuple[str, str, int]:
        """
        解析链接, 用于代替默认的 getLinkInfo
        返回 URL, FileName, FileSize
        """
        pass

    @abstractmethod
    def load(self):
        """
        插件加载
        self.loadConfig, self.registerUrl 应在这里调用
        """
        pass

    @abstractmethod
    def unload(self):
        """
        插件卸载
        self.unloadConfig, self.unregisterUrl 应在这里调用
        """
        pass

    @abstractmethod
    def uninstall(self):
        """
        插件删除, 应在这里删除配置信息和插件残留的文件
        """
        pass
