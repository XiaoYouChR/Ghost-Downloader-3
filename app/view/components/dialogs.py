from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    MessageBoxBase, SubtitleLabel, BodyLabel, CheckBox, RadioButton, LineEdit, ToolButton, FluentIcon, ToolTipFilter
)


class DeleteTaskDialog(MessageBoxBase):

    def __init__(self, parent=None, showCheckBox=True, deleteOnClose=True):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(self.tr("删除任务"), self)
        self.contentLabel = BodyLabel(
            self.tr("确定要删除此任务吗？"), self)
        self.deleteFileCheckBox = CheckBox(self.tr("删除文件"), self)

        self.deleteFileCheckBox.setVisible(showCheckBox)

        if deleteOnClose:
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self.initWidget()

    def initWidget(self):
        self.deleteFileCheckBox.setChecked(True)
        self.widget.setMinimumWidth(330)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(12)
        self.viewLayout.addWidget(self.contentLabel)
        self.viewLayout.addSpacing(10)
        self.viewLayout.addWidget(self.deleteFileCheckBox)


class PlanTaskDialog(MessageBoxBase):

    SHUTDOWN = 0
    RESTART = 1
    OPEN_FILE = 2

    def __init__(self, parent=None, deleteOnClose=True):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(self.tr("设置计划任务"), self)
        self.contentLabel = BodyLabel(self.tr("所有任务完成后执行以下操作："), self)
        self.radioButtonGroup = QButtonGroup(self)
        self.powerOffButton = RadioButton(self.tr("关机"), self)
        self.restartButton = RadioButton(self.tr("重启"), self)
        self.openFileButton = RadioButton(self.tr("打开文件"), self)
        self.pathContainer = QWidget(self)
        self.pathLayout = QHBoxLayout(self.pathContainer)
        self.lineEdit = LineEdit(self.pathContainer)
        self.selectFolderButton = ToolButton(FluentIcon.FOLDER, self.pathContainer)

        if deleteOnClose:
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self.initWidget()
        self.initLayout()
        self.connectSignalToSlot()

    def initWidget(self):
        self.widget.setMinimumWidth(420)
        self.yesButton.setText(self.tr("确认"))
        self.cancelButton.setText(self.tr("取消"))

        self.radioButtonGroup.addButton(self.powerOffButton)
        self.radioButtonGroup.addButton(self.restartButton)
        self.radioButtonGroup.addButton(self.openFileButton)
        self.radioButtonGroup.setExclusive(True)
        self.powerOffButton.setChecked(True)

        self.lineEdit.setPlaceholderText(self.tr("请选择要打开的文件"))
        self.lineEdit.setClearButtonEnabled(True)
        self.selectFolderButton.setToolTip(self.tr("选择文件"))
        self.selectFolderButton.installEventFilter(ToolTipFilter(self.selectFolderButton))

        self.pathLayout.setContentsMargins(0, 0, 0, 0)
        self.pathLayout.setSpacing(8)
        self.pathLayout.addWidget(self.lineEdit, 1)
        self.pathLayout.addWidget(self.selectFolderButton)

        self._syncPathWidgets()

    def initLayout(self):
        optionsLayout = QVBoxLayout()
        optionsLayout.setContentsMargins(0, 0, 0, 0)
        optionsLayout.setSpacing(10)
        optionsLayout.addWidget(self.powerOffButton)
        optionsLayout.addWidget(self.restartButton)
        optionsLayout.addWidget(self.openFileButton)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(2)
        self.viewLayout.addWidget(self.contentLabel)
        self.viewLayout.addSpacing(4)
        self.viewLayout.addLayout(optionsLayout)
        self.viewLayout.addSpacing(2)
        self.viewLayout.addWidget(self.pathContainer)

    def connectSignalToSlot(self):
        self.openFileButton.toggled.connect(self._syncPathWidgets)
        self.selectFolderButton.clicked.connect(self._chooseFile)

    def _syncPathWidgets(self):
        enabled = self.openFileButton.isChecked()
        self.pathContainer.setVisible(enabled)
        if enabled and not self.lineEdit.text().strip():
            self.lineEdit.setFocus()

    def _chooseFile(self):
        filePath, _ = QFileDialog.getOpenFileName(self, self.tr("选择文件"))
        if filePath:
            self.lineEdit.setText(filePath)

    def selectedAction(self) -> int:
        checkedButton = self.radioButtonGroup.checkedButton()
        if checkedButton is self.restartButton:
            return self.RESTART
        if checkedButton is self.openFileButton:
            return self.OPEN_FILE
        return self.SHUTDOWN

    def selectedFilePath(self) -> str:
        return self.lineEdit.text().strip()

    def validate(self) -> bool:
        if self.selectedAction() == self.OPEN_FILE and not self.selectedFilePath():
            return False

        return True
