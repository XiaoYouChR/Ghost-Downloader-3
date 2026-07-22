from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QCoreApplication, QRectF, QSize, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QMovie, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    BodyLabel, CaptionLabel, CardWidget, CheckBox, ComboBox,
    DrillInTransitionStackedWidget, FluentIcon, FluentWidget,
    GroupHeaderCardWidget, HorizontalPipsPager, IconWidget, InfoBar,
    InfoBarIcon, InfoBarPosition, PipsScrollButtonDisplayMode,
    PrimaryPushButton, PushButton, SubtitleLabel, SwitchButton, Theme,
    TitleLabel, TransparentPushButton, isDarkTheme, qconfig, themeColor,
)
from qfluentwidgets.common.style_sheet import updateStyleSheet

from app.config.cfg import cfg, LANGUAGE_TEXTS
from app.config.constants import (
    CHROME_WEBSTORE_URL, EDGE_ADDONS_URL, FIREFOX_ADDONS_URL,
    LATEST_EXTENSION_VERSION,
)

if TYPE_CHECKING:
    from app.models.pack import BinaryRuntime
    from app.services.browser_service import BrowserService
    from app.services.coroutine_runner import CoroutineRunner
    from app.services.feature_service import FeatureService
    from app.services.task_service import TaskService

WINDOW_SIZE = QSize(960, 600)
PREVIEW_GIF = ":/res/install_chrome_extension_guidance.webp"
# 960 - 边距 36*2 - 右栏 280 - 间距 16 = 592，按 16:9 取整
PREVIEW_SIZE = QSize(592, 333)
STORE_COLUMN_WIDTH = 280

NEUTRAL_CHIP_COLORS = ("#EFEFEF", "#666666", "#3D3D3D", "#AAAAAA")
SUCCESS_CHIP_COLORS = ("#E8F5E9", "#0F7B46", "#1A3A1A", "#4ADE80")


