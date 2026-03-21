import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QResource, QCoreApplication, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFileDialog
from qfluentwidgets import SettingCardGroup, RangeSettingCard, FluentIcon, SwitchSettingCard, PushSettingCard, \
    HyperlinkButton, ComboBoxSettingCard, HyperlinkCard, PrimaryPushSettingCard, InfoBar, FlyoutView, Flyout, \
    InfoBarPosition, ToolButton, ToolTipFilter

from app.supports.config import cfg, FIREFOX_ADDONS_URL, EDGE_ADDONS_URL, CHROME_ADDONS_URL, AUTHOR_URL, AUTHOR, YEAR, \
    VERSION, FEEDBACK_URL
from app.supports.utils import openAppLogFolder
from app.view.components.setting_cards import SpinBoxSettingCard, SelectFolderSettingCard, ProxySettingCard

if TYPE_CHECKING:
    from app.view.windows.main_window import MainWindow

if sys.platform != "darwin":
    from qfluentwidgets import SmoothScrollArea as ScrollArea
else:
    from qfluentwidgets import ScrollArea


class SettingPage(ScrollArea):
    """设置页面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Initialize
        self.container = QWidget()
        self.vBoxLayout = QVBoxLayout(self.container)
        self.generalDownloadGroup = SettingCardGroup(self.tr("综合下载设置"), self.container)
        self.browserGroup = SettingCardGroup(self.tr("浏览器扩展"), self.container)
        self.personalGroup = SettingCardGroup(self.tr("个性化"), self.container)
        self.softwareGroup = SettingCardGroup(self.tr("应用"), self.container)
        self.aboutGroup = SettingCardGroup(self.tr("关于"), self.container)

        self.initWidget()
        self.initCards()
        self.initLayout()
        self.connectSignalToSlot()

    def initWidget(self):
        self.setWidget(self.container)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setObjectName("SettingPage")
        self.enableTransparentBackground()

    def initCards(self):
        # General Download
        self.maxTaskNumCard = RangeSettingCard(
            cfg.maxTaskNum,
            FluentIcon.TRAIN,
            self.tr("最大任务数"),
            self.tr("最多能同时进行的任务数量"),
            self.generalDownloadGroup,
        )
        self.generalDownloadGroup.addSettingCard(self.maxTaskNumCard)
        self.preBlockNumCard = RangeSettingCard(
            cfg.preBlockNum,
            FluentIcon.CLOUD,
            self.tr("预分配线程数"),
            self.tr(
                "线程越多，下载越快。线程数大于 64 时，有触发反爬导致文件损坏的风险"
            ),
            self.generalDownloadGroup,
        )
        self.generalDownloadGroup.addSettingCard(self.preBlockNumCard)
        self.autoSpeedUpCard = SwitchSettingCard(
            FluentIcon.SPEED_HIGH,
            self.tr("自动提速"),
            self.tr("AI 实时检测各线程效率并自动增加线程数以提高下载速度"),
            cfg.autoSpeedUp,
            self.generalDownloadGroup,
        )
        self.generalDownloadGroup.addSettingCard(self.autoSpeedUpCard)
        self.maxReassignSizeCard = RangeSettingCard(
            cfg.maxReassignSize,
            FluentIcon.LIBRARY,
            self.tr("最大重新分配大小 (MB)"),
            self.tr(
                "每线程剩余量大于此值时, 有线程完成或自动提速条件满足会触发重新分配"
            ),
            self.generalDownloadGroup,
        )
        self.generalDownloadGroup.addSettingCard(self.maxReassignSizeCard)
        self.speedLimitationCard = SpinBoxSettingCard(
            FluentIcon.SPEED_OFF,
            self.tr("下载限速"),
            self.tr("当下载任务界面限速开关开启时，所有任务将根据此值进行限速"),
            " KB/s",
            cfg.speedLimitation,
            self.generalDownloadGroup,
            512,
            1 / 1024,
        )
        self.generalDownloadGroup.addSettingCard(self.speedLimitationCard)
        self.SSLVerifyCard = SwitchSettingCard(
            FluentIcon.DEVELOPER_TOOLS,
            self.tr("下载时验证 SSL 证书"),
            self.tr("文件无法下载时，可尝试关闭该选项"),
            cfg.SSLVerify,
            self.generalDownloadGroup,
        )
        self.generalDownloadGroup.addSettingCard(self.SSLVerifyCard)
        self.downloadFolderCard = SelectFolderSettingCard(
            cfg.downloadFolder.value, cfg.memoryDownloadFolders, self.generalDownloadGroup
        )
        self.generalDownloadGroup.addSettingCard(self.downloadFolderCard)
        self.proxyServerCard = ProxySettingCard(
            cfg.proxyServer, self.generalDownloadGroup
        )
        self.generalDownloadGroup.addSettingCard(self.proxyServerCard)
        # Browser
        self.browserExtensionCard = SwitchSettingCard(
            FluentIcon.CONNECT,
            self.tr("启用浏览器扩展"),
            self.tr("接收来自浏览器的下载信息，请安装浏览器扩展后使用"),
            cfg.enableBrowserExtension,
            self.browserGroup,
        )
        self.browserGroup.addSettingCard(self.browserExtensionCard)
        self.raiseWindowWhenReceiveMsg = SwitchSettingCard(
            FluentIcon.CHAT,
            self.tr("收到下载信息时弹出窗口"),
            self.tr("收到下载信息时弹出窗口，方便您调整下载参数"),
            cfg.enableRaiseWindowWhenReceiveMsg,
            self.browserGroup,
        )
        self.browserGroup.addSettingCard(self.raiseWindowWhenReceiveMsg)
        self.installExtensionCard = PushSettingCard(
            self.tr("导出 Chromium 扩展"),
            FluentIcon.DICTIONARY,
            self.tr("安装浏览器扩展"),
            self.tr("请选择最适合您的浏览器扩展安装方式"),
            self.browserGroup,
        )
        self.browserGroup.addSettingCard(self.installExtensionCard)
        self.installFirefoxAddonsBtn = HyperlinkButton(self.installExtensionCard)
        self.installFirefoxAddonsBtn.setText(self.tr("Firefox"))
        self.installFirefoxAddonsBtn.setUrl(FIREFOX_ADDONS_URL)
        self.installExtensionCard.hBoxLayout.insertWidget(
            5, self.installFirefoxAddonsBtn, 0, Qt.AlignmentFlag.AlignRight
        )
        self.installExtensionCard.hBoxLayout.insertSpacing(6, 16)
        self.installFirefoxAddonsBtn = HyperlinkButton(self.installExtensionCard)
        self.installFirefoxAddonsBtn.setText(self.tr("Edge"))
        self.installFirefoxAddonsBtn.setUrl(EDGE_ADDONS_URL)
        self.installExtensionCard.hBoxLayout.insertWidget(
            5, self.installFirefoxAddonsBtn, 0, Qt.AlignmentFlag.AlignRight
        )
        self.installExtensionCard.hBoxLayout.insertSpacing(6, 16)
        self.installFirefoxAddonsBtn = HyperlinkButton(self.installExtensionCard)
        self.installFirefoxAddonsBtn.setText(self.tr("Chrome"))
        self.installFirefoxAddonsBtn.setUrl(CHROME_ADDONS_URL)
        self.installExtensionCard.hBoxLayout.insertWidget(
            5, self.installFirefoxAddonsBtn, 0, Qt.AlignmentFlag.AlignRight
        )
        self.installExtensionCard.hBoxLayout.insertSpacing(6, 16)
        self.installExtensionGuidanceCard = PushSettingCard(
            self.tr("查看安装指南"),
            FluentIcon.HELP,
            self.tr("浏览器扩展安装指南"),
            self.tr("解决安装浏览器扩展时遇到的常见问题"),
            self.browserGroup,
        )
        self.browserGroup.addSettingCard(self.installExtensionGuidanceCard)
        # Personalization
        self.themeCard = ComboBoxSettingCard(
            cfg.customThemeMode,
            FluentIcon.BRUSH,
            self.tr("应用主题"),
            self.tr("更改应用程序的外观"),
            texts=[self.tr("浅色"), self.tr("深色"), self.tr("跟随系统设置")],
            parent=self.personalGroup,
        )
        self.personalGroup.addSettingCard(self.themeCard)
        # self.themeColorCard = CustomColorSettingCard(
        #     cfg.themeColor,
        #     FluentIcon.PALETTE,
        #     '主题色',
        #     '更改应用程序的主题颜色',
        #     self.personalGroup
        # )
        if sys.platform == "win32":
            self.backgroundEffectCard = ComboBoxSettingCard(
                cfg.backgroundEffect,
                FluentIcon.TRANSPARENT,
                self.tr("窗口背景透明材质"),
                self.tr("设置窗口背景透明效果和透明材质"),
                texts=["Acrylic", "Mica", "MicaAlt", "Aero", "None"],
                parent=self.personalGroup,
            )
            self.personalGroup.addSettingCard(self.backgroundEffectCard)
        self.zoomCard = SpinBoxSettingCard(
            FluentIcon.ZOOM,
            self.tr("界面缩放"),
            self.tr("改变应用程序界面的缩放比例, 0% 为自动"),
            " %",
            cfg.dpiScale,
            self.personalGroup,
            division=100,
        )
        self.personalGroup.addSettingCard(self.zoomCard)
        self.languageCard = ComboBoxSettingCard(
            cfg.language,
            FluentIcon.LANGUAGE,
            self.tr("语言"),
            self.tr("设置界面的首选语言"),
            texts=[
                "简体中文 (中国大陆)",
                "正體中文 (台灣)",
                "粤语 (香港)",
                # "文言 (華夏)",
                "English (US)",
                "日本語 (日本)",
                "Русский (Россия)",
                self.tr("使用系统设置"),
            ],
            parent=self.personalGroup,
        )
        self.personalGroup.addSettingCard(self.languageCard)
        # Software
        self.updateOnStartUpCard = SwitchSettingCard(
            FluentIcon.UPDATE,
            self.tr("在应用程序启动时检查更新"),
            self.tr("新版本将更稳定，并具有更多功能"),
            configItem=cfg.checkUpdateAtStartUp,
            parent=self.softwareGroup,
        )
        self.softwareGroup.addSettingCard(self.updateOnStartUpCard)
        self.autoRunCard = SwitchSettingCard(
            FluentIcon.VPN,
            self.tr("开机启动"),
            self.tr("在系统启动时静默运行 Ghost Downloader"),
            configItem=cfg.autoRun,
            parent=self.softwareGroup,
        )
        self.softwareGroup.addSettingCard(self.autoRunCard)
        self.clipboardListenerCard = SwitchSettingCard(
            FluentIcon.PASTE,
            self.tr("剪贴板监听"),
            self.tr("剪贴板监听器将自动检测剪贴板中的链接并添加下载任务"),
            configItem=cfg.enableClipboardListener,
            parent=self.softwareGroup,
        )
        self.softwareGroup.addSettingCard(self.clipboardListenerCard)
        # Application
        self.authorCard = HyperlinkCard(
            AUTHOR_URL,
            self.tr("打开作者的个人空间"),
            FluentIcon.PROJECTOR,
            self.tr("了解作者"),
            self.tr("发现更多 {} 的作品").format(AUTHOR),
            self.aboutGroup,
        )
        self.aboutGroup.addSettingCard(self.authorCard)
        self.feedbackCard = PrimaryPushSettingCard(
            self.tr("提供反馈"),
            FluentIcon.FEEDBACK,
            self.tr("提供反馈"),
            self.tr("通过提供反馈来帮助我们改进 Ghost Downloader"),
            self.aboutGroup,
        )
        self.aboutGroup.addSettingCard(self.feedbackCard)
        self.openLogButton = ToolButton(FluentIcon.DOCUMENT, self.feedbackCard)
        self.openLogButton.setToolTip(self.tr("查看日志"))
        self.openLogButton.installEventFilter(ToolTipFilter(self.openLogButton))
        self.feedbackCard.hBoxLayout.insertSpacing(6, 8)
        self.feedbackCard.hBoxLayout.insertWidget(7, self.openLogButton, 0, Qt.AlignmentFlag.AlignRight)
        self.aboutCard = PrimaryPushSettingCard(
            self.tr("检查更新"),
            FluentIcon.INFO,
            self.tr("关于"),
            "© " + "Copyright" + f" {YEAR}, {AUTHOR}. " + f"Version {VERSION}",
            self.aboutGroup,
        )
        self.aboutGroup.addSettingCard(self.aboutCard)

    def initLayout(self):
        self.vBoxLayout.addWidget(self.generalDownloadGroup)
        self.vBoxLayout.addWidget(self.browserGroup)
        self.vBoxLayout.addWidget(self.personalGroup)
        self.vBoxLayout.addWidget(self.softwareGroup)
        self.vBoxLayout.addWidget(self.aboutGroup)

    def connectSignalToSlot(self):
        cfg.appRestartSig.connect(self._showRestartTooltip)
        self.downloadFolderCard.pathChanged.connect(lambda x: cfg.set(cfg.downloadFolder, x))
        self.installExtensionCard.clicked.connect(self._onInstallExtensionCardClicked)
        self.installExtensionGuidanceCard.clicked.connect(self._onInstallExtensionGuidanceClicked)
        self.autoRunCard.checkedChanged.connect(self._onAutoRunCardChecked)
        self.aboutCard.clicked.connect(self._onAboutCardClicked)
        self.feedbackCard.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(FEEDBACK_URL))
        )
        self.openLogButton.clicked.connect(openAppLogFolder)

    def _showRestartTooltip(self):
        InfoBar.success(
            self.tr("已配置"), self.tr("重启软件后生效"), duration=1500, parent=self
        )

    def _onAboutCardClicked(self):
        mainWindow: "MainWindow" = self.window()
        mainWindow.checkForUpdates(manual=True)

    def _onInstallExtensionCardClicked(self):
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

    def _onInstallExtensionGuidanceClicked(self):
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
        view.closed.connect(w.deleteLater)
        view.closed.connect(view.deleteLater)

    def _onAutoRunCardChecked(self, value: bool):
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
                        QCoreApplication.applicationFilePath().replace("/", "\\")
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
            from pwd import getpwuid

            if value:
                with open(
                    f"/Users/{getpwuid(os.getuid()).pw_name}/Library/LaunchAgents/com.xiaoyouchr.ghostdownloader.plist",
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
                                <string>'{QCoreApplication.applicationFilePath()}'</string>
                                <string>--silence</string>
                                </array>
                                <key>RunAtLoad</key>
                                <true/>
                                </dict>
                                </plist>"""
                    )
            else:
                os.remove(
                    f"/Users/{getpwuid(os.getuid()).pw_name}/Library/LaunchAgents/com.xiaoyouchr.ghostdownloader.plist"
                )
        elif sys.platform == "linux":
            from getpass import getuser
            if value:
                autoStartPath = Path(f"/home/{getuser()}/.config/autostart/")
                if not autoStartPath.exists():
                    autoStartPath.mkdir(parents=True, exist_ok=True)

                with open(
                    f"/home/{getuser()}/.config/autostart/gd3.desktop",
                    "w",
                    encoding="utf-8",
                ) as f:
                    _ = f"""[Desktop Entry]
                        Type=Application
                        Version={VERSION}
                        Name=Ghost Downloader 3
                        Comment=A multi-threading downloader with QThread based on PySide6
                        Exec="{QCoreApplication.applicationFilePath()}" --silence
                        StartupNotify=false
                        Terminal=false
                        """
                    f.write(_)
                    f.flush()
            else:
                os.remove(f"/home/{getuser()}/.config/autostart/gd3.desktop")

        else:
            InfoBar.warning(
                title=self.tr("警告"),
                content=self.tr("鬼知道你用的是什么平台？"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=1000,
                parent=self.parent(),
            )
