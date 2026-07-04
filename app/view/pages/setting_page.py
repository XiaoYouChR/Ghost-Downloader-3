from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QVBoxLayout, QWidget, QApplication
from qfluentwidgets import (
    ComboBoxSettingCard, FluentIcon, HyperlinkCard, HyperlinkButton, InfoBar,
    InfoBarPosition, MessageBox, PrimaryPushSettingCard, PushSettingCard,
    RangeSettingCard, SwitchSettingCard, ToolButton, ToolTipFilter,
)

from app.view.components.scroll_area import ScrollArea

from app.config.cfg import cfg
from app.platform.android import IS_ANDROID
from app.config.constants import (
    AUTHOR, AUTHOR_URL, EDGE_ADDONS_URL, FEEDBACK_URL,
    FIREFOX_ADDONS_URL, VERSION, YEAR,
)
from app.view.components.category_settings import CategoryRulesCard
from app.view.components.setting_card_group import CollapsibleSettingCardGroup
from app.view.components.setting_cards import (
    ClientProfileSettingCard, DefaultHeadersSettingCard, LineEditSettingCard,
    ProxySettingCard, SpinBoxSettingCard,
)
from app.view.components.editors import FolderPicker


class SettingPage(ScrollArea):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.container = QWidget()
        self.vBoxLayout = QVBoxLayout(self.container)
        self.vBoxLayout.addStretch(1)

        from app.view.icons import AppIcon
        self.generalGroup = CollapsibleSettingCardGroup(AppIcon.DOWNLOAD, self.tr("综合下载设置"), "general", self.container)
        self.categoryGroup = CollapsibleSettingCardGroup(AppIcon.CATEGORY, self.tr("下载分类"), "category", self.container)
        self.browserGroup = CollapsibleSettingCardGroup(AppIcon.BROWSER, self.tr("浏览器扩展"), "browser", self.container)
        self.aria2RpcGroup = CollapsibleSettingCardGroup(AppIcon.CONNECT, self.tr("Aria2 RPC 兼容"), "aria2rpc", self.container)
        self.personalGroup = CollapsibleSettingCardGroup(AppIcon.CUSTOMIZE, self.tr("个性化"), "personalization", self.container)
        self.softwareGroup = CollapsibleSettingCardGroup(AppIcon.APPLICATION, self.tr("应用"), "software", self.container)
        self.aboutGroup = CollapsibleSettingCardGroup(AppIcon.ABOUT, self.tr("关于"), "about", self.container)

        self._initWidget()
        self._initCards()
        self._initLayout()
        self._bind()

    def addSettingGroup(self, group: CollapsibleSettingCardGroup) -> None:
        self.vBoxLayout.insertWidget(self.vBoxLayout.count() - 1, group)

    def _initWidget(self) -> None:
        self.setWidget(self.container)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setObjectName("SettingPage")
        self.enableTransparentBackground()
        self.setProperty("isStackedTransparent", False)

    def _initCards(self) -> None:
        self.speedLimitationCard = SpinBoxSettingCard(
            FluentIcon.SPEED_OFF, self.tr("下载限速"),
            self.tr("当下载任务界面限速开关开启时，所有任务将根据此值进行限速"),
            suffix=" KB/s", configItem=cfg.speedLimitation,
            singleStep=512, division=1 / 1024,
        )
        from qfluentwidgets import SettingCard
        self.downloadFolderCard = SettingCard(FluentIcon.FOLDER, self.tr("下载路径"), self.tr("文件默认保存位置"))
        self.downloadFolderPicker = FolderPicker(self.downloadFolderCard)
        self.downloadRestoreButton = ToolButton(FluentIcon.CANCEL, self.downloadFolderCard)
        self.downloadRestoreButton.setToolTip(self.tr("恢复默认路径"))
        self.downloadRestoreButton.installEventFilter(ToolTipFilter(self.downloadRestoreButton))
        self.downloadFolderPicker.refreshHistory()
        self.downloadFolderPicker.setPath(cfg.downloadFolder.value)
        self.downloadFolderCard.hBoxLayout.addWidget(self.downloadFolderPicker, 0, Qt.AlignmentFlag.AlignRight)
        self.downloadFolderCard.hBoxLayout.addSpacing(8)
        self.downloadFolderCard.hBoxLayout.addWidget(self.downloadRestoreButton, 0, Qt.AlignmentFlag.AlignRight)
        self.downloadFolderCard.hBoxLayout.addSpacing(16)
        self.clientProfileCard = ClientProfileSettingCard()

        self.generalGroup.addSettingCards([
            RangeSettingCard(cfg.maxTaskNum, FluentIcon.TRAIN, self.tr("最大任务数"),
                             self.tr("最多能同时进行的任务数量")),
            RangeSettingCard(cfg.preBlockNum, FluentIcon.CLOUD, self.tr("预分配线程数"),
                             self.tr("线程越多，下载越快。线程数大于 64 时，有触发反爬导致文件损坏的风险")),
            SwitchSettingCard(FluentIcon.SPEED_HIGH, self.tr("自动提速"),
                              self.tr("AI 实时检测各线程效率并自动增加线程数以提高下载速度"),
                              cfg.autoSpeedUp),
            SpinBoxSettingCard(FluentIcon.LIBRARY, self.tr("最小再分配大小"),
                              self.tr("每线程剩余量大于此值时, 有线程完成或自动提速条件满足会触发重新分配"),
                              " KB", cfg.maxReassignSize, singleStep=64),
            self.speedLimitationCard,
            SwitchSettingCard(FluentIcon.HISTORY, self.tr("保留文件修改时间"),
                              self.tr("下载完成后将文件的修改时间设为服务器提供的 Last-Modified 值"),
                              cfg.shouldPreserveLastModified),
            SwitchSettingCard(FluentIcon.DEVELOPER_TOOLS, self.tr("下载时验证 SSL 证书"),
                              self.tr("文件无法下载时，可尝试关闭该选项"),
                              cfg.shouldVerifySsl),
            self.downloadFolderCard,
            ProxySettingCard(cfg.proxyServer),
            self.clientProfileCard,
            DefaultHeadersSettingCard(FluentIcon.DICTIONARY, self.tr("默认请求头"),
                                      self.tr("设置默认 HTTP 请求头，User-Agent 由模拟身份控制（选择原样发送时除外）")),
        ])

        self.categoryRulesCard = CategoryRulesCard()
        self.categoryGroup.addSettingCards([
            SwitchSettingCard(FluentIcon.TAG, self.tr("启用下载分类"),
                              self.tr("根据扩展名将下载任务归类，便于筛选与分发到指定文件夹"),
                              cfg.isCategoryEnabled),
            self.categoryRulesCard,
        ])

        self.browserPairTokenCard = PrimaryPushSettingCard(
            self.tr("复制令牌"), FluentIcon.COPY, self.tr("配对令牌"),
            cfg.browserExtensionPairToken.value,
        )
        self.regenerateTokenButton = ToolButton(FluentIcon.SYNC, self.browserPairTokenCard)
        self.regenerateTokenButton.setToolTip(self.tr("重新生成令牌"))
        self.regenerateTokenButton.installEventFilter(ToolTipFilter(self.regenerateTokenButton))
        self.browserPairTokenCard.hBoxLayout.insertSpacing(6, 8)
        self.browserPairTokenCard.hBoxLayout.insertWidget(
            7, self.regenerateTokenButton, 0, Qt.AlignmentFlag.AlignRight,
        )

        self.storeInstallCard = HyperlinkCard(
            EDGE_ADDONS_URL, self.tr("Edge 商店"), FluentIcon.GLOBE,
            self.tr("从商店安装扩展"),
            self.tr("商店版扩展需等待审核后才能获得更新"),
        )
        firefoxBtn = HyperlinkButton(self.storeInstallCard)
        firefoxBtn.setText(self.tr("Firefox 商店"))
        firefoxBtn.setUrl(FIREFOX_ADDONS_URL)
        self.storeInstallCard.hBoxLayout.insertWidget(
            5, firefoxBtn, 0, Qt.AlignmentFlag.AlignRight,
        )
        self.storeInstallCard.hBoxLayout.insertSpacing(6, 16)

        self.chromiumInstallCard = PrimaryPushSettingCard(
            self.tr("一键安装"), FluentIcon.DOWNLOAD,
            self.tr("安装到 Chromium 浏览器"),
            self.tr("自动解包扩展并引导加载（Chrome / Brave 等），扩展随桌面端更新自动升级"),
        )
        self.exportExtensionButton = HyperlinkButton(self.chromiumInstallCard)
        self.exportExtensionButton.setText(self.tr("导出 CRX"))
        self.chromiumInstallCard.hBoxLayout.insertWidget(
            5, self.exportExtensionButton, 0, Qt.AlignmentFlag.AlignRight,
        )
        self.chromiumInstallCard.hBoxLayout.insertSpacing(6, 16)

        self.browserPortCard = SpinBoxSettingCard(
            FluentIcon.COMMAND_PROMPT, self.tr("服务端口"),
            self.tr("浏览器扩展连接使用的端口"),
            configItem=cfg.browserExtensionPort, singleStep=1, division=1,
        )

        self.browserEnableCard = SwitchSettingCard(
            FluentIcon.CONNECT, self.tr("启用浏览器扩展"),
            self.tr("接收来自浏览器的下载信息，请安装浏览器扩展后使用"),
            cfg.isBrowserExtensionEnabled,
        )

        self.urlSchemeCard = SwitchSettingCard(
            FluentIcon.LINK, self.tr("注册 URL 协议"),
            self.tr("注册 ghostdownloader:// 协议，允许浏览器扩展启动桌面端"),
            cfg.isUrlSchemeRegistered,
        ) if sys.platform != "darwin" else None

        browserCards = [
            self.browserEnableCard,
            SwitchSettingCard(FluentIcon.CHAT, self.tr("收到下载信息时弹出窗口"),
                              self.tr("收到下载信息时弹出窗口，方便您调整下载参数"),
                              cfg.shouldRaiseWindowOnBrowserTask),
            self.browserPairTokenCard,
            self.storeInstallCard,
            self.chromiumInstallCard,
            self.browserPortCard,
        ]
        if self.urlSchemeCard:
            browserCards.insert(2, self.urlSchemeCard)

        self.browserGroup.addSettingCards(browserCards)

        self.aria2RpcGroup.addSettingCards([
            SwitchSettingCard(
                FluentIcon.LINK, self.tr("启用 Aria2 RPC 兼容"),
                self.tr("兼容 Aria2 JSON-RPC 协议，可接收外部工具发送的下载链接"),
                cfg.isAria2RpcEnabled,
            ),
            SpinBoxSettingCard(
                FluentIcon.GLOBE, self.tr("监听端口"),
                self.tr("Aria2 RPC 默认端口为 16800"),
                configItem=cfg.aria2RpcPort, singleStep=1, division=1,
            ),
            LineEditSettingCard(
                FluentIcon.FINGERPRINT, self.tr("令牌"),
                self.tr("若设置，客户端需传入 token 才可创建任务"),
                configItem=cfg.aria2RpcToken,
                placeholder=self.tr("可选"),
                isPassword=True,
            ),
            SwitchSettingCard(
                FluentIcon.VPN, self.tr("模拟浏览器指纹"),
                self.tr("为通过 Aria2 RPC 接收的任务附加浏览器 TLS 指纹与请求头"),
                cfg.aria2RpcEmulateFingerprint,
            ),
        ])

        self.zoomCard = SpinBoxSettingCard(
            FluentIcon.ZOOM, self.tr("界面缩放"),
            self.tr("改变应用程序界面的缩放比例, 0% 为自动"),
            suffix=" %", configItem=cfg.dpiScale, division=100,
        )

        personalCards = [
            ComboBoxSettingCard(cfg.themeMode, FluentIcon.BRUSH, self.tr("应用主题"),
                                self.tr("更改应用程序的外观"),
                                texts=[self.tr("浅色"), self.tr("深色"), self.tr("跟随系统设置")]),
        ]
        if sys.platform == "win32":
            personalCards.append(
                ComboBoxSettingCard(cfg.backgroundEffect, FluentIcon.TRANSPARENT,
                                    self.tr("窗口背景透明材质"),
                                    self.tr("设置窗口背景透明效果和透明材质"),
                                    texts=["Acrylic", "Mica", "MicaAlt", "Aero", "None"]),
            )
        personalCards.append(self.zoomCard)
        if sys.platform == "darwin":
            self.showDockIconCard = SwitchSettingCard(
                FluentIcon.APPLICATION, self.tr("在 Dock 栏中显示程序"),
                self.tr("关闭后可通过菜单栏图标继续使用程序"),
                cfg.shouldShowDockIcon,
            )
            self.showDockSpeedCard = SwitchSettingCard(
                FluentIcon.SPEED_HIGH, self.tr("在 Dock 图标上显示实时速度"),
                self.tr("下载时在程序坞图标上叠加当前速度"),
                cfg.shouldShowDockSpeed,
            )
            self.showDockSpeedCard.setEnabled(cfg.shouldShowDockIcon.value)
            personalCards.extend([
                self.showDockIconCard,
                self.showDockSpeedCard,
                SwitchSettingCard(FluentIcon.SPEED_HIGH, self.tr("在菜单栏显示实时速度"),
                                  self.tr("下载时在菜单栏图标旁显示当前速度"),
                                  cfg.shouldShowMenuBarSpeed),
            ])
        personalCards.append(
            ComboBoxSettingCard(cfg.language, FluentIcon.LANGUAGE, self.tr("语言"),
                                self.tr("设置界面的首选语言"),
                                texts=["简体中文 (中国大陆)", "正體中文 (台灣)", "粤语 (香港)",
                                       "English (US)", "日本語 (日本)", "Русский (Россия)",
                                       "Português (Brasil)", self.tr("使用系统设置")]),
        )
        self.personalGroup.addSettingCards(personalCards)

        self.autoRunCard = SwitchSettingCard(
            FluentIcon.VPN, self.tr("开机启动"),
            self.tr("在系统启动时静默运行 Ghost Downloader"),
            cfg.shouldRunAtLogin,
        )
        from app.config.paths import APP_DATA_DIR, isPortable
        if isPortable():
            self.migrateCard = PushSettingCard(
                self.tr("切换到用户模式"), FluentIcon.SYNC,
                self.tr("数据存储模式"),
                self.tr("当前为 Portable 模式，数据保存在程序旁: {0}").format(APP_DATA_DIR),
            )
        else:
            self.migrateCard = PushSettingCard(
                self.tr("切换到 Portable 模式"), FluentIcon.SYNC,
                self.tr("数据存储模式"),
                self.tr("当前为用户模式，数据保存在: {0}").format(APP_DATA_DIR),
            )

        softwareCards = [
            SwitchSettingCard(FluentIcon.UPDATE, self.tr("在应用程序启动时检查更新"),
                              self.tr("新版本将更稳定，并具有更多功能"),
                              cfg.shouldCheckUpdateAtStartup),
            self.autoRunCard,
            SwitchSettingCard(FluentIcon.PASTE, self.tr("剪贴板监听"),
                              self.tr("剪贴板监听器将自动检测剪贴板中的链接并添加下载任务"),
                              cfg.isClipboardListenerEnabled),
        ]
        if not IS_ANDROID:
            softwareCards.append(self.migrateCard)
        self.softwareGroup.addSettingCards(softwareCards)

        self.feedbackCard = PrimaryPushSettingCard(
            self.tr("提供反馈"), FluentIcon.FEEDBACK,
            self.tr("提供反馈"),
            self.tr("通过提供反馈来帮助我们改进 Ghost Downloader"),
        )
        self.openLogButton = ToolButton(FluentIcon.DOCUMENT, self.feedbackCard)
        self.openLogButton.setToolTip(self.tr("查看日志"))
        self.openLogButton.installEventFilter(ToolTipFilter(self.openLogButton))
        self.feedbackCard.hBoxLayout.insertSpacing(6, 8)
        self.feedbackCard.hBoxLayout.insertWidget(
            7, self.openLogButton, 0, Qt.AlignmentFlag.AlignRight,
        )

        self.aboutCard = PrimaryPushSettingCard(
            self.tr("检查更新"), FluentIcon.INFO, self.tr("关于"),
            f"© Copyright {YEAR}, {AUTHOR}. Version {VERSION}",
        )

        self.aboutGroup.addSettingCards([
            HyperlinkCard(AUTHOR_URL, self.tr("打开作者的个人空间"), FluentIcon.PROJECTOR,
                          self.tr("了解作者"), self.tr("发现更多 {} 的作品").format(AUTHOR)),
            self.feedbackCard,
            self.aboutCard,
        ])

    def _initLayout(self) -> None:
        self.addSettingGroup(self.generalGroup)
        self.addSettingGroup(self.categoryGroup)
        self.addSettingGroup(self.browserGroup)
        self.addSettingGroup(self.aria2RpcGroup)
        self.addSettingGroup(self.personalGroup)
        self.addSettingGroup(self.softwareGroup)
        from app.services.feature_service import featureService
        for group in featureService.settingGroups(self.container):
            self.addSettingGroup(group)
        self.addSettingGroup(self.aboutGroup)

    def _bind(self) -> None:
        from app.services.browser_service import browserService

        cfg.appRestartSig.connect(self._showRestartTooltip)
        cfg.browserExtensionPairToken.valueChanged.connect(self._refreshPairTokenCard)
        browserService.connectionChanged.connect(self._refreshBrowserStatus)
        if sys.platform == "darwin":
            cfg.shouldShowDockIcon.valueChanged.connect(self.showDockSpeedCard.setEnabled)

        self.downloadFolderPicker.pathChanged.connect(self._onDownloadFolderChanged)
        self.downloadRestoreButton.clicked.connect(
            lambda: (self.downloadFolderPicker.setPath(cfg.downloadFolder.defaultValue),
                     cfg.set(cfg.downloadFolder, cfg.downloadFolder.defaultValue))
        )

        self.browserPairTokenCard.clicked.connect(self._onCopyTokenClicked)
        self.regenerateTokenButton.clicked.connect(self._onRegenerateTokenClicked)
        self.chromiumInstallCard.clicked.connect(self._onChromiumInstallClicked)
        self.exportExtensionButton.clicked.connect(self._onExportExtensionClicked)
        if self.urlSchemeCard:
            self.urlSchemeCard.checkedChanged.connect(self._onUrlSchemeChanged)
        self.autoRunCard.checkedChanged.connect(self._onRunAtLoginChanged)
        self.aboutCard.clicked.connect(self._onAboutCardClicked)
        self.feedbackCard.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(FEEDBACK_URL)))
        self.openLogButton.clicked.connect(self._onOpenLogClicked)
        if not IS_ANDROID:
            self.migrateCard.clicked.connect(self._onMigrateClicked)

    def _onDownloadFolderChanged(self, path: str) -> None:
        cfg.set(cfg.downloadFolder, path)
        self.downloadFolderPicker.saveHistory(path)

    def _showRestartTooltip(self) -> None:
        InfoBar.success(self.tr("已配置"), self.tr("重启软件后生效"), duration=1500, parent=self)

    def _refreshPairTokenCard(self) -> None:
        from app.services.browser_service import browserService
        self.browserPairTokenCard.setContent(browserService.token)

    def _onCopyTokenClicked(self) -> None:
        from app.services.browser_service import browserService
        token = browserService.token
        if not token:
            return
        QApplication.clipboard().setText(token)
        InfoBar.success(self.tr("已复制配对令牌"), token,
                        duration=2000, position=InfoBarPosition.BOTTOM_RIGHT, parent=self.window())

    def _onRegenerateTokenClicked(self) -> None:
        from app.services.browser_service import browserService
        token = browserService.regenerateToken()
        QApplication.clipboard().setText(token)
        InfoBar.success(self.tr("已重新生成配对令牌"), self.tr("新令牌已复制到剪贴板"),
                        duration=2000, position=InfoBarPosition.BOTTOM_RIGHT, parent=self.window())

    def _onChromiumInstallClicked(self) -> None:
        from app.services.browser_service import extractBrowserExtension, EXTENSION_UNPACK_DIR
        from app.services.coroutine_runner import coroutineRunner

        coroutineRunner.submit(
            extractBrowserExtension(),
            done=self._onExtensionExtractDone,
            failed=self._onExtensionExtractFailed,
        )

    def _onExtensionExtractDone(self, path) -> None:
        from app.view.dialogs.extension_install import ExtensionInstallDialog
        ExtensionInstallDialog(path, self.window()).exec()

    def _onExtensionExtractFailed(self, error: str) -> None:
        InfoBar.error(self.tr("解包失败"), error,
                      duration=3000, position=InfoBarPosition.BOTTOM_RIGHT, parent=self.window())

    def _refreshBrowserStatus(self) -> None:
        from app.services.browser_service import browserService
        installType, version = browserService.connectionSummary
        port = browserService.boundPort
        if not installType:
            text = self.tr("未连接")
        elif installType == "development":
            text = self.tr("已连接 v{} (桌面端自管理)").format(version)
        else:
            text = self.tr("已连接 v{} (商店安装)").format(version)
        self.browserEnableCard.setContent(text)

    def _onExportExtensionClicked(self) -> None:
        from PySide6.QtCore import QFile, QIODevice, QResource
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, self.tr("选择导出路径"),
                                              "./Extension.crx", "Chromium Extension(*.crx)")
        if path:
            f = QFile(path)
            if f.open(QIODevice.OpenModeFlag.WriteOnly):
                f.write(bytes(QResource(":/res/chrome_extension.crx").data()))
                f.close()

    def _onUrlSchemeChanged(self, enabled: bool) -> None:
        from app.platform.url_scheme import registerUrlScheme, unregisterUrlScheme
        if enabled:
            registerUrlScheme()
        else:
            unregisterUrlScheme()

    def _onRunAtLoginChanged(self, enabled: bool) -> None:
        from app.platform.run_at_login import setRunAtLogin
        setRunAtLogin(enabled)

    def _onMigrateClicked(self) -> None:
        from app.config.paths import isPortable, migrate, PORTABLE_PATH, USER_PATH

        target = USER_PATH if isPortable() else PORTABLE_PATH
        mode = self.tr("用户模式") if isPortable() else self.tr("Portable 模式")
        dialog = MessageBox(
            self.tr("切换数据存储模式"),
            self.tr("确定要切换到{0}吗？\n\n数据将被复制到新位置，程序随后退出。请手动重新打开。").format(mode),
            self.window(),
        )
        if not dialog.exec():
            return

        QApplication.instance().aboutToQuit.connect(lambda: migrate(target))
        QApplication.instance().quit()

    def _onAboutCardClicked(self) -> None:
        from app.services.coroutine_runner import coroutineRunner
        from app.update import fetchRelease

        InfoBar.info(self.tr("检查更新"), self.tr("正在检查更新..."),
                     duration=1500, position=InfoBarPosition.BOTTOM_RIGHT, parent=self.window())
        coroutineRunner.submit(
            fetchRelease(),
            done=self._onUpdateChecked, failed=self._onUpdateCheckFailed,
            owner=self,
        )

    def _onUpdateChecked(self, release) -> None:
        from app.config.constants import VERSION
        from app.update import isOutdated

        if not isOutdated(release):
            InfoBar.success(self.tr("当前已是最新版本"),
                            self.tr("当前版本 {0}，最新版本 {1}").format(VERSION, release.version),
                            duration=3000, position=InfoBarPosition.BOTTOM_RIGHT, parent=self.window())
            return

        from app.update import showReleaseDialog
        showReleaseDialog(release, self.window())

    def _onUpdateCheckFailed(self, error: str) -> None:
        InfoBar.error(self.tr("检查更新失败"), self.tr("无法获取最新版本信息"),
                      duration=3000, position=InfoBarPosition.BOTTOM_RIGHT, parent=self.window())

    def _onOpenLogClicked(self) -> None:
        from app.config.paths import APP_DATA_DIR
        from app.platform.desktop import revealInFolder
        revealInFolder(f"{APP_DATA_DIR}/GhostDownloader.log")

    def showEvent(self, event) -> None:
        self._restoreOrder()
        super().showEvent(event)

    def _restoreOrder(self) -> None:
        groups = [
            self.vBoxLayout.itemAt(i).widget()
            for i in range(self.vBoxLayout.count())
            if self.vBoxLayout.itemAt(i).widget()
        ]
        keyToWidget = {g.objectName(): g for g in groups}
        order = [k for k in cfg.settingGroupOrder.value if k in keyToWidget]
        rest = [k for k in keyToWidget if k not in order]
        aboutKey = self.aboutGroup.objectName()
        if aboutKey in rest:
            rest.remove(aboutKey)
            rest.append(aboutKey)
        order += rest
        for idx, key in enumerate(order):
            self.vBoxLayout.insertWidget(idx, keyToWidget[key])
        for g in groups:
            if isinstance(g, CollapsibleSettingCardGroup):
                g.updateArrows()
