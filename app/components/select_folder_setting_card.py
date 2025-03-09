from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import Qt
from PySide6.QtWidgets import QFileDialog
from qfluentwidgets import EditableComboBox, ToolButton, FluentIcon as FIF, SettingCard, ConfigItem

from ..common.config import cfg


def connectList(l1, l2):
    """连接两个列表的生成器函数，用于合并两个列表的迭代"""
    for i in l1:
        yield i
    for i in l2:
        yield i

class HistoryPathComboBox(EditableComboBox):
    """自定义可编辑组合框，支持默认项和历史记录功能"""
    pathChanged = Signal(str)  # 路径改变信号

    def __init__(self, parent=None, default:str="", memory:list=None):
        super().__init__(parent)
        self.setMinimumWidth(250)

        if memory is None:
            memory = []
        self._currentItems = set()  # 缓存当前显示的路径集合
        self.defaultText = '默认路径'  # 默认项显示文本
        self.default = default        # 默认路径值
        self.memory = memory           # 历史记录列表

        self.flashList()  # 初始化列表显示
        self.currentTextChanged.connect(self._changed)

        self.setCurrentText(default)

    def _changed(self, text):
        """处理选项改变事件"""
        if text != self.defaultText:
            self.pathChanged.emit(text)
        else:
            self.pathChanged.emit(self.default)

    def flashList(self):
        """刷新下拉列表，合并默认项和历史记录"""
        newPaths = set()
        newPaths.add(self.defaultText)
        for path in connectList([self.default], self.memory):
            if path:  # 忽略空路径
                newPaths.add(path)

        # 计算需要添加/移除的项
        toRemove = self._currentItems - newPaths
        toAdd = newPaths - self._currentItems

        if not (toRemove or toAdd):
            return  # 无变化时直接返回

        # 执行增删操作
        for path in toRemove:
            self.removeItem(self.findText(path))
        for path in toAdd:
            self.addItem(path)

        self._currentItems = newPaths.copy()  # 更新缓存

    def focusInEvent(self, e):
        """获取焦点时同步配置并刷新列表"""
        _ = cfg.historyDownloadFolder.value
        if not _ == self.memory:
            self.setMemory(_)
            self.flashList()
        super().focusInEvent(e)

    def setDefault(self, default):
        """设置默认路径"""
        self.default = default

    def setMemory(self, memory):
        """设置历史记录"""
        self.memory = memory

class SelectFolderSettingCard(SettingCard):
    """下载路径设置卡片组件"""
    pathChanged = Signal(str)  # 路径修改信号

    def __init__(self, defaultItem: ConfigItem, memoryItem: ConfigItem, parent=None):
        super().__init__(FIF.DOWNLOAD, "下载路径", cfg.downloadFolder.value, parent)
        self.memoryItem = memoryItem  # 历史记录配置项
        self.defaultItem = defaultItem  # 默认路径配置项

        # 初始化组合框
        self.editableComboBox = HistoryPathComboBox(self, self.defaultItem.value, self.memoryItem.value)

        # 初始化选择按钮
        self.chooseFolderButton = ToolButton(FIF.FOLDER, self)

        # 连接信号
        self.editableComboBox.pathChanged.connect(self.__updatePath)
        self.chooseFolderButton.clicked.connect(self.__chooseFolder)

        # 布局设置
        self.hBoxLayout.addWidget(self.editableComboBox, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(5)
        self.hBoxLayout.addWidget(self.chooseFolderButton, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.editableComboBox.flashList()

    def __chooseFolder(self):
        """打开文件夹选择对话框"""
        folder = QFileDialog.getExistingDirectory(None, "选择文件夹")
        if folder:
            self.__updatePath(folder)

    def __append(self, path):
        """添加新路径到历史记录"""
        if path:
            self.editableComboBox.memory.append(path)
            if len(self.editableComboBox.memory) > 7:
                self.editableComboBox.memory.pop(0)
            self.editableComboBox.flashList()
            cfg.set(self.memoryItem, self.editableComboBox.memory)

    def __isPathExists(self, path):
        """检查路径是否已存在"""
        return (path in self.memoryItem.value or
                path == self.editableComboBox.default or
                path in self.editableComboBox.memory)

    @Slot(str)
    def __updatePath(self, path: str):
        """更新当前路径"""
        if not self.__isPathExists(path):
            self.__append(path)

        self.setContent(path)  # 更新卡片显示

        self.editableComboBox.setCurrentText(path)

        self.pathChanged.emit(path)  # 发出修改信号

    def __del__(self):
        """析构时清理重复历史记录并保存"""
        uniquePaths = set(self.memoryItem.value)
        cfg.set(self.memoryItem, list(uniquePaths))
