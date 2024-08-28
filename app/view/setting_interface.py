# coding:utf-8
import sys, os

from PySide6.QtCore import Qt, Signal, QUrl, QResource
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QFileDialog, QVBoxLayout, QApplication
from qfluentwidgets import FluentIcon as FIF, InfoBarPosition
from qfluentwidgets import InfoBar
from qfluentwidgets import (SettingCardGroup, SwitchSettingCard, OptionsSettingCard, PushSettingCard,
                            HyperlinkCard, PrimaryPushSettingCard, ScrollArea,
                            setTheme, RangeSettingCard)

from ..common.config import cfg, FEEDBACK_URL, AUTHOR, VERSION, YEAR, AUTHOR_URL
from ..components.update_dialog import checkUpdate


class SettingInterface(ScrollArea):
    """ Setting interface """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.scrollWidget = QWidget()
        self.expandLayout = QVBoxLayout(self.scrollWidget)

        # music folders
        self.downloadGroup = SettingCardGroup(
            "下载相关设置", self.scrollWidget)

        self.blockNumCard = RangeSettingCard(
            cfg.maxBlockNum,
            FIF.CLOUD,
            "下载线程数",
            '下载线程越多，下载越快，同时也越吃性能',
            self.downloadGroup
        )

        self.maxReassignSizeCard = RangeSettingCard(
            cfg.maxReassignSize,
            FIF.LIBRARY,
            "最大重新分配大小 (MB)",
            '已完成的线程将帮助工作量最大的线程分担下载任务，防止文件越下越慢',
            self.downloadGroup
        )


        self.downloadFolderCard = PushSettingCard(
            "选择文件夹",
            FIF.DOWNLOAD,
            "下载路径",
            cfg.get(cfg.downloadFolder),
            self.downloadGroup
        )

        # browser
        self.browserGroup = SettingCardGroup(
            "浏览器扩展", self.scrollWidget)
        self.browserExtensionCard = SwitchSettingCard(
            FIF.CONNECT,
            "启用浏览器扩展",
            "接收来自浏览器的下载信息，请安装浏览器扩展后使用",
            cfg.enableBrowserExtension,
            self.browserGroup,
        )
        self.installExtensionCard = PushSettingCard(
            "导出浏览器插件",
            FIF.DICTIONARY,
            "安装浏览器扩展",
            "需要您导出 .crx 文件后手动安装至 Chromium 内核的浏览器",
            self.browserGroup
        )

        # personalization
        self.personalGroup = SettingCardGroup(
            "个性化", self.scrollWidget)
        # self.themeCard = OptionsSettingCard(
        #     cfg.themeMode,
        #     FIF.BRUSH,
        #     self.tr('Application theme'),
        #     self.tr("Change the appearance of your application"),
        #     texts=[
        #         self.tr('Light'), self.tr('Dark'),
        #         self.tr('Use system setting')
        #     ],
        #     parent=self.personalGroup
        # )
        # self.themeColorCard = CustomColorSettingCard(
        #     cfg.themeColor,
        #     FIF.PALETTE,
        #     self.tr('Theme color'),
        #     self.tr('Change the theme color of you application'),
        #     self.personalGroup
        # )
        self.zoomCard = OptionsSettingCard(
            cfg.dpiScale,
            FIF.ZOOM,
            "界面缩放",
            "改变应用程序界面的缩放比例",
            texts=[
                "100%", "125%", "150%", "175%", "200%",
                "自动"
            ],
            parent=self.personalGroup
        )
        # self.languageCard = ComboBoxSettingCard(
        #     cfg.language,
        #     FIF.LANGUAGE,
        #     self.tr('Language'),
        #     self.tr('Set your preferred language for UI'),
        #     texts=['简体中文', '繁體中文', 'English', self.tr('Use system setting')],
        #     parent=self.personalGroup
        # )

        # update software
        self.updateSoftwareGroup = SettingCardGroup(
            "应用", self.scrollWidget)
        self.updateOnStartUpCard = SwitchSettingCard(
            FIF.UPDATE,
            "在应用程序启动时检查更新",
            "新版本将更稳定，并具有更多功能",
            configItem=cfg.checkUpdateAtStartUp,
            parent=self.updateSoftwareGroup
        )
        self.autoRunCard = SwitchSettingCard(
            FIF.VPN,
            "开机启动",
            "在系统启动时静默运行 Ghost Downloader",
            configItem=cfg.autoRun,
            parent=self.updateSoftwareGroup
        )

        # application
        self.aboutGroup = SettingCardGroup("关于", self.scrollWidget)
        self.authorCard = HyperlinkCard(
            AUTHOR_URL,
            "打开作者的个人空间",
            FIF.PROJECTOR,
            "了解作者",
            f"发现更多 {AUTHOR} 的作品",
            self.aboutGroup
        )
        self.feedbackCard = PrimaryPushSettingCard(
            "提供反馈",
            FIF.FEEDBACK,
            "提供反馈",
            "通过提供反馈来帮助我们改进 Ghost Downloader",
            self.aboutGroup
        )
        self.aboutCard = PrimaryPushSettingCard(
            "检查更新",
            FIF.INFO,
            "关于",
            '© ' + 'Copyright' + f" {YEAR}, {AUTHOR}. " +
            f'Version {VERSION}',
            self.aboutGroup
        )

        self.__initWidget()

        # Apply QSS
        self.setStyleSheet("""QScrollArea, .QWidget {
                                border: none;
                                background-color: transparent;
                            }""")

    def __initWidget(self):
        self.resize(1000, 800)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.setObjectName('settingInterface')

        # initialize style sheet
        self.scrollWidget.setObjectName('scrollWidget')

        # initialize layout
        self.__initLayout()
        self.__connectSignalToSlot()

    def __initLayout(self):

        # add cards to group
        self.downloadGroup.addSettingCard(self.blockNumCard)
        self.downloadGroup.addSettingCard(self.maxReassignSizeCard)
        self.downloadGroup.addSettingCard(self.downloadFolderCard)

        self.browserGroup.addSettingCard(self.browserExtensionCard)
        self.browserGroup.addSettingCard(self.installExtensionCard)
        # self.personalGroup.addSettingCard(self.themeCard)
        # self.personalGroup.addSettingCard(self.themeColorCard)
        self.personalGroup.addSettingCard(self.zoomCard)
        # self.personalGroup.addSettingCard(self.languageCard)


        self.updateSoftwareGroup.addSettingCard(self.updateOnStartUpCard)
        self.updateSoftwareGroup.addSettingCard(self.autoRunCard)

        self.aboutGroup.addSettingCard(self.authorCard)
        self.aboutGroup.addSettingCard(self.feedbackCard)
        self.aboutGroup.addSettingCard(self.aboutCard)

        # add setting card group to layout
        self.expandLayout.setSpacing(20)
        self.expandLayout.setContentsMargins(36, 30, 36, 30)
        self.expandLayout.addWidget(self.downloadGroup)
        self.expandLayout.addWidget(self.browserGroup)
        self.expandLayout.addWidget(self.personalGroup)
        self.expandLayout.addWidget(self.updateSoftwareGroup)
        self.expandLayout.addWidget(self.aboutGroup)

    def __showRestartTooltip(self):
        """ show restart tooltip """
        InfoBar.success(
            "已配置",
            "重启软件后生效",
            duration=1500,
            parent=self
        )

    def __onDownloadFolderCardClicked(self):
        """ download folder card clicked slot """
        folder = QFileDialog.getExistingDirectory(
            self, "选择下载文件夹", "./")
        if not folder or cfg.get(cfg.downloadFolder) == folder:
            return

        cfg.set(cfg.downloadFolder, folder)
        self.downloadFolderCard.setContent(folder)

    def __onBrowserExtensionCardChecked(self, value: bool):
        if value: # enable
            self.window().runBrowserExtensionServer()
        if not value:
            self.window().stopBrowserExtensionServer()

    def __onInstallExtensionCardClicked(self):
        """ install extension card clicked slot """
        fileResolve, type = QFileDialog.getSaveFileName(self, "选择导出路径", "./Extension.crx", "Chromium Extension(*.crx)")
        if fileResolve:
            with open(fileResolve, "wb") as f:
                f.write(QResource(":/res/chrome_extension.crx").data())

    def __onAutoRunCardChecked(self, value: bool):
        """ Set auto run """
        if sys.platform == "win32":
            import winreg
            if value:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                     r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_WRITE)
                winreg.SetValueEx(key, 'GhostDownloader', 0, winreg.REG_SZ,
                                  '"{}" --silence'.format(QApplication.applicationFilePath().replace("/", "\\")))
            else:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                     r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_WRITE)
                winreg.DeleteValue(key, 'GhostDownloader')
        elif sys.platform == "darwin":
            if value:
                with open(f"/Users/{os.getlogin()}/Library/LaunchAgents/app.ghost.downloader.plist", "w") as f:
                    f.write(f"""<?xml version="1.0" encoding="UTF-8"?>
                                <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
                                <plist version="1.0">
                                <dict>
                                <key>Label</key>
                                <string>app.ghost.downloader</string>
                                <key>ProgramArguments</key>
                                <array>
                                <string>{QApplication.applicationFilePath()}</string>
                                <string>--silence</string>
                                </array>
                                <key>RunAtLoad</key>
                                <true/>
                                </dict>
                                </plist>""")
            else:
                os.remove(f"/Users/{os.getlogin()}/Library/LaunchAgents/app.ghost.downloader.plist")
        else:
            InfoBar.warning(
                title='注意',
                content=f"该功能仅在 Windows/macOS 平台有效.",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                # position='Custom',   # NOTE: use custom info bar manager
                duration=1000,
                parent=self.parent()
            )

    def __onAboutCardClicked(self):
        """ check update and show information """
        InfoBar.info("请稍候", "正在检查更新...", position=InfoBarPosition.TOP_RIGHT, duration=1000, parent=self)
        checkUpdate(self)

    def __connectSignalToSlot(self):
        """ connect signal to slot """
        cfg.appRestartSig.connect(self.__showRestartTooltip)
        cfg.themeChanged.connect(setTheme)

        # download
        self.blockNumCard.valueChanged.connect(lambda: cfg.set(cfg.maxBlockNum, self.blockNumCard.configItem.value))
        self.downloadFolderCard.clicked.connect(
            self.__onDownloadFolderCardClicked)

        # extension
        self.browserExtensionCard.checkedChanged.connect(self.__onBrowserExtensionCardChecked)
        self.installExtensionCard.clicked.connect(self.__onInstallExtensionCardClicked)

        # software
        self.autoRunCard.checkedChanged.connect(self.__onAutoRunCardChecked)

        # about
        self.aboutCard.clicked.connect(self.__onAboutCardClicked)
        self.feedbackCard.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(FEEDBACK_URL)))