class IconChip(QWidget):

    def __init__(self, icon: FluentIcon, colors: tuple[str, str, str, str],
                 size: int = 40, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._colors = colors
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        lightBg, lightFg, darkBg, darkFg = self._colors
        bg, fg = (darkBg, darkFg) if isDarkTheme() else (lightBg, lightFg)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(self.rect(), 8, 8)
        margin = round(self.width() * 0.25)
        iconRect = self.rect().adjusted(margin, margin, -margin, -margin)
        self._icon.render(painter, iconRect, fill=fg)


class ThemePreview(QWidget):

    def __init__(self, mode: str, parent=None):
        super().__init__(parent)
        self._mode = mode
        self.setFixedHeight(96)

    def _drawMini(self, painter: QPainter, rect: QRectF, isDark: bool) -> None:
        bg = QColor("#232323") if isDark else QColor("#F5F7FA")
        titleBar = QColor("#2E2E2E") if isDark else QColor("#E9EDF2")
        bar = QColor("#333333") if isDark else QColor("#FFFFFF")

        painter.fillRect(rect, bg)
        painter.fillRect(QRectF(rect.x(), rect.y(), rect.width(), 14), titleBar)

        padding = 8
        barX = rect.x() + padding
        barWidth = rect.width() - padding * 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bar)
        painter.drawRoundedRect(QRectF(barX, rect.y() + 22, barWidth, 9), 3, 3)
        painter.drawRoundedRect(QRectF(barX, rect.y() + 37, barWidth * 0.55, 9), 3, 3)
        painter.setBrush(themeColor())
        painter.drawRoundedRect(
            QRectF(barX, rect.y() + rect.height() - 20, barWidth * 0.34, 11), 3, 3
        )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        outer = QRectF(self.rect())
        clipPath = QPainterPath()
        clipPath.addRoundedRect(outer, 6, 6)
        painter.setClipPath(clipPath)

        if self._mode == "auto":
            half = outer.width() / 2
            self._drawMini(painter, QRectF(outer.x(), outer.y(), half, outer.height()), isDark=False)
            self._drawMini(painter, QRectF(outer.x() + half, outer.y(), half, outer.height()), isDark=True)
        else:
            self._drawMini(painter, outer, isDark=self._mode == "dark")

        painter.setClipping(False)
        painter.setPen(QPen(QColor(128, 128, 128, 60), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(outer.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)


class ThemeCard(CardWidget):

    def __init__(self, theme: Theme, label: str, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._isSelected = False
        self._initWidget(label)
        self._initLayout()

    def _initWidget(self, label: str) -> None:
        self.setClickEnabled(True)
        mode = {Theme.LIGHT: "light", Theme.DARK: "dark"}.get(self.theme, "auto")
        self.preview = ThemePreview(mode, self)
        self.label = BodyLabel(label, self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def _initLayout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(10)
        layout.addWidget(self.preview)
        layout.addWidget(self.label)

    def setSelected(self, isSelected: bool) -> None:
        self._isSelected = isSelected
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._isSelected:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(themeColor(), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        radius = self.borderRadius
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), radius, radius)


class ActionCard(CardWidget):

    def __init__(self, icon: FluentIcon, title: str, hint: str = "",
                 isRecommended: bool = False, parent=None):
        super().__init__(parent)
        self._isRecommended = isRecommended
        self._initWidget(icon, title, hint)
        self._initLayout()

    def _initWidget(self, icon: FluentIcon, title: str, hint: str) -> None:
        self.setClickEnabled(True)
        if hint:
            self.setMinimumHeight(80)
        else:
            self.setFixedHeight(48)
        self.iconChip = IconChip(icon, NEUTRAL_CHIP_COLORS, size=30, parent=self)
        self.titleLabel = BodyLabel(title, self)
        self.hintLabel = None
        if hint:
            self.hintLabel = CaptionLabel(hint, self)
            self.hintLabel.setTextColor(Qt.GlobalColor.gray, Qt.GlobalColor.gray)
            self.hintLabel.setWordWrap(True)
        self.chevron = IconWidget(FluentIcon.CHEVRON_RIGHT_MED, self)
        self.chevron.setFixedSize(12, 12)

    def _initLayout(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(12)
        layout.addWidget(self.iconChip)

        textCol = QVBoxLayout()
        textCol.setSpacing(2)
        textCol.addWidget(self.titleLabel)
        if self.hintLabel is not None:
            textCol.addWidget(self.hintLabel)
        layout.addLayout(textCol, 1)
        layout.addWidget(self.chevron)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._isRecommended:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(themeColor(), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        radius = self.borderRadius
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), radius, radius)


class OptionCard(CardWidget):

    def __init__(self, icon: FluentIcon, title: str, desc: str,
                 isChecked: bool = False, parent=None):
        super().__init__(parent)
        self._initWidget(icon, title, desc, isChecked)
        self._initLayout()

    def _initWidget(self, icon: FluentIcon, title: str, desc: str, isChecked: bool) -> None:
        self.setFixedHeight(64)
        self.iconChip = IconChip(icon, NEUTRAL_CHIP_COLORS, size=34, parent=self)
        self.titleLabel = BodyLabel(title, self)
        self.descLabel = CaptionLabel(desc, self)
        self.descLabel.setTextColor(Qt.GlobalColor.gray, Qt.GlobalColor.gray)
        self.switch = SwitchButton(self)
        self.switch.setOnText("")
        self.switch.setOffText("")
        self.switch.setChecked(isChecked)

    def _initLayout(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 8, 18, 8)
        layout.setSpacing(14)
        layout.addWidget(self.iconChip)

        textCol = QVBoxLayout()
        textCol.setSpacing(0)
        textCol.addWidget(self.titleLabel)
        textCol.addWidget(self.descLabel)
        layout.addLayout(textCol, 1)
        layout.addWidget(self.switch)

    def isChecked(self) -> bool:
        return self.switch.isChecked()


class PageHeader(QWidget):

    def __init__(self, title: str, desc: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(SubtitleLabel(title, self))
        descLabel = CaptionLabel(desc, self)
        descLabel.setTextColor(Qt.GlobalColor.gray, Qt.GlobalColor.gray)
        layout.addWidget(descLabel)


class WelcomePage(QWidget):

    startClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.iconLabel = QLabel(self)
        self.iconLabel.setPixmap(QIcon(":/image/logo.png").pixmap(88, 88))
        self.iconLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.titleLabel = TitleLabel(self.tr("欢迎使用 Ghost Downloader"), self)
        self.titleLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.subtitleLabel = BodyLabel(
            self.tr("快速、智能的下载管理器。\n接下来的几步将帮助你完成基本配置。"), self
        )
        self.subtitleLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitleLabel.setWordWrap(True)

        self.startButton = PrimaryPushButton(self.tr("开始配置"), self)
        self.startButton.setFixedWidth(200)

    def _initLayout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)
        layout.addStretch(3)
        layout.addWidget(self.iconLabel, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(16)
        layout.addWidget(self.titleLabel)
        layout.addWidget(self.subtitleLabel)
        layout.addSpacing(28)
        layout.addWidget(self.startButton, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(4)

    def _bind(self) -> None:
        self.startButton.clicked.connect(self.startClicked)


class BasicSettingsPage(QWidget):

    languageChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.header = PageHeader(
            self.tr("基本设置"),
            self.tr("选择你喜欢的外观，设置下载文件的保存位置"), self,
        )

        self._themeCards: list[ThemeCard] = []
        for theme, label in [(Theme.LIGHT, self.tr("浅色")),
                              (Theme.DARK, self.tr("深色")),
                              (Theme.AUTO, self.tr("跟随系统"))]:
            self._themeCards.append(ThemeCard(theme, label, self))
        self._refreshThemeCards()

        self.settingsCard = GroupHeaderCardWidget(self.tr("偏好"), self)

        self.langCombo = ComboBox(self)
        self.langCombo.setMinimumWidth(200)
        for lang in cfg.language.options:
            self.langCombo.addItem(LANGUAGE_TEXTS.get(lang, self.tr("使用系统设置")))
        self.langCombo.setCurrentIndex(cfg.language.options.index(cfg.language.value))

        self.browseButton = PushButton(self.tr("浏览..."), self)

    def _initLayout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addStretch(1)

        themeRow = QHBoxLayout()
        themeRow.setSpacing(14)
        for card in self._themeCards:
            themeRow.addWidget(card)
        layout.addLayout(themeRow)
        layout.addStretch(1)

        self.settingsCard.addGroup(
            FluentIcon.LANGUAGE, self.tr("界面语言"),
            self.tr("更改立即生效"), self.langCombo,
        )
        self._folderGroup = self.settingsCard.addGroup(
            FluentIcon.FOLDER, self.tr("下载保存位置"),
            str(cfg.downloadFolder.value), self.browseButton,
        )
        layout.addWidget(self.settingsCard)
        layout.addStretch(1)

    def _bind(self) -> None:
        for card in self._themeCards:
            card.clicked.connect(lambda t=card.theme: self._onThemePicked(t))
        self.langCombo.currentIndexChanged.connect(self._onLanguageChanged)
        self.browseButton.clicked.connect(self._onBrowseClicked)

    def _onThemePicked(self, theme: Theme) -> None:
        cfg.set(cfg.themeMode, theme)
        updateStyleSheet()
        qconfig.themeChangedFinished.emit()
        self._refreshThemeCards()

    def _refreshThemeCards(self) -> None:
        current = cfg.themeMode.value
        for card in self._themeCards:
            card.setSelected(card.theme == current)

    def _onLanguageChanged(self, index: int) -> None:
        options = cfg.language.options
        if 0 <= index < len(options) and options[index] != cfg.language.value:
            cfg.set(cfg.language, options[index])
            self.languageChanged.emit()

    def _onBrowseClicked(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, self.tr("选择下载目录"), str(cfg.downloadFolder.value)
        )
        if folder:
            cfg.set(cfg.downloadFolder, folder)
            self._folderGroup.setContent(folder)


class BrowserExtensionPage(QWidget):

    def __init__(self, browserService: BrowserService, coroutineRunner: CoroutineRunner, parent: QWidget | None = None):
        super().__init__(parent)
        self._browserService = browserService
        self._coroutineRunner = coroutineRunner
        self._isPaired = False
        self._banner: InfoBar | None = None
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.header = PageHeader(
            self.tr("安装浏览器扩展"),
            self.tr("让浏览器中的下载自动接管到 Ghost Downloader"), self,
        )

        self.previewLabel = QLabel(self)
        self.previewLabel.setFixedSize(PREVIEW_SIZE)
        self.previewLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        movie = QMovie(PREVIEW_GIF, parent=self)
        if movie.isValid():
            movie.setScaledSize(PREVIEW_SIZE)
            self.previewLabel.setMovie(movie)
            movie.start()
        else:
            self.previewLabel.setText(self.tr("安装教程动图"))
            if isDarkTheme():
                bg, fg = "rgba(255,255,255,0.06)", "rgba(255,255,255,0.5)"
            else:
                bg, fg = "rgba(0,0,0,0.04)", "rgba(0,0,0,0.4)"
            self.previewLabel.setStyleSheet(
                f"QLabel {{ background: {bg}; color: {fg}; border-radius: 8px; }}"
            )

        self.manualCard = ActionCard(
            FluentIcon.DOWNLOAD, self.tr("手动安装"),
            self.tr("随桌面端自动更新，适用于所有 Chromium 浏览器"),
            isRecommended=True, parent=self,
        )
        self.storeCards: list[tuple[ActionCard, str]] = []
        for title, url in [
            (self.tr("Chrome 商店"), CHROME_WEBSTORE_URL),
            (self.tr("Edge 商店"), EDGE_ADDONS_URL),
            (self.tr("Firefox 商店"), FIREFOX_ADDONS_URL),
        ]:
            self.storeCards.append((ActionCard(FluentIcon.GLOBE, title, parent=self), url))

        self.footnote = CaptionLabel(self.tr("商店版更新需等待审核，可能滞后于桌面端"), self)
        self.footnote.setTextColor(Qt.GlobalColor.gray, Qt.GlobalColor.gray)

    def _initLayout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addStretch(1)

        contentLayout = QHBoxLayout()
        contentLayout.setSpacing(16)

        leftLayout = QVBoxLayout()
        leftLayout.setSpacing(10)
        leftLayout.addWidget(self.previewLabel)
        self._bannerSlot = QVBoxLayout()
        self._bannerSlot.setContentsMargins(0, 0, 0, 0)
        leftLayout.addLayout(self._bannerSlot)
        contentLayout.addLayout(leftLayout)

        rightWidget = QWidget(self)
        rightWidget.setFixedWidth(STORE_COLUMN_WIDTH)
        rightLayout = QVBoxLayout(rightWidget)
        rightLayout.setContentsMargins(0, 0, 0, 0)
        rightLayout.setSpacing(10)
        rightLayout.addStretch(1)
        rightLayout.addWidget(self.manualCard)
        for card, _ in self.storeCards:
            rightLayout.addWidget(card)
        rightLayout.addWidget(self.footnote)
        rightLayout.addStretch(1)
        contentLayout.addWidget(rightWidget)

        layout.addLayout(contentLayout)
        layout.addStretch(1)

    def _bind(self) -> None:
        self.manualCard.clicked.connect(self._onManualInstallClicked)
        for card, url in self.storeCards:
            card.clicked.connect(lambda u=url: QDesktopServices.openUrl(QUrl(u)))
        self._browserService.connectionChanged.connect(self._onConnectionChanged)
        self._browserService.protocolMismatched.connect(self._onProtocolMismatched)

    def _setBanner(self, icon: InfoBarIcon, title: str) -> None:
        if self._banner is not None:
            self._bannerSlot.removeWidget(self._banner)
            self._banner.deleteLater()
        self._banner = InfoBar(
            icon, title, "", isClosable=False,
            duration=-1, position=InfoBarPosition.NONE, parent=self,
        )
        self._banner.contentLabel.hide()
        self._banner.setFixedWidth(PREVIEW_SIZE.width())
        self._bannerSlot.addWidget(self._banner)

    def refreshPortStatus(self) -> None:
        if self._isPaired:
            return
        if self._browserService.boundPort:
            self._setBanner(
                InfoBarIcon.INFORMATION,
                self.tr("正在端口 {} 上等待扩展连接").format(browserService.boundPort),
            )
        elif not cfg.isBrowserExtensionEnabled.value:
            self._setBanner(
                InfoBarIcon.WARNING,
                self.tr("浏览器扩展未启用，可稍后在设置中开启"),
            )
        else:
            self._setBanner(
                InfoBarIcon.WARNING,
                self.tr("端口 {} 被占用，请在设置中更换端口").format(
                    cfg.browserExtensionPort.value
                ),
            )

    def _setConnectedBanner(self, version: str) -> None:
        if version:
            text = self.tr("已连接扩展 v{}，最新版本为 v{}").format(
                version, LATEST_EXTENSION_VERSION
            )
        else:
            text = self.tr("已连接扩展，最新版本为 v{}").format(LATEST_EXTENSION_VERSION)
        self._setBanner(InfoBarIcon.SUCCESS, text)

    def _onConnectionChanged(self) -> None:
        installType, version = self._browserService.connectionSummary
        if installType or version:
            self._isPaired = True
            self._setConnectedBanner(version)
        else:
            self._isPaired = False
            self.refreshPortStatus()

    def _onManualInstallClicked(self) -> None:
        from app.services.browser_service import extractBrowserExtension
        self._coroutineRunner.submit(
            extractBrowserExtension(),
            done=self._onExtensionExtracted,
            failed=self._onExtensionExtractFailed,
            owner=self,
        )

    def _onExtensionExtracted(self, path: Path) -> None:
        from app.platform.desktop import openChromiumUrl, revealInFolder
        revealInFolder(str(path))
        if not openChromiumUrl("chrome://extensions"):
            QApplication.clipboard().setText("chrome://extensions")
            InfoBar.info(
                self.tr("请手动打开浏览器"),
                self.tr("chrome://extensions 已复制到剪贴板"),
                duration=5000, position=InfoBarPosition.TOP, parent=self,
            )

    def _onExtensionExtractFailed(self, error) -> None:
        InfoBar.error(
            self.tr("解包失败"), str(error),
            duration=5000, position=InfoBarPosition.TOP, parent=self,
        )

    def onPairRequested(self, request: dict) -> None:
        self._browserService.approvePair(request["session"], request["requestId"])
        self._isPaired = True
        self._setConnectedBanner(request.get("extensionVersion", ""))

    def _onProtocolMismatched(self) -> None:
        self._setBanner(
            InfoBarIcon.WARNING,
            self.tr("协议版本不匹配，商店版可能滞后，请尝试手动安装"),
        )


class RuntimeInstallPage(QWidget):

    def __init__(self, featureService: FeatureService, parent: QWidget | None = None):
        super().__init__(parent)
        self._featureService = featureService
        self._checkBoxes: list[tuple[CheckBox, BinaryRuntime]] = []
        self._isMounted = False
        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
        self.header = PageHeader(
            self.tr("安装推荐组件"),
            self.tr("点击下一步将自动安装勾选的组件，稍后可在设置中管理"), self,
        )
        self._card = GroupHeaderCardWidget(self.tr("推荐组件"), self)

    def _initLayout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addStretch(1)
        layout.addWidget(self._card)
        layout.addStretch(1)

    def mount(self) -> None:
        if self._isMounted:
            return
        self._isMounted = True

        entries = [rt for rt in self._featureService.runtimes() if rt.canInstall and rt.title]
        entries.sort(key=lambda rt: not rt.isRecommended)

        for runtime in entries:
            trailing = QWidget(self)
            trailingLayout = QHBoxLayout(trailing)
            trailingLayout.setContentsMargins(0, 0, 0, 0)
            trailingLayout.setSpacing(12)

            tag = CaptionLabel(runtime.name, trailing)
            tag.setTextColor(Qt.GlobalColor.gray, Qt.GlobalColor.gray)
            trailingLayout.addWidget(tag)

            if runtime.path():
                installedLabel = CaptionLabel(self.tr("已安装"), trailing)
                installedLabel.setTextColor(Qt.GlobalColor.darkGreen, Qt.GlobalColor.green)
                trailingLayout.addWidget(installedLabel)
            else:
                checkBox = CheckBox(trailing)
                checkBox.setChecked(runtime.isRecommended)
                trailingLayout.addWidget(checkBox)
                self._checkBoxes.append((checkBox, runtime))

            self._card.addGroup(
                runtime.icon,
                QCoreApplication.translate("BinaryRuntime", runtime.title),
                QCoreApplication.translate("BinaryRuntime", runtime.description),
                trailing,
            )

    def selectedRuntimes(self) -> list[BinaryRuntime]:
        return [rt for cb, rt in self._checkBoxes if cb.isChecked()]


class AdvancedOptionsPage(QWidget):

    def __init__(self, featureService: FeatureService, parent: QWidget | None = None):
        super().__init__(parent)
        self._featureService = featureService
        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
        self.header = PageHeader(
            self.tr("更多选项"),
            self.tr("按需开启以下功能，也可以稍后在设置中修改"), self,
        )
        self.categoryCard = OptionCard(
            FluentIcon.TAG, self.tr("自动分类保存"),
            self.tr("按文件类型自动保存到 视频、音频、文档 等子文件夹"),
            isChecked=cfg.isCategoryEnabled.value, parent=self,
        )
        self.fileAssocCard = OptionCard(
            FluentIcon.DOCUMENT, self.tr("关联文件类型"),
            self.tr("双击 .torrent 等文件时自动用 Ghost Downloader 打开"),
            isChecked=self._isFileAssociationEnabled(), parent=self,
        )
        self.urlSchemeCard = OptionCard(
            FluentIcon.LINK, self.tr("注册 URL 协议"),
            self.tr("允许网页通过 ghostdownloader:// 链接唤起本应用"),
            isChecked=cfg.isUrlSchemeRegistered.value, parent=self,
        )
        self.aria2Card = OptionCard(
            FluentIcon.COMMAND_PROMPT, self.tr("Aria2 RPC 兼容"),
            self.tr("让支持 Aria2 的工具和网站把下载任务发给 Ghost Downloader"),
            isChecked=cfg.isAria2RpcEnabled.value, parent=self,
        )
        self.runAtLoginCard = OptionCard(
            FluentIcon.POWER_BUTTON, self.tr("开机自启"),
            self.tr("登录系统时自动在后台启动，随时接管下载"),
            isChecked=cfg.shouldRunAtLogin.value, parent=self,
        )
        self.clipboardCard = OptionCard(
            FluentIcon.PASTE, self.tr("剪贴板监听"),
            self.tr("复制下载链接时自动弹出新任务提示"),
            isChecked=cfg.isClipboardListenerEnabled.value, parent=self,
        )

    def _isFileAssociationEnabled(self) -> bool:
        return any(
            pack.config.associateFileTypes.value
            for pack in self._featureService.packs
            if pack.config is not None and hasattr(pack.config, "associateFileTypes")
        )

    def _initLayout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addStretch(1)

        listLayout = QVBoxLayout()
        listLayout.setSpacing(8)
        for card in [self.categoryCard, self.fileAssocCard, self.urlSchemeCard,
                     self.aria2Card, self.runAtLoginCard, self.clipboardCard]:
            listLayout.addWidget(card)
        layout.addLayout(listLayout)
        layout.addStretch(1)

    def save(self) -> None:
        cfg.set(cfg.isCategoryEnabled, self.categoryCard.isChecked())

        for pack in self._featureService.packs:
            config = pack.config
            if config is not None and hasattr(config, "associateFileTypes"):
                cfg.set(config.associateFileTypes, self.fileAssocCard.isChecked())

        if self.urlSchemeCard.isChecked() != cfg.isUrlSchemeRegistered.value:
            from app.platform.url_scheme import registerUrlScheme, unregisterUrlScheme
            if self.urlSchemeCard.isChecked():
                registerUrlScheme()
            else:
                unregisterUrlScheme()
            cfg.set(cfg.isUrlSchemeRegistered, self.urlSchemeCard.isChecked())

        cfg.set(cfg.isAria2RpcEnabled, self.aria2Card.isChecked())

        if self.runAtLoginCard.isChecked() != cfg.shouldRunAtLogin.value:
            from app.platform.run_at_login import setRunAtLogin
            setRunAtLogin(self.runAtLoginCard.isChecked())
            cfg.set(cfg.shouldRunAtLogin, self.runAtLoginCard.isChecked())

        cfg.set(cfg.isClipboardListenerEnabled, self.clipboardCard.isChecked())


class CompletePage(QWidget):

    finishClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.checkIcon = IconChip(FluentIcon.ACCEPT, SUCCESS_CHIP_COLORS, size=80, parent=self)

        self.titleLabel = TitleLabel(self.tr("一切就绪"), self)
        self.titleLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.descLabel = BodyLabel(
            self.tr("Ghost Downloader 已准备好为你工作。\n你可以随时在设置中调整所有选项。"),
            self,
        )
        self.descLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.descLabel.setWordWrap(True)

        self.finishButton = PrimaryPushButton(self.tr("开始使用"), self)
        self.finishButton.setFixedWidth(200)

    def _initLayout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)
        layout.addStretch(3)
        layout.addWidget(self.checkIcon, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(16)
        layout.addWidget(self.titleLabel)
        layout.addWidget(self.descLabel)
        layout.addSpacing(28)
        layout.addWidget(self.finishButton, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(4)

    def _bind(self) -> None:
        self.finishButton.clicked.connect(self.finishClicked)


class OobeWindow(FluentWidget):

    finished = Signal()

    PAGE_COUNT = 6

    def __init__(
        self,
        browserService: BrowserService,
        coroutineRunner: CoroutineRunner,
        featureService: FeatureService,
        taskService: TaskService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent=parent)
        self._browserService = browserService
        self._coroutineRunner = coroutineRunner
        self._featureService = featureService
        self._taskService = taskService
        self._currentIndex = 0
        self._isFinished = False
        self._queuedRuntimeIds: set[str] = set()
        self._translator = None
        self._initWidget()
        self._initContent()
        self._initLayout()
        self._bind()
        self._refreshNavigation()

    def _initWidget(self) -> None:
        from qfluentwidgets import MSFluentTitleBar
        self.setTitleBar(MSFluentTitleBar(self))
        self.setWindowTitle("Ghost Downloader")
        self.setWindowIcon(QIcon(":/image/logo.png"))
        self.titleBar.hBoxLayout.insertSpacing(2, 6)
        self.titleBar.maxBtn.hide()
        self.setFixedSize(WINDOW_SIZE)
        desktop = QApplication.primaryScreen().availableGeometry()
        self.move(desktop.center() - self.rect().center())

    def _initContent(self) -> None:
        self.welcomePage = WelcomePage(self)
        self.basicSettingsPage = BasicSettingsPage(self)
        self.browserExtensionPage = BrowserExtensionPage(
            self._browserService, self._coroutineRunner, self)
        self.runtimeInstallPage = RuntimeInstallPage(self._featureService, self)
        self.advancedOptionsPage = AdvancedOptionsPage(self._featureService, self)
        self.completePage = CompletePage(self)

        self.stackedWidget = DrillInTransitionStackedWidget(self)
        self.stackedWidget.addWidget(self.welcomePage)
        self.stackedWidget.addWidget(self.basicSettingsPage)
        self.stackedWidget.addWidget(self.browserExtensionPage)
        self.stackedWidget.addWidget(self.runtimeInstallPage)
        self.stackedWidget.addWidget(self.advancedOptionsPage)
        self.stackedWidget.addWidget(self.completePage)

        self.backButton = PushButton(self.tr("上一步"), self)
        self.skipButton = TransparentPushButton(self.tr("跳过全部"), self)
        self.nextButton = PrimaryPushButton(self.tr("下一步"), self)
        self.pipsPager = HorizontalPipsPager(self)
        self.pipsPager.setPageNumber(self.PAGE_COUNT)
        self.pipsPager.setVisibleNumber(self.PAGE_COUNT)
        self.pipsPager.setPreviousButtonDisplayMode(PipsScrollButtonDisplayMode.NEVER)
        self.pipsPager.setNextButtonDisplayMode(PipsScrollButtonDisplayMode.NEVER)
        self.pipsPager.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def _initLayout(self) -> None:
        mainLayout = QVBoxLayout(self)
        mainLayout.setContentsMargins(36, self.titleBar.height() + 8, 36, 16)
        mainLayout.setSpacing(0)
        mainLayout.addWidget(self.stackedWidget, 1)

        navLayout = QHBoxLayout()
        navLayout.setContentsMargins(0, 14, 0, 0)

        leftBox = QHBoxLayout()
        leftBox.addWidget(self.skipButton)
        leftBox.addWidget(self.backButton)
        leftBox.addStretch()

        rightBox = QHBoxLayout()
        rightBox.addStretch()
        rightBox.addWidget(self.nextButton)

        navLayout.addLayout(leftBox, 1)
        navLayout.addWidget(self.pipsPager)
        navLayout.addLayout(rightBox, 1)
        mainLayout.addLayout(navLayout)

    def _bind(self) -> None:
        self.welcomePage.startClicked.connect(self._onNextClicked)
        self.basicSettingsPage.languageChanged.connect(self._onLanguageChanged)
        self.completePage.finishClicked.connect(self._finish)
        self.backButton.clicked.connect(self._onBackClicked)
        self.nextButton.clicked.connect(self._onNextClicked)
        self.skipButton.clicked.connect(self._finish)

    def onPairRequested(self, request: dict) -> None:
        self.browserExtensionPage.onPairRequested(request)

    def _onLanguageChanged(self) -> None:
        # 延迟到信号栈外重建：发出信号的下拉框会随内容区一起销毁
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._reloadLanguage)

    def _reloadLanguage(self) -> None:
        from PySide6.QtCore import QTranslator
        application = QApplication.instance()
        if self._translator is not None:
            application.removeTranslator(self._translator)
        self._translator = QTranslator(application)
        self._translator.load(cfg.language.value.value, "gd3", ".", ":/i18n")
        application.installTranslator(self._translator)
        self._rebuildContent()

    def _rebuildContent(self) -> None:
        index = self._currentIndex
        for widget in [self.stackedWidget, self.backButton,
                       self.skipButton, self.nextButton, self.pipsPager]:
            widget.hide()
            widget.deleteLater()
        QWidget().setLayout(self.layout())

        self._initContent()
        self._initLayout()
        self._bind()
        self._currentIndex = index
        self.stackedWidget.setAnimationEnabled(False)
        self.stackedWidget.setCurrentIndex(index)
        self.stackedWidget.setAnimationEnabled(True)
        self._refreshNavigation()

    def _refreshNavigation(self) -> None:
        i = self._currentIndex
        isFirst = i == 0
        isLast = i == self.PAGE_COUNT - 1

        self.backButton.setVisible(not isFirst and not isLast)
        self.nextButton.setVisible(not isFirst and not isLast)
        self.skipButton.setVisible(isFirst)
        self.pipsPager.setCurrentIndex(i)

    def _onNextClicked(self) -> None:
        if self._currentIndex >= self.PAGE_COUNT - 1:
            return

        if self._currentIndex == 3:
            self._installSelectedRuntimes()
        if self._currentIndex == 4:
            self.advancedOptionsPage.save()

        self._currentIndex += 1
        self.stackedWidget.setCurrentIndex(self._currentIndex)
        self._refreshNavigation()
        if self._currentIndex == 2:
            self.browserExtensionPage.refreshPortStatus()
        elif self._currentIndex == 3:
            self.runtimeInstallPage.mount()

    def _onBackClicked(self) -> None:
        if self._currentIndex <= 0:
            return
        self._currentIndex -= 1
        self.stackedWidget.setCurrentIndex(self._currentIndex, isBack=True)
        self._refreshNavigation()

    def _installSelectedRuntimes(self) -> None:
        runtimes = self.runtimeInstallPage.selectedRuntimes()
        if not runtimes:
            return

        from loguru import logger

        _taskService = self._taskService

        def onDone(task, name):
            _taskService.add(task)

        def onFailed(error, name):
            logger.error("OOBE 安装 {} 失败: {}", name, error)

        for runtime in runtimes:
            if runtime.path() or runtime.runtimeId in self._queuedRuntimeIds:
                continue
            self._queuedRuntimeIds.add(runtime.runtimeId)
            self._coroutineRunner.submit(
                runtime.installTask(),
                done=onDone,
                failed=onFailed,
                name=runtime.name,
            )

    def _finish(self) -> None:
        if self._isFinished:
            return
        self._isFinished = True
        cfg.set(cfg.hasCompletedOobe, True)
        self.finished.emit()
        self.close()

    def closeEvent(self, event) -> None:
        # 用户直接关窗视为"跳过全部"
        if not self._isFinished:
            self._isFinished = True
            cfg.set(cfg.hasCompletedOobe, True)
            self.finished.emit()
        super().closeEvent(event)
