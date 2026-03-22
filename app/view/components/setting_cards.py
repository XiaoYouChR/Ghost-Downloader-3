from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QButtonGroup,
    QHBoxLayout,
    QSpacerItem,
    QSizePolicy,
    QFileDialog,
)
from qfluentwidgets import (
    SettingCard,
    RangeConfigItem,
    SpinBox,
    ExpandGroupSettingCard,
    ConfigItem,
    FluentIcon,
    BodyLabel,
    RadioButton,
    ComboBox,
    LineEdit,
    EditableComboBox,
    ToolButton,
)
from urllib.parse import urlsplit

from app.supports.config import cfg
from app.supports.utils import getSystemProxies


class SpinBoxSettingCard(SettingCard):
    """支持自定义倍数的 SpinBox 设置卡片"""

    def __init__(
        self,
        icon,
        title,
        content=None,
        suffix: str = None,
        configItem: RangeConfigItem = None,
        parent=None,
        singleStep: int = 50,
        division: float = 1,
    ):
        super().__init__(icon, title, content, parent)
        self.division = division
        self.configItem = configItem

        self.spinBox = SpinBox(self)
        self.spinBox.setObjectName("spinBox")
        self.spinBox.setSingleStep(singleStep)
        self.spinBox.setMinimumWidth(180)
        self.spinBox.setSuffix(suffix)

        if configItem:
            _ = configItem.range
            self.spinBox.setRange(_[0] * division, _[1] * division)

        self.hBoxLayout.addWidget(self.spinBox)
        self.hBoxLayout.addSpacing(24)

        self.spinBox.setValue(self.configItem.value * division)

    def leaveEvent(self, event):
        if self.configItem:
            cfg.set(self.configItem, self.spinBox.value() / self.division)


