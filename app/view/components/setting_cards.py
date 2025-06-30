from typing import Union
from urllib.parse import urlparse

from PySide6.QtGui import Qt, QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QButtonGroup, QHBoxLayout, QSpacerItem, QSizePolicy
from qfluentwidgets import ExpandGroupSettingCard, ConfigItem, FluentIcon as FI, BodyLabel, RadioButton, ComboBox, \
    LineEdit, SettingCard, FluentIconBase, RangeConfigItem, SpinBox

from app.supports.config import cfg
from app.supports.utils import getSystemProxy


class ProxySettingCard(ExpandGroupSettingCard):
    """ Custom proxyServer setting card """

    def __init__(self, configItem: ConfigItem, parent=None):
        """
        Parameters
        ----------
        configItem: ColorConfigItem
            options config item

        parent: QWidget
            parent window
        """
        super().__init__(FI.GLOBE, self.tr("代理"), self.tr("设置下载时希望使用的代理"), parent=parent)
        self.configItem = configItem

        self.__setupUi()

        self.buttonGroup.buttonClicked.connect(self.__onRadioButtonClicked)

        if self.configItem.value == "Auto":
            self.defaultRadioButton.setChecked(True)
            self.__onRadioButtonClicked(self.defaultRadioButton)
        elif self.configItem.value == "Off":
            self.offRadioButton.setChecked(True)
            self.__onRadioButtonClicked(self.offRadioButton)
        else:
            self.customRadioButton.setChecked(True)
            self.__onRadioButtonClicked(self.customRadioButton)
            self.customProtocolComboBox.setCurrentText(self.configItem.value[:self.configItem.value.find("://")])
            _ = self.configItem.value[self.configItem.value.find("://")+3:].split(":")
            self.customIPLineEdit.setText(_[0])
            self.customPortLineEdit.setText(_[1])

            self.choiceLabel.setText(self.buttonGroup.checkedButton().text())
            self.choiceLabel.adjustSize()

    def __setupUi(self):
        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)

        self.choiceLabel = BodyLabel(self)
        self.addWidget(self.choiceLabel)

        self.radioButtonGroupWidget = QWidget(self.view)
        self.radioButtonLayout = QVBoxLayout(self.radioButtonGroupWidget)

        self.offRadioButton = RadioButton(
            self.tr("不使用代理"), self.radioButtonGroupWidget)
        self.defaultRadioButton = RadioButton(
            self.tr("自动检测系统代理"), self.radioButtonGroupWidget)
        self.customRadioButton = RadioButton(
            self.tr("使用自定义代理"), self.radioButtonGroupWidget)

        self.radioButtonLayout.setSpacing(19)
        self.radioButtonLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.radioButtonLayout.setContentsMargins(48, 18, 0, 18)
        self.radioButtonLayout.addWidget(self.offRadioButton)
        self.radioButtonLayout.addWidget(self.defaultRadioButton)
        self.radioButtonLayout.addWidget(self.customRadioButton)
        self.radioButtonLayout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)

        self.buttonGroup = QButtonGroup(self)
        self.buttonGroup.addButton(self.offRadioButton)
        self.buttonGroup.addButton(self.defaultRadioButton)
        self.buttonGroup.addButton(self.customRadioButton)

        self.proxyGroupWidget = QWidget(self.view)
        self.verticalLayout = QVBoxLayout(self.proxyGroupWidget)
        self.verticalLayout.setContentsMargins(48, 18, 44, 18)
        self.proxyGroupWidget.setLayout(self.verticalLayout)

        self.customProxyLayout = QHBoxLayout(self.proxyGroupWidget)
        self.label_1 = BodyLabel(
            self.tr("编辑代理服务器: "), self.proxyGroupWidget)
        self.customProtocolComboBox = ComboBox(self.proxyGroupWidget)
        self.customProtocolComboBox.addItems(["socks5", "http", "https"])
        self.label_2 = BodyLabel("://", self.proxyGroupWidget)
        self.customIPLineEdit = LineEdit(self.proxyGroupWidget)
        self.customIPLineEdit.setPlaceholderText(self.tr("代理 IP 地址"))
        self.label_3 = BodyLabel(":", self.proxyGroupWidget)
        self.customPortLineEdit = LineEdit(self.proxyGroupWidget)
        self.customPortLineEdit.setPlaceholderText(self.tr("端口"))

        self.customProxyLayout.addWidget(self.label_1, 0, Qt.AlignmentFlag.AlignLeft)
        self.customProxyLayout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        self.customProxyLayout.addWidget(self.customProtocolComboBox, 0, Qt.AlignmentFlag.AlignLeft)
        self.customProxyLayout.addWidget(self.label_2, 0, Qt.AlignmentFlag.AlignLeft)
        self.customProxyLayout.addWidget(self.customIPLineEdit, 0, Qt.AlignmentFlag.AlignLeft)
        self.customProxyLayout.addWidget(self.label_3, 0, Qt.AlignmentFlag.AlignLeft)
        self.customProxyLayout.addWidget(self.customPortLineEdit, 0, Qt.AlignmentFlag.AlignLeft)
        self.customProxyLayout.setSizeConstraint(QHBoxLayout.SizeConstraint.SetMinimumSize)

        self.customAuthLayout = QHBoxLayout(self.proxyGroupWidget)
        self.label_4 = BodyLabel(self.tr("编辑代理认证:"), self.proxyGroupWidget)
        self.label_5 = BodyLabel(self.tr("账户"), self.proxyGroupWidget)
        self.customUsernameLineEdit = LineEdit(self.proxyGroupWidget)
        self.customUsernameLineEdit.setPlaceholderText(self.tr("在这里输入代理账户"))
        self.label_6 = BodyLabel(self.tr("密码"), self.proxyGroupWidget)
        self.customPasswordLineEdit = LineEdit(self.proxyGroupWidget)
        self.customPasswordLineEdit.setPlaceholderText(self.tr("在这里输入代理密码"))

        self.customAuthLayout.addWidget(self.label_4, 0, Qt.AlignmentFlag.AlignLeft)
        self.customAuthLayout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed))
        self.customAuthLayout.addWidget(self.label_5, 0, Qt.AlignmentFlag.AlignLeft)
        self.customAuthLayout.addWidget(self.customUsernameLineEdit, 0, Qt.AlignmentFlag.AlignLeft)
        self.customAuthLayout.addWidget(self.label_6, 0, Qt.AlignmentFlag.AlignLeft)
        self.customAuthLayout.addWidget(self.customPasswordLineEdit, 0, Qt.AlignmentFlag.AlignLeft)
        self.customAuthLayout.setSizeConstraint(QHBoxLayout.SizeConstraint.SetMinimumSize)

        self.verticalLayout.addLayout(self.customProxyLayout)
        self.verticalLayout.addLayout(self.customAuthLayout)

        self.addGroupWidget(self.radioButtonGroupWidget)
        self.addGroupWidget(self.proxyGroupWidget)

    def __onRadioButtonClicked(self, button: RadioButton):
        """ radio button clicked slot """

        if button.text() == self.choiceLabel.text():
            return

        self.choiceLabel.setText(button.text())
        self.choiceLabel.adjustSize()

        if button is self.defaultRadioButton:  # 自动
            self.proxyGroupWidget.setDisabled(True)

            _ = getSystemProxy()
            # SystemProxy 可能为 None, "" 或者类似于 "socks5://user:pass@proxy.example.com:65535" 的格式
            # 若不为空则自动填充选项, 其中 user 和 pass 可能不存在
            if _:
                parsedUrl = urlparse(_)
                self.customProtocolComboBox.setCurrentText(parsedUrl.scheme)
                self.customIPLineEdit.setText(parsedUrl.hostname)
                self.customPortLineEdit.setText(parsedUrl.port)
                self.customUsernameLineEdit.setText(parsedUrl.username)
                self.customPasswordLineEdit.setText(parsedUrl.password)
            else:
                self.customProtocolComboBox.setCurrentText("")
                self.customIPLineEdit.setText(self.tr("未检测到代理"))
                self.customPortLineEdit.setText("")
                self.customUsernameLineEdit.setText("")
                self.customPasswordLineEdit.setText("")

            cfg.set(self.configItem, "Auto")

        elif button is self.offRadioButton:  # 关闭
            self.proxyGroupWidget.setDisabled(True)

            cfg.set(self.configItem, "Off")

        elif button is self.customRadioButton:
            self.proxyGroupWidget.setDisabled(False)

    def leaveEvent(self, event):
        """鼠标离开时检测 custom 选项是否合法并保存配置"""
        if self.customRadioButton.isChecked():
            protocol = self.customProtocolComboBox.currentText()
            host = self.customIPLineEdit.text().strip()
            port = self.customPortLineEdit.text().strip()
            user = self.customUsernameLineEdit.text().strip()
            password = self.customPasswordLineEdit.text().strip()

            if not all([protocol, host, port]):
                proxyServer = ""
            else:
                authPart = ""
                if user:
                    authPart = user
                    if password:
                        authPart += f":{password}"
                    authPart += "@"

                proxyServer = f"{protocol}://{authPart}{host}:{port}"

            if cfg.proxyServer.validator.validate(proxyServer):
                cfg.set(self.configItem, proxyServer)
            else:
                self.defaultRadioButton.click()
                self.defaultRadioButton.setChecked(True)


class SpinBoxSettingCard(SettingCard):
    """ Split Box Setting Card """

    def __init__(self, icon: Union[str, QIcon, FluentIconBase], title, content=None, suffix:str=None, configItem: RangeConfigItem = None, parent=None, singleStep:int=50, multiple:int=1):
        super().__init__(icon, title, content, parent)
        self.multiple = multiple
        self.configItem = configItem

        self.spinBox = SpinBox(self)
        self.spinBox.setObjectName('spinBox')
        self.spinBox.setSingleStep(singleStep)
        self.spinBox.setMinimumWidth(180)
        self.spinBox.setSuffix(suffix)

        if configItem:
            _ = configItem.range
            self.spinBox.setRange(_[0] * multiple, _[1] * multiple)

        self.hBoxLayout.addWidget(self.spinBox)
        self.hBoxLayout.addSpacing(24)

        self.spinBox.setValue(self.configItem.value * multiple)

    def leaveEvent(self, event):
        if self.configItem:
            cfg.set(self.configItem, self.spinBox.value() / self.multiple)
