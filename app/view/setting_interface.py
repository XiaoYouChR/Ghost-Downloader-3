# coding:utf-8
import os
import sys
from pathlib import Path
from typing import Union

from PySide6.QtCore import Qt, QUrl, QResource
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QWidget,
    QFileDialog,
    QVBoxLayout,
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QSpacerItem,
    QSizePolicy,
)
from qfluentwidgets import (
    FluentIcon as FIF,
    InfoBarPosition,
    ExpandGroupSettingCard,
    ConfigItem,
    BodyLabel,
    RadioButton,
    ComboBox,
    LineEdit,
    ComboBoxSettingCard,
    FlyoutView,
    Flyout,
    SettingCard,
    HyperlinkButton,
    FluentIconBase,
    RangeConfigItem,
    SpinBox,
)

if sys.platform != "darwin":
    from qfluentwidgets import SmoothScrollArea as ScrollArea
else:
    from qfluentwidgets import ScrollArea
from qfluentwidgets import InfoBar
from qfluentwidgets import (
    SettingCardGroup,
    SwitchSettingCard,
    PushSettingCard,
    HyperlinkCard,
    PrimaryPushSettingCard,
    setTheme,
    RangeSettingCard,
)

from ..common.config import (
    cfg,
    FEEDBACK_URL,
    AUTHOR,
    VERSION,
    YEAR,
    AUTHOR_URL,
    FIREFOX_ADDONS_URL,
    EDGE_ADDONS_URL,
    CHROME_ADDONS_URL,
)
from ..common.methods import getSystemProxy
from ..components.select_folder_setting_card import SelectFolderSettingCard
from ..components.update_dialog import checkUpdate


class CustomProxySettingCard(ExpandGroupSettingCard):
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
            FIF.GLOBE,
            self.tr("代理"),
            self.tr("设置下载时希望使用的代理"),
            parent=parent,
        )

        self.configItem = configItem

        self.choiceLabel = BodyLabel(self)

        self.radioWidget = QWidget(self.view)
        self.radioLayout = QVBoxLayout(self.radioWidget)
        self.offRadioButton = RadioButton(self.tr("不使用代理"), self.radioWidget)
        self.defaultRadioButton = RadioButton(
            self.tr("自动检测系统代理"), self.radioWidget
        )
        self.customRadioButton = RadioButton(
            self.tr("使用自定义代理"), self.radioWidget
        )

        self.buttonGroup = QButtonGroup(self)

        self.customProxyWidget = QWidget(self.view)
        self.customProxyLayout = QHBoxLayout(self.customProxyWidget)
        self.customLabel = BodyLabel(
            self.tr("编辑代理服务器: "), self.customProxyWidget
        )
        self.customProtocolComboBox = ComboBox(self.customProxyWidget)
        self.customProtocolComboBox.addItems(["socks5", "http", "https"])
        self.label_1 = BodyLabel("://", self.customProxyWidget)
        self.customIPLineEdit = LineEdit(self.customProxyWidget)
        self.customIPLineEdit.setPlaceholderText(self.tr("代理 IP 地址"))
        self.label_2 = BodyLabel(":", self.customProxyWidget)
        self.customPortLineEdit = LineEdit(self.customProxyWidget)
        self.customPortLineEdit.setPlaceholderText(self.tr("端口"))

        self.__initWidget()

        if self.configItem.value == "Auto":
            self.defaultRadioButton.setChecked(True)
            self.__onRadioButtonClicked(self.defaultRadioButton)
        elif self.configItem.value == "Off":
            self.offRadioButton.setChecked(True)
            self.__onRadioButtonClicked(self.offRadioButton)
        else:
            self.customRadioButton.setChecked(True)
            self.__onRadioButtonClicked(self.customRadioButton)
            self.customProtocolComboBox.setCurrentText(
                self.configItem.value[: self.configItem.value.find("://")]
            )
            _ = self.configItem.value[self.configItem.value.find("://") + 3 :].split(
                ":"
            )
            self.customIPLineEdit.setText(_[0])
            self.customPortLineEdit.setText(_[1])

            self.choiceLabel.setText(self.buttonGroup.checkedButton().text())
            self.choiceLabel.adjustSize()

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

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.radioWidget)
        self.addGroupWidget(self.customProxyWidget)

    def __onRadioButtonClicked(self, button: RadioButton):
        """radio button clicked slot"""
        if button.text() == self.choiceLabel.text():
            return

        self.choiceLabel.setText(button.text())
        self.choiceLabel.adjustSize()

        if button is self.defaultRadioButton:  # 自动
            # 禁用 custom 选项
            self.customProxyWidget.setDisabled(True)

            _ = getSystemProxy()
            # 分析 SystemProxy, SystemProxy 可能为 None, "", 类似于 "http://127.0.0.1:1080" 的格式, 若不为空则自动填充 custom 选项
            if _:
                protocol = _[: _.find("://")]
                self.customProtocolComboBox.setCurrentText(protocol)
                _ = _[_.find("://") + 3 :].split(":")
                self.customIPLineEdit.setText(_[0])
                self.customPortLineEdit.setText(_[1])
            else:
                self.customProtocolComboBox.setCurrentText("")
                self.customIPLineEdit.setText(self.tr("未检测到代理"))
                self.customPortLineEdit.setText("")

            cfg.set(self.configItem, "Auto")

        elif button is self.offRadioButton:  # 关闭
            # 禁用 custom 选项
            self.customProxyWidget.setDisabled(True)

            cfg.set(self.configItem, "Off")

        elif button is self.customRadioButton:
            # 启用 custom 选项
            self.customProxyWidget.setDisabled(False)

    def leaveEvent(self, event):  # 鼠标离开时检测 custom 选项是否合法并保存配置
        if self.customRadioButton.isChecked():
            protocol = self.customProtocolComboBox.currentText()
            ip = self.customIPLineEdit.text()
            port = self.customPortLineEdit.text()

            proxyServer = f"{protocol}://{ip}:{port}"
            if cfg.proxyServer.validator.PATTERN.match(proxyServer):
                cfg.set(self.configItem, proxyServer)
            else:
                self.defaultRadioButton.click()
                self.defaultRadioButton.setChecked(True)


