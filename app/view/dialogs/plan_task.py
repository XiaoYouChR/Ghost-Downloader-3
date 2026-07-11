from PySide6.QtWidgets import QButtonGroup, QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel, FluentIcon, LineEdit, MessageBoxBase,
    RadioButton, SubtitleLabel, ToolButton, ToolTipFilter,
)


from app.services.plan import PlanAction


class PlanTaskDialog(MessageBoxBase):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(self.tr("设置计划任务"), self)
        self.contentLabel = BodyLabel(self.tr("所有任务完成后执行以下操作："), self)
        self.radioGroup = QButtonGroup(self)
        self.shutdownButton = RadioButton(self.tr("关机"), self)
        self.restartButton = RadioButton(self.tr("重启"), self)
        self.sleepButton = RadioButton(self.tr("睡眠"), self)
        self.openFileButton = RadioButton(self.tr("打开文件"), self)
        self.pathContainer = QWidget(self)
        self.pathLayout = QHBoxLayout(self.pathContainer)
        self.pathEdit = LineEdit(self.pathContainer)
        self.browseButton = ToolButton(FluentIcon.FOLDER, self.pathContainer)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.widget.setMinimumWidth(420)
        self.yesButton.setText(self.tr("确认"))
        self.cancelButton.setText(self.tr("取消"))

        self.radioGroup.addButton(self.shutdownButton)
        self.radioGroup.addButton(self.restartButton)
        self.radioGroup.addButton(self.sleepButton)
        self.radioGroup.addButton(self.openFileButton)
        self.radioGroup.setExclusive(True)
        self.shutdownButton.setChecked(True)

        self.pathEdit.setPlaceholderText(self.tr("请选择要打开的文件"))
        self.pathEdit.setClearButtonEnabled(True)
        self.browseButton.setToolTip(self.tr("选择文件"))
        self.browseButton.installEventFilter(ToolTipFilter(self.browseButton))

        self.pathLayout.setContentsMargins(0, 0, 0, 0)
        self.pathLayout.setSpacing(8)
        self.pathLayout.addWidget(self.pathEdit, 1)
        self.pathLayout.addWidget(self.browseButton)
        self.pathContainer.setVisible(False)

    def _initLayout(self) -> None:
        optionsLayout = QVBoxLayout()
        optionsLayout.setContentsMargins(0, 0, 0, 0)
        optionsLayout.setSpacing(10)
        optionsLayout.addWidget(self.shutdownButton)
        optionsLayout.addWidget(self.restartButton)
        optionsLayout.addWidget(self.sleepButton)
        optionsLayout.addWidget(self.openFileButton)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(2)
        self.viewLayout.addWidget(self.contentLabel)
        self.viewLayout.addSpacing(4)
        self.viewLayout.addLayout(optionsLayout)
        self.viewLayout.addSpacing(2)
        self.viewLayout.addWidget(self.pathContainer)

    def _bind(self) -> None:
        self.openFileButton.toggled.connect(self._onActionChanged)
        self.browseButton.clicked.connect(self._onBrowseClicked)

    def _onActionChanged(self) -> None:
        self.pathContainer.setVisible(self.openFileButton.isChecked())

    def _onBrowseClicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self.tr("选择文件"))
        if path:
            self.pathEdit.setText(path)

    def selectedAction(self) -> int:
        if self.radioGroup.checkedButton() is self.restartButton:
            return PlanAction.RESTART
        if self.radioGroup.checkedButton() is self.sleepButton:
            return PlanAction.SLEEP
        if self.radioGroup.checkedButton() is self.openFileButton:
            return PlanAction.OPEN_FILE
        return PlanAction.SHUTDOWN

    def selectedFilePath(self) -> str:
        return self.pathEdit.text().strip()

    def validate(self) -> bool:
        if self.selectedAction() == PlanAction.OPEN_FILE and not self.selectedFilePath():
            return False
        return True
