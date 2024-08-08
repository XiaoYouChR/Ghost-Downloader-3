# coding:utf-8
from qfluentwidgets import (SettingCardGroup, SwitchSettingCard, FolderListSettingCard,
                            OptionsSettingCard, PushSettingCard,
                            HyperlinkCard, PrimaryPushSettingCard, ScrollArea,
                            ComboBoxSettingCard, ExpandLayout, Theme, CustomColorSettingCard,
                            setTheme, setThemeColor, RangeSettingCard, isDarkTheme, TitleLabel, LargeTitleLabel,
                            RangeConfigItem)
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import InfoBar
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QFileDialog

from ..common.config import cfg, FEEDBACK_URL, AUTHOR, VERSION, YEAR, AUTHOR_URL


class SettingInterface(ScrollArea):
    """ Setting interface """

    checkUpdateSig = Signal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.scrollWidget = QWidget()
        self.expandLayout = ExpandLayout(self.scrollWidget)

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

        self.downloadFolderCard = PushSettingCard(
            "选择文件夹",
            FIF.DOWNLOAD,
            "下载路径",
            cfg.get(cfg.downloadFolder),
            self.downloadGroup
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
            "软件更新", self.scrollWidget)
        self.updateOnStartUpCard = SwitchSettingCard(
            FIF.UPDATE,
            "在应用程序启动时检查更新",
            "新版本将更稳定，并具有更多功能",
            configItem=cfg.checkUpdateAtStartUp,
            parent=self.updateSoftwareGroup
        )

        # application
        self.aboutGroup = SettingCardGroup("关于", self.scrollWidget)
        self.authorCard = HyperlinkCard(
            AUTHOR_URL,
            "打开作者的个人空间",
            FIF.PROJECTOR,
            "了解作者",
            "发现更多 XiaoYouChR 的作品",
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
        self.setViewportMargins(0, 30, 0, 5)
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
        self.downloadGroup.addSettingCard(self.downloadFolderCard)

        # self.personalGroup.addSettingCard(self.themeCard)
        # self.personalGroup.addSettingCard(self.themeColorCard)
        self.personalGroup.addSettingCard(self.zoomCard)
        # self.personalGroup.addSettingCard(self.languageCard)


        self.updateSoftwareGroup.addSettingCard(self.updateOnStartUpCard)

        self.aboutGroup.addSettingCard(self.authorCard)
        self.aboutGroup.addSettingCard(self.feedbackCard)
        self.aboutGroup.addSettingCard(self.aboutCard)

        # add setting card group to layout
        self.expandLayout.setSpacing(20)
        self.expandLayout.setContentsMargins(36, 10, 36, 0)
        self.expandLayout.addWidget(self.downloadGroup)
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

    def __connectSignalToSlot(self):
        """ connect signal to slot """
        cfg.appRestartSig.connect(self.__showRestartTooltip)
        cfg.themeChanged.connect(setTheme)

        # download
        self.blockNumCard.valueChanged.connect(lambda: cfg.set(cfg.maxBlockNum, self.blockNumCard.configItem.value))
        self.downloadFolderCard.clicked.connect(
            self.__onDownloadFolderCardClicked)

        # personalization
        # self.themeColorCard.colorChanged.connect(setThemeColor)

        # about
        self.aboutCard.clicked.connect(self.checkUpdateSig)
        self.feedbackCard.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(FEEDBACK_URL)))