class SpinBoxSettingCard(SettingCard):
    """Split Box Setting Card"""

    def __init__(
        self,
        icon: Union[str, QIcon, FluentIconBase],
        title,
        content=None,
        suffix: str = None,
        configItem: RangeConfigItem = None,
        parent=None,
        singleStep: int = 50,
        division: int = 1,
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


class SettingInterface(ScrollArea):
    """Setting interface"""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.scrollWidget = QWidget()
        self.expandLayout = QVBoxLayout(self.scrollWidget)

        # music folders
        self.downloadGroup = SettingCardGroup(
            self.tr("下载相关设置"), self.scrollWidget
        )

        self.blockNumCard = RangeSettingCard(
            cfg.preBlockNum,
            FIF.CLOUD,
            self.tr("预分配线程数"),
            self.tr(
                "线程越多，下载越快。线程数大于 64 时，有触发反爬导致文件损坏的风险"
            ),
            self.downloadGroup,
        )

        self.maxReassignSizeCard = RangeSettingCard(
            cfg.maxReassignSize,
            FIF.LIBRARY,
            self.tr("最大重新分配大小 (MB)"),
            self.tr(
                "每线程剩余量大于此值时, 有线程完成或自动提速条件满足会触发重新分配"
            ),
            self.downloadGroup,
        )

        self.maxTaskNumCard = RangeSettingCard(
            cfg.maxTaskNum,
            FIF.TRAIN,
            self.tr("最大任务数"),
            self.tr("最多能同时进行的任务数量"),
            self.downloadGroup,
        )

        self.speedLimitationCard = SpinBoxSettingCard(
            FIF.SPEED_OFF,
            self.tr("下载限速"),
            self.tr("限制每秒全局下载速度, 0 为不限速"),
            " KB/s",
            cfg.speedLimitation,
            self.downloadGroup,
            512,
            1 / 1024,
        )

        self.autoSpeedUpCard = SwitchSettingCard(
            FIF.SPEED_HIGH,
            self.tr("自动提速"),
            self.tr("AI 实时检测各线程效率并自动增加线程数以提高下载速度"),
            cfg.autoSpeedUp,
            self.downloadGroup,
        )

        self.SSLVerifyCard = SwitchSettingCard(
            FIF.DEVELOPER_TOOLS,
            self.tr("下载时验证 SSL 证书"),
            self.tr("文件无法下载时，可尝试关闭该选项"),
            cfg.SSLVerify,
            self.downloadGroup,
        )

        self.downloadFolderCard = SelectFolderSettingCard(
            cfg.downloadFolder, cfg.historyDownloadFolder, self.downloadGroup
        )
        # self.downloadFolderCard = PushSettingCard(
        #     "选择文件夹",
        #     FIF.DOWNLOAD,
        #     "下载路径",
        #     cfg.get(cfg.downloadFolder)
        # )

        self.proxyServerCard = CustomProxySettingCard(
            cfg.proxyServer, self.downloadGroup
        )

        # browser
        self.browserGroup = SettingCardGroup(self.tr("浏览器扩展"), self.scrollWidget)
        self.browserExtensionCard = SwitchSettingCard(
            FIF.CONNECT,
            self.tr("启用浏览器扩展"),
            self.tr("接收来自浏览器的下载信息，请安装浏览器扩展后使用"),
            cfg.enableBrowserExtension,
            self.browserGroup,
        )
        self.raiseWindowWhenReceiveMsg = SwitchSettingCard(
            FIF.CHAT,
            self.tr("收到下载信息时弹出窗口"),
            self.tr("收到下载信息时弹出窗口，方便您调整下载参数"),
            cfg.enableRaiseWindowWhenReceiveMsg,
            self.browserGroup,
        )
        self.installExtensionCard = PushSettingCard(
            self.tr("导出 Chromium 扩展"),
            FIF.DICTIONARY,
            self.tr("安装浏览器扩展"),
            self.tr("请选择最适合您的浏览器扩展安装方式"),
            self.browserGroup,
        )
        self.installFirefoxAddonsBtn = HyperlinkButton(self.installExtensionCard)
        self.installFirefoxAddonsBtn.setText(self.tr("Firefox"))
        self.installFirefoxAddonsBtn.setUrl(FIREFOX_ADDONS_URL)
        self.installExtensionCard.hBoxLayout.insertWidget(
            5, self.installFirefoxAddonsBtn, 0, Qt.AlignRight
        )
        self.installExtensionCard.hBoxLayout.insertSpacing(6, 16)

        self.installFirefoxAddonsBtn = HyperlinkButton(self.installExtensionCard)
        self.installFirefoxAddonsBtn.setText(self.tr("Edge"))
        self.installFirefoxAddonsBtn.setUrl(EDGE_ADDONS_URL)
        self.installExtensionCard.hBoxLayout.insertWidget(
            5, self.installFirefoxAddonsBtn, 0, Qt.AlignRight
        )
        self.installExtensionCard.hBoxLayout.insertSpacing(6, 16)

        self.installFirefoxAddonsBtn = HyperlinkButton(self.installExtensionCard)
        self.installFirefoxAddonsBtn.setText(self.tr("Chrome"))
        self.installFirefoxAddonsBtn.setUrl(CHROME_ADDONS_URL)
        self.installExtensionCard.hBoxLayout.insertWidget(
            5, self.installFirefoxAddonsBtn, 0, Qt.AlignRight
        )
        self.installExtensionCard.hBoxLayout.insertSpacing(6, 16)

        self.installExtensionGuidanceCard = PushSettingCard(
            self.tr("查看安装指南"),
            FIF.HELP,
            self.tr("浏览器扩展安装指南"),
            self.tr("解决安装浏览器扩展时遇到的常见问题"),
            self.browserGroup,
        )
        # personalization
        self.personalGroup = SettingCardGroup(self.tr("个性化"), self.scrollWidget)
        self.themeCard = ComboBoxSettingCard(
            cfg.customThemeMode,
            FIF.BRUSH,
            self.tr("应用主题"),
            self.tr("更改应用程序的外观"),
            texts=[self.tr("浅色"), self.tr("深色"), self.tr("跟随系统设置")],
            parent=self.personalGroup,
        )
        # self.themeColorCard = CustomColorSettingCard(
        #     cfg.themeColor,
        #     FIF.PALETTE,
        #     '主题色',
        #     '更改应用程序的主题颜色',
        #     self.personalGroup
        # )
        if sys.platform == "win32":
            self.backgroundEffectCard = ComboBoxSettingCard(
                cfg.backgroundEffect,
                FIF.TRANSPARENT,
                self.tr("窗口背景透明材质"),
                self.tr("设置窗口背景透明效果和透明材质"),
                texts=["Acrylic", "Mica", "MicaBlur", "MicaAlt", "Aero", "None"],
                parent=self.personalGroup,
            )
        self.zoomCard = SpinBoxSettingCard(
            FIF.ZOOM,
            self.tr("界面缩放"),
            self.tr("改变应用程序界面的缩放比例, 0% 为自动"),
            " %",
            cfg.dpiScale,
            self.personalGroup,
            division=100,
        )
        self.languageCard = ComboBoxSettingCard(
            cfg.language,
            FIF.LANGUAGE,
            self.tr("语言"),
            self.tr("设置界面的首选语言"),
            texts=[
                "简体中文 (中国大陆)",
                "正體中文 (台灣)",
                "粤语 (香港)",
                "文言 (華夏)",
                "English (US)",
                "日本語 (日本)",
                self.tr("使用系统设置"),
            ],
            parent=self.personalGroup,
        )
        # update software
        self.softwareGroup = SettingCardGroup(self.tr("应用"), self.scrollWidget)
        self.updateOnStartUpCard = SwitchSettingCard(
            FIF.UPDATE,
            self.tr("在应用程序启动时检查更新"),
            self.tr("新版本将更稳定，并具有更多功能"),
            configItem=cfg.checkUpdateAtStartUp,
            parent=self.softwareGroup,
        )
        self.autoRunCard = SwitchSettingCard(
            FIF.VPN,
            self.tr("开机启动"),
            self.tr("在系统启动时静默运行 Ghost Downloader"),
            configItem=cfg.autoRun,
            parent=self.softwareGroup,
        )
        self.clipboardListenerCard = SwitchSettingCard(
            FIF.PASTE,
            self.tr("剪贴板监听"),
            self.tr("剪贴板监听器将自动检测剪贴板中的链接并添加下载任务"),
            configItem=cfg.enableClipboardListener,
            parent=self.softwareGroup,
        )
        # application
        self.aboutGroup = SettingCardGroup(self.tr("关于"), self.scrollWidget)
        self.authorCard = HyperlinkCard(
            AUTHOR_URL,
            self.tr("打开作者的个人空间"),
            FIF.PROJECTOR,
            self.tr("了解作者"),
            self.tr("发现更多 {} 的作品").format(AUTHOR),
            self.aboutGroup,
        )
        self.feedbackCard = PrimaryPushSettingCard(
            self.tr("提供反馈"),
            FIF.FEEDBACK,
            self.tr("提供反馈"),
            self.tr("通过提供反馈来帮助我们改进 Ghost Downloader"),
            self.aboutGroup,
        )
        self.aboutCard = PrimaryPushSettingCard(
            self.tr("检查更新"),
            FIF.INFO,
            self.tr("关于"),
            "© " + "Copyright" + f" {YEAR}, {AUTHOR}. " + f"Version {VERSION}",
            self.aboutGroup,
        )

        self.resize(1000, 800)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.setObjectName("settingInterface")

        # initialize style sheet
        self.scrollWidget.setObjectName("scrollWidget")
        self.setStyleSheet(
            """QScrollArea, .QWidget {
                                border: none;
                                background-color: transparent;
                            }"""
        )

        # initialize layout
        self.__initLayout()
        self.__connectSignalToSlot()

    def __initLayout(self):

        # add cards to group
        self.downloadGroup.addSettingCard(self.blockNumCard)
        self.downloadGroup.addSettingCard(self.maxReassignSizeCard)
        self.downloadGroup.addSettingCard(self.maxTaskNumCard)
        self.downloadGroup.addSettingCard(self.speedLimitationCard)
        self.downloadGroup.addSettingCard(self.autoSpeedUpCard)
        self.downloadGroup.addSettingCard(self.SSLVerifyCard)
        self.downloadGroup.addSettingCard(self.downloadFolderCard)
        self.downloadGroup.addSettingCard(self.proxyServerCard)

        self.browserGroup.addSettingCard(self.browserExtensionCard)
        self.browserGroup.addSettingCard(self.raiseWindowWhenReceiveMsg)
        self.browserGroup.addSettingCard(self.installExtensionCard)
        self.browserGroup.addSettingCard(self.installExtensionGuidanceCard)
        self.personalGroup.addSettingCard(self.themeCard)
        # self.personalGroup.addSettingCard(self.themeColorCard)
        if sys.platform == "win32":
            self.personalGroup.addSettingCard(self.backgroundEffectCard)
        self.personalGroup.addSettingCard(self.zoomCard)
        self.personalGroup.addSettingCard(self.languageCard)

        self.softwareGroup.addSettingCard(self.updateOnStartUpCard)
        self.softwareGroup.addSettingCard(self.clipboardListenerCard)
        self.softwareGroup.addSettingCard(self.autoRunCard)

        self.aboutGroup.addSettingCard(self.authorCard)
        self.aboutGroup.addSettingCard(self.feedbackCard)
        self.aboutGroup.addSettingCard(self.aboutCard)

        # add setting card group to layout
        self.expandLayout.setSpacing(20)
        self.expandLayout.setContentsMargins(36, 30, 36, 30)
        self.expandLayout.addWidget(self.downloadGroup)
        self.expandLayout.addWidget(self.browserGroup)
        self.expandLayout.addWidget(self.personalGroup)
        self.expandLayout.addWidget(self.softwareGroup)
        self.expandLayout.addWidget(self.aboutGroup)

    def __showRestartTooltip(self):
        """show restart tooltip"""
        InfoBar.success(
            self.tr("已配置"), self.tr("重启软件后生效"), duration=1500, parent=self
        )

    def __onDownloadFolderChanged(self, path):
        cfg.set(cfg.downloadFolder, path)

    def __onBackgroundEffectCardChanged(self, option):
        """background effect card changed slot"""
        self.window().applyBackgroundEffectByCfg()

    def __onBrowserExtensionCardChecked(self, value: bool):
        if value:  # enable
            self.window().runBrowserExtensionServer()
        if not value:
            self.window().stopBrowserExtensionServer()

    def __onClipboardListenerCardChecked(self, value: bool):
        if value:
            self.window().runClipboardListener()
        else:
            self.window().stopClipboardListener()

    def __onInstallExtensionCardClicked(self):
        """install extension card clicked slot"""
        fileResolve, type = QFileDialog.getSaveFileName(
            self,
            self.tr("选择导出路径"),
            "./Extension.crx",
            "Chromium Extension(*.crx)",
        )
        if fileResolve:
            with open(fileResolve, "wb") as f:
                f.write(QResource(":/res/chrome_extension.crx").data())

    def __onInstallExtensionGuidanceClicked(self):
        """install extension guidance card clicked slot"""
        view = FlyoutView(
            title=self.tr("安装指南"),
            content=self.tr("请按照步骤安装浏览器扩展"),
            image=":/res/install_chrome_extension_guidance.png",
            isClosable=True,
        )

        view.viewLayout.insertSpacing(0, 960)

        # show view
        w = Flyout.make(view, self.installExtensionGuidanceCard.button, self)
        view.closed.connect(w.close)
        # view.closed.connect(w.deleteLater)
        # view.closed.connect(view.deleteLater)

    def __onAutoRunCardChecked(self, value: bool):
        """Set auto run"""
        if sys.platform == "win32":
            import winreg

            if value:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0,
                    winreg.KEY_WRITE,
                )
                winreg.SetValueEx(
                    key,
                    "GhostDownloader",
                    0,
                    winreg.REG_SZ,
                    '"{}" --silence'.format(
                        QApplication.applicationFilePath().replace("/", "\\")
                    ),
                )
            else:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0,
                    winreg.KEY_WRITE,
                )
                winreg.DeleteValue(key, "GhostDownloader")
        elif sys.platform == "darwin":
            import pwd

            if value:
                with open(
                    f"/Users/{pwd.getpwuid(os.getuid()).pw_name}/Library/LaunchAgents/com.xiaoyouchr.ghostdownloader.plist",
                    "w",
                ) as f:
                    f.write(
                        f"""<?xml version="1.0" encoding="UTF-8"?>
                                <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
                                <plist version="1.0">
                                <dict>
                                <key>Label</key>
                                <string>com.xiaoyouchr.ghostdownloader</string>
                                <key>ProgramArguments</key>
                                <array>
                                <string>'{QApplication.applicationFilePath()}'</string>
                                <string>--silence</string>
                                </array>
                                <key>RunAtLoad</key>
                                <true/>
                                </dict>
                                </plist>"""
                    )
            else:
                os.remove(
                    f"/Users/{pwd.getpwuid(os.getuid()).pw_name}/Library/LaunchAgents/com.xiaoyouchr.ghostdownloader.plist"
                )
        elif sys.platform == "linux":
            if value:
                autoStartPath = Path(f"/home/{os.getlogin()}/.config/autostart/")
                if not autoStartPath.exists():
                    autoStartPath.mkdir(parents=True, exist_ok=True)

                with open(
                    f"/home/{os.getlogin()}/.config/autostart/gd3.desktop",
                    "w",
                    encoding="utf-8",
                ) as f:
                    _ = f"""[Desktop Entry]
                        Type=Application
                        Version={VERSION}
                        Name=Ghost Downloader 3
                        Comment=A multi-threading downloader with QThread based on PySide6
                        Exec="{QApplication.applicationFilePath()}" --silence
                        StartupNotify=false
                        Terminal=false
                        """
                    print(_)
                    f.write(_)
                    f.flush()

            else:
                os.remove(f"/home/{os.getlogin()}/.config/autostart/gd3.desktop")

        else:
            InfoBar.warning(
                title=self.tr("警告"),
                content=self.tr("鬼知道你用的是什么平台？"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                # position='Custom',   # NOTE: use custom info bar manager
                duration=1000,
                parent=self.parent(),
            )

    def __onAboutCardClicked(self):
        """check update and show information"""
        InfoBar.info(
            self.tr("请稍候"),
            self.tr("正在检查更新..."),
            position=InfoBarPosition.TOP_RIGHT,
            duration=1000,
            parent=self,
        )
        checkUpdate(self.window())

    def __connectSignalToSlot(self):
        """connect signal to slot"""
        cfg.appRestartSig.connect(self.__showRestartTooltip)
        cfg.themeChanged.connect(setTheme)

        # download
        self.blockNumCard.valueChanged.connect(
            lambda: cfg.set(cfg.preBlockNum, self.blockNumCard.configItem.value)
        )
        self.downloadFolderCard.pathChanged.connect(self.__onDownloadFolderChanged)

        # extension
        self.browserExtensionCard.checkedChanged.connect(
            self.__onBrowserExtensionCardChecked
        )
        self.installExtensionCard.clicked.connect(self.__onInstallExtensionCardClicked)
        self.installExtensionGuidanceCard.clicked.connect(
            self.__onInstallExtensionGuidanceClicked
        )

        # personalization
        if sys.platform == "win32":
            self.backgroundEffectCard.comboBox.currentIndexChanged.connect(
                self.__onBackgroundEffectCardChanged
            )

        # software
        self.autoRunCard.checkedChanged.connect(self.__onAutoRunCardChecked)

        # about
        self.aboutCard.clicked.connect(self.__onAboutCardClicked)
        self.feedbackCard.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(FEEDBACK_URL))
        )