class ProxySettingCard(ExpandGroupSettingCard):
    """Custom proxyServer setting card"""

    def __init__(self, configItem: ConfigItem, parent=None):
        """
        Parameters
        ----------
        configItem: ColorConfigItem
            options config item

        parent: QWidget
            parent window
        """
        super().__init__(
            FluentIcon.GLOBE,
            self.tr("代理"),
            self.tr("设置下载时希望使用的代理"),
            parent=parent,
        )

        self.configItem = configItem

        self.choiceLabel = BodyLabel(self)
        self.radioWidget = QWidget(self.view)
        self.radioLayout = QVBoxLayout(self.radioWidget)

        self.buttonGroup = QButtonGroup(self)
        self.offRadioButton = RadioButton(self.tr("不使用代理"), self.radioWidget)
        self.defaultRadioButton = RadioButton(
            self.tr("自动检测系统代理"), self.radioWidget
        )
        self.customRadioButton = RadioButton(
            self.tr("使用自定义代理"), self.radioWidget
        )

        self.customProxyWidget = QWidget(self.view)
        self.customProxyLayout = QHBoxLayout(self.customProxyWidget)
        self.customLabel = BodyLabel(
            self.tr("编辑代理服务器: "), self.customProxyWidget
        )
        self.customProtocolComboBox = ComboBox(self.customProxyWidget)
        self.customProtocolComboBox.addItems(["socks4", "socks5", "http", "https"])
        self.label_1 = BodyLabel("://", self.customProxyWidget)
        self.customIPLineEdit = LineEdit(self.customProxyWidget)
        self.customIPLineEdit.setPlaceholderText(self.tr("代理 IP 地址"))
        self.label_2 = BodyLabel(":", self.customProxyWidget)
        self.customPortLineEdit = LineEdit(self.customProxyWidget)
        self.customPortLineEdit.setPlaceholderText(self.tr("端口"))

        # 代理账号和密码
        self.credentialsWidget = QWidget(self.view)
        self.credentialsLayout = QHBoxLayout(self.credentialsWidget)
        self.credentialsLabel = BodyLabel(self.tr("认证信息: "), self.credentialsWidget)
        self.usernameLineEdit = LineEdit(self.credentialsWidget)
        self.usernameLineEdit.setPlaceholderText(self.tr("用户名（可选）"))
        self.label_3 = BodyLabel(" : ", self.credentialsWidget)
        self.passwordLineEdit = LineEdit(self.credentialsWidget)
        self.passwordLineEdit.setPlaceholderText(self.tr("密码（可选）"))
        self.passwordLineEdit.setEchoMode(LineEdit.EchoMode.Password)

        self.__initWidget()
        configValue = self.configItem.value

        if configValue == "Auto":
            self.defaultRadioButton.setChecked(True)
            self.__onRadioButtonClicked(self.defaultRadioButton)
        elif configValue == "Off":
            self.offRadioButton.setChecked(True)
            self.__onRadioButtonClicked(self.offRadioButton)
        else:
            self.customRadioButton.setChecked(True)
            self.__onRadioButtonClicked(self.customRadioButton)
            self._applyProxyUrl(configValue)

            self.choiceLabel.setText(self.buttonGroup.checkedButton().text())
            self.choiceLabel.adjustSize()

    def _applyProxyUrl(self, proxyUrl: str | None):
        if not proxyUrl:
            self.customProtocolComboBox.setCurrentText("")
            self.customIPLineEdit.setText(self.tr("未检测到代理"))
            self.customPortLineEdit.setText("")
            self.usernameLineEdit.setText("")
            self.passwordLineEdit.setText("")
            return

        parsed = urlsplit(proxyUrl)
        self.customProtocolComboBox.setCurrentText(parsed.scheme)
        self.customIPLineEdit.setText(parsed.hostname or "")
        self.customPortLineEdit.setText(str(parsed.port or ""))
        self.usernameLineEdit.setText(parsed.username or "")
        self.passwordLineEdit.setText(parsed.password or "")

    def __initWidget(self):
        self.__initLayout()
        self.buttonGroup.buttonClicked.connect(self.__onRadioButtonClicked)

    def __initLayout(self):
        self.addWidget(self.choiceLabel)

        self.radioLayout.setSpacing(19)
        self.radioLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.radioLayout.setContentsMargins(48, 18, 0, 18)

        self.buttonGroup.addButton(self.offRadioButton)
        self.buttonGroup.addButton(self.defaultRadioButton)
        self.buttonGroup.addButton(self.customRadioButton)

        self.radioLayout.addWidget(self.offRadioButton)
        self.radioLayout.addWidget(self.defaultRadioButton)
        self.radioLayout.addWidget(self.customRadioButton)
        self.radioLayout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)

        self.customProxyLayout.setContentsMargins(48, 18, 44, 18)
        self.customProxyLayout.addWidget(
            self.customLabel, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.customProxyLayout.addSpacerItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        )
        self.customProxyLayout.addWidget(
            self.customProtocolComboBox, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.customProxyLayout.addWidget(self.label_1, 0, Qt.AlignmentFlag.AlignLeft)
        self.customProxyLayout.addWidget(
            self.customIPLineEdit, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.customProxyLayout.addWidget(self.label_2, 0, Qt.AlignmentFlag.AlignLeft)
        self.customProxyLayout.addWidget(
            self.customPortLineEdit, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.customProxyLayout.setSizeConstraint(
            QHBoxLayout.SizeConstraint.SetMinimumSize
        )

        self.credentialsLayout.setContentsMargins(48, 18, 44, 18)
        self.credentialsLayout.addWidget(
            self.credentialsLabel, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.credentialsLayout.addSpacerItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        )
        self.credentialsLayout.addWidget(
            self.usernameLineEdit, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.credentialsLayout.addWidget(self.label_3, 0, Qt.AlignmentFlag.AlignLeft)
        self.credentialsLayout.addWidget(
            self.passwordLineEdit, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.credentialsLayout.setSizeConstraint(
            QHBoxLayout.SizeConstraint.SetMinimumSize
        )

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.radioWidget)
        self.addGroupWidget(self.customProxyWidget)
        self.addGroupWidget(self.credentialsWidget)

    def __onRadioButtonClicked(self, button: RadioButton):
        """radio button clicked slot"""
        if button.text() == self.choiceLabel.text():
            return

        self.choiceLabel.setText(button.text())
        self.choiceLabel.adjustSize()

        if button is self.defaultRadioButton:  # 自动
            # 禁用 Custom 编辑器
            self.customProxyWidget.setDisabled(True)
            self.credentialsWidget.setDisabled(True)

            systemProxies = getSystemProxies()
            systemValue = None
            if systemProxies:
                for protocol in ("https", "http", "ftp"):
                    systemValue = systemProxies.get(protocol)
                    if systemValue:
                        break
            self._applyProxyUrl(systemValue)

            cfg.set(self.configItem, "Auto")

        elif button is self.offRadioButton:  # 关闭
            # 禁用 Custom 编辑器
            self.customProxyWidget.setDisabled(True)
            self.credentialsWidget.setDisabled(True)

            cfg.set(self.configItem, "Off")

        elif button is self.customRadioButton:
            # 启用 Custom 编辑器
            self.customProxyWidget.setDisabled(False)
            self.credentialsWidget.setDisabled(False)

    def leaveEvent(self, event):  # 鼠标离开时检测 Custom 选项是否合法并保存配置
        if self.customRadioButton.isChecked():
            protocol = self.customProtocolComboBox.currentText()
            ip = self.customIPLineEdit.text()
            port = self.customPortLineEdit.text()
            username = self.usernameLineEdit.text()
            password = self.passwordLineEdit.text()

            # 构建代理字符串：protocol://[username:password@]ip:port
            if username or password:
                credentials = f"{username}:{password}@"
            else:
                credentials = ""

            proxyServer = f"{protocol}://{credentials}{ip}:{port}"
            if cfg.proxyServer.validator.validate(proxyServer):
                cfg.set(self.configItem, proxyServer)
            else:
                self.defaultRadioButton.click()
                self.defaultRadioButton.setChecked(True)


class SelectFolderSettingCard(SettingCard):
    """下载路径设置卡片组件，集成历史路径管理"""

    pathChanged = Signal(str)  # 路径修改信号

    def __init__(self, defaultPath: str, memoryConfigItem: ConfigItem, parent=None):
        super().__init__(
            FluentIcon.DOWNLOAD, self.tr("下载路径"), cfg.downloadFolder.value, parent
        )
        self.memoryItem: ConfigItem = memoryConfigItem  # 历史记录配置项
        self.defaultPath = defaultPath

        # 历史路径管理
        self.memoryPaths = self.memoryItem.value  # 历史记录列表
        self._comboBoxItems = set()  # 缓存组合框当前显示的路径集合

        # UI组件
        self.editableComboBox = EditableComboBox(self)
        # self.editableComboBox.setMinimumWidth(250)
        # TODO editableComboBox 若 Editable, 会导致重大 Bug, 通过 SizeHint 优化 editableComboBox
        self.editableComboBox.setReadOnly(True)
        self.chooseFolderButton = ToolButton(FluentIcon.FOLDER, self)
        self.restoreDefaultButton = ToolButton(
            FluentIcon.CANCEL, self
        )  # 恢复默认路径按钮

        # 初始化组合框
        self._refreshComboBoxItems()
        self.editableComboBox.currentTextChanged.connect(self._onComboBoxTextChanged)

        # 连接信号
        self.chooseFolderButton.clicked.connect(self._chooseFolder)
        self.restoreDefaultButton.clicked.connect(self._restoreDefault)

        # 设置按钮提示
        self.chooseFolderButton.setToolTip(self.tr("浏览文件夹"))
        self.restoreDefaultButton.setToolTip(self.tr("恢复默认路径"))

        # 布局设置
        self.hBoxLayout.addWidget(self.editableComboBox, 2)
        self.hBoxLayout.addSpacing(5)
        self.hBoxLayout.addWidget(
            self.chooseFolderButton
        )
        self.hBoxLayout.addSpacing(5)
        self.hBoxLayout.addWidget(
            self.restoreDefaultButton
        )
        self.hBoxLayout.addSpacing(16)

    def _onComboBoxTextChanged(self, text):
        """处理组合框文本改变事件"""
        self._updatePath(text)

    def _refreshComboBoxItems(self):
        """刷新组合框中的路径列表"""
        newPaths = set()
        for path in [self.defaultPath] + self.memoryPaths:
            if path:  # 忽略空路径
                newPaths.add(path)

        # 计算需要添加/移除的项
        toRemoveItems = self._comboBoxItems - newPaths
        toAddItems = newPaths - self._comboBoxItems

        if not (toRemoveItems or toAddItems):
            return

        # 执行增删操作
        for path in toRemoveItems:
            idx = self.editableComboBox.findText(path)
            if idx >= 0:
                self.editableComboBox.removeItem(idx)
        for path in toAddItems:
            self.editableComboBox.addItem(path)

        self._comboBoxItems = newPaths

    def _syncMemoryPathsFromConfig(self):
        """从配置文件同步历史路径"""
        currentValue = self.memoryItem.value
        if currentValue != self.memoryPaths:
            self.memoryPaths = currentValue
            self._refreshComboBoxItems()

    def _chooseFolder(self):
        """打开文件夹选择对话框"""
        folder = QFileDialog.getExistingDirectory(None, self.tr("选择文件夹"))
        if folder:
            self._updatePath(folder)

    def _append(self, path: str):
        """添加新路径到历史记录"""
        self.memoryPaths.append(path)
        # 限制历史记录数量不超过7条
        if len(self.memoryPaths) > 7:
            self.memoryPaths.pop(0)
        # 更新UI并保存配置
        self._refreshComboBoxItems()
        cfg.set(self.memoryItem, self.memoryPaths)

    def _isPathExists(self, path) -> bool:
        """检查路径是否已存在"""
        return path in self.memoryPaths

    def _restoreDefault(self):
        """恢复默认路径"""
        self._updatePath(self.defaultPath)

    @Slot(str)
    def _updatePath(self, path: str):
        """更新当前路径"""
        if path and not self._isPathExists(path):
            self._append(path)

        self.setContent(path)  # 更新卡片显示
        self.editableComboBox.blockSignals(True)  # 阻止信号以避免递归
        self.editableComboBox.setCurrentText(path)
        self.editableComboBox.blockSignals(False)
        self.pathChanged.emit(path)  # 发出修改信号

    def focusInEvent(self, e):
        """获取焦点时同步配置并刷新列表"""
        self._syncMemoryPathsFromConfig()
        return super().focusInEvent(e)

    def __del__(self):
        """析构时清理重复历史记录并保存"""
        uniquePaths = list(dict.fromkeys(self.memoryItem.value))
        cfg.set(self.memoryItem, uniquePaths)
