from PySide6.QtCore import Signal, Slot, QDir
from PySide6.QtGui import Qt
from PySide6.QtWidgets import QFileDialog
from qfluentwidgets import EditableComboBox, ToolButton, FluentIcon as FIF, SettingCard, ConfigItem

from ..common.config import cfg


def connectList(l1, l2):
    # print('Connect:', l1, l2)
    for i in l1:
        yield i
    for i in l2:
        yield i


class CustomEditableComboBox(EditableComboBox):
    pathChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.defaultText = 'Default'
        self.default = None
        self.memory = []

        self.flashList()

        self.currentTextChanged.connect(self._changed)

    def _changed(self, text):
        if text != self.defaultText:
            self.pathChanged.emit(text)
        else:
            self.pathChanged.emit(self.default)

    def flashList(self):
        cur_text = self.currentText()
        self.clear()

        tracker = set()

        for path in connectList([self.default], self.memory):
            if path != '' and path not in tracker:
                tracker.add(path)  # 防止重复的列表项
                if path is self.default:
                    self.addItem(self.defaultText)
                else:
                    self.addItem(path)

        self.setCurrentText(cur_text)
        self.memory = list(tracker)

    def focusInEvent(self, e):
        self.setMemory(cfg.get(cfg.historyDownloadFolder))  # 保证同步
        self.flashList()

    def setDefault(self, default):
        self.default = default

    def setMemory(self, memory):
        self.memory = memory


class ChooseFolderButton(ToolButton):
    pathChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIcon(FIF.FOLDER)

        self.clicked.connect(self.__chooseFolder)

    def __chooseFolder(self):
        folder = QFileDialog.getExistingDirectory(None, "选择文件夹")
        if not folder:
            return
        self.pathChanged.emit(folder)


class SelectFolderSettingCard(SettingCard):
    changeEvent = Signal(str)  # 路径修改信号

    def __init__(self, default: ConfigItem, memory: ConfigItem, parent=None):
        super().__init__(FIF.DOWNLOAD,
                         "下载路径",
                         cfg.downloadFolder.value,
                         parent)
        self.memoryItem = memory
        self.defaultItem = default
        
        self.editableComboBox = CustomEditableComboBox()
        self.editableComboBox.setDefault(cfg.get(self.defaultItem))
        self.editableComboBox.setMemory(cfg.get(self.memoryItem))

        self.chooseFolderButton = ChooseFolderButton()

        self.editableComboBox.pathChanged.connect(self.__updatePath)
        self.chooseFolderButton.pathChanged.connect(self.__updatePath)

        self.hBoxLayout.addWidget(self.editableComboBox, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(5)
        self.hBoxLayout.addWidget(self.chooseFolderButton, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.editableComboBox.flashList()

    def __append(self, path):
        if path:
            self.editableComboBox.memory.append(path)
            self.editableComboBox.flashList()
            cfg.set(self.memoryItem, self.editableComboBox.memory)

    def __exists(self, path):
        return (path in self.memoryItem.value or
                path == self.editableComboBox.default or path in self.editableComboBox.memory)

    @Slot(str)
    def __updatePath(self, path: str):
        # print("Update:", path)
        if not self.__exists(path):
            self.__append(path)

        self.setContent(path)
        self.editableComboBox.setText(path)
        self.editableComboBox.setCurrentText(path)

        self.changeEvent.emit(path)

    def __del__(self):  # 整理列表,防止重复
        ls = set()
        for item in self.memoryItem.value:
            ls.add(item)
        ls = list(ls)
        cfg.set(self.memoryItem, ls)
