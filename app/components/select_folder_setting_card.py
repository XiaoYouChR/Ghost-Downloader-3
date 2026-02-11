import os.path

from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import Qt
from PySide6.QtWidgets import QFileDialog
from qfluentwidgets import EditableComboBox, ToolButton, FluentIcon as FIF, SettingCard, ConfigItem, InfoBar

from ..common.config import cfg


class HistoryPathComboBox(EditableComboBox):
    """自定义可编辑组合框，支持默认项和历史记录功能"""
    pathChanged = Signal(str)  # 路径改变信号

    def __init__(self, parent=None, current: str = "", memory: list = None):
        super().__init__(parent)
        self.setMinimumWidth(250)

        if memory is None:
            memory = []
        self._currentItems = set()  # 缓存当前显示的路径集合
        self.currentPath = current  # 默认路径值
        self.memory = memory  # 历史记录列表

        self.flashList()  # 初始化列表显示
        self.editingFinished.connect(self.__pathChanged)  # 绑定编辑结束事件
        self.currentIndexChanged.connect(self.__pathChanged)

        self.setCurrentText(current)

    def __pathChanged(self):
        """处理选项改变事件"""
        text = self.text()
        if not text:  # 清空之后确定不算改变
            self.setText(self.currentPath)
            return

        self.pathChanged.emit(text)  # 发送

    def flashList(self):
        """刷新下拉列表，合并默认项和历史记录"""
        self.items.clear()
        self.addItems([item for item in self.memory if item])

    def focusInEvent(self, e):
        """获取焦点时同步配置并刷新列表"""
        _ = cfg.historyDownloadFolder.value
        if _ != self.memory:
            self.memory = _
            self.flashList()
        super().focusInEvent(e)


class SelectFolderSettingCard(SettingCard):
    """下载路径设置卡片组件"""
    pathChanged = Signal(str)  # 路径修改信号

    def __init__(self, defaultItem: ConfigItem, memoryItem: ConfigItem, parent=None):
        super().__init__(FIF.DOWNLOAD, self.tr("下载路径"), cfg.downloadFolder.value, parent)
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
        self.setContent(defaultItem.value)

    def __chooseFolder(self):
        """打开文件夹选择对话框"""
        folder = QFileDialog.getExistingDirectory(None, self.tr("选择文件夹"))
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
                path == self.editableComboBox.currentPath or
                path in self.editableComboBox.memory)

    @Slot(str)
    def __updatePath(self, path: str):
        """更新当前路径"""
        if not os.path.isabs(path):
            InfoBar.error(self.tr('路径不正确'), path, parent=self)
            return

        if not self.__isPathExists(path):
            self.__append(path)

        self.setContent(path)  # 更新卡片显示
        self.pathChanged.emit(path)  # 发出修改信号

    def __del__(self):
        """析构时清理重复历史记录并保存"""
        uniquePaths = set(self.memoryItem.value)
        cfg.set(self.memoryItem, list(uniquePaths))
