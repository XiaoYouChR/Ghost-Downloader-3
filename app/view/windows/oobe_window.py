from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QRectF, QSize, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QMovie, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel,
    QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    BodyLabel, CaptionLabel, CardWidget, CheckBox, ComboBox,
    DrillInTransitionStackedWidget, FluentIcon, FluentWidget,
    GroupHeaderCardWidget, HorizontalPipsPager, InfoBar, InfoBarIcon,
    InfoBarPosition, PipsScrollButtonDisplayMode, PrimaryPushButton,
    PushButton, SubtitleLabel, SwitchButton, Theme, TitleLabel,
    TransparentPushButton, isDarkTheme, themeColor,
)

from app.config.cfg import cfg, Language
from app.config.constants import (
    CHROME_WEBSTORE_URL, EDGE_ADDONS_URL, FIREFOX_ADDONS_URL,
)

if TYPE_CHECKING:
    from app.models.pack import BinaryRuntime

WINDOW_SIZE = QSize(960, 600)
PREVIEW_GIF = ":/res/install_chrome_extension_guidance.webp"
# 960 - 边距 36*2 - 右栏 280 - 间距 16 = 592，按 16:9 取整
PREVIEW_SIZE = QSize(592, 333)
STORE_COLUMN_WIDTH = 280

# 以运行时类名为键，避免依赖 Pack 的模块导入路径
# colors: (lightBg, lightFg, darkBg, darkFg)
RUNTIME_PROFILES = {
    "FFmpegRuntime": {
        "title": "视频合并",
        "description": "哔哩哔哩、YouTube 等网站视频下载必备，合并音视频轨道为完整文件",
        "icon": FluentIcon.VIDEO,
        "colors": ("#E8DCFF", "#7B61FF", "#3D2E6B", "#B49AFF"),
        "defaultChecked": True,
        "order": 0,
    },
    "M3U8Runtime": {
        "title": "M3U8 / 直播下载",
        "description": "支持 HLS、DASH 等流媒体协议，可录制直播流",
        "icon": FluentIcon.MEDIA,
        "colors": ("#D4F0FF", "#0078D4", "#1A3548", "#4CC2FF"),
        "defaultChecked": True,
        "order": 1,
    },
    "YouTubeRuntime": {
        "title": "YouTube 下载",
        "description": "支持 YouTube、Twitter 等数百个视频网站",
        "icon": FluentIcon.GLOBE,
        "colors": ("#FFE0E0", "#E53935", "#4A2020", "#FF6B6B"),
        "defaultChecked": True,
        "order": 2,
    },
    "ED2kRuntime": {
        "title": "eD2k / eMule",
        "description": "支持电驴协议，适合下载经典资源",
        "icon": FluentIcon.BOOK_SHELF,
        "colors": ("#E0F0E0", "#2E7D32", "#1A3A1A", "#66BB6A"),
        "defaultChecked": False,
        "order": 3,
    },
}


# ─── Reusable widgets ───────────────────────────────────────────────


class IconChip(QWidget):
    """圆角底色图标块，深浅主题各一套配色"""

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
        try:
            self._icon.render(painter, iconRect, fill=fg)
        except TypeError:
            self._icon.render(painter, iconRect)


NEUTRAL_CHIP_COLORS = ("#EFEFEF", "#666666", "#3D3D3D", "#AAAAAA")


class ThemePreview(QWidget):
    """迷你窗口缩略图：假标题栏 + 内容条 + 强调色块。mode: light / dark / auto"""

    def __init__(self, mode: str, parent=None):
        super().__init__(parent)
        self._mode = mode
        self.setFixedHeight(96)

    def _drawMini(self, painter: QPainter, rect: QRectF, dark: bool) -> None:
        bg = QColor("#232323") if dark else QColor("#F5F7FA")
        titleBar = QColor("#2E2E2E") if dark else QColor("#E9EDF2")
        bar = QColor("#333333") if dark else QColor("#FFFFFF")

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
            leftRect = QRectF(outer.x(), outer.y(), half, outer.height())
            rightRect = QRectF(outer.x() + half, outer.y(), half, outer.height())
            self._drawMini(painter, leftRect, dark=False)
            self._drawMini(painter, rightRect, dark=True)
        else:
            self._drawMini(painter, outer, dark=self._mode == "dark")

        painter.setClipping(False)
        painter.setPen(QPen(QColor(128, 128, 128, 60), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(outer.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)


class ThemeCard(CardWidget):
    """主题选择卡片，选中时描主题色边框"""

    def __init__(self, theme: Theme, label: str, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._isSelected = False
        self.setClickEnabled(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(10)

        mode = {Theme.LIGHT: "light", Theme.DARK: "dark"}.get(theme, "auto")
        layout.addWidget(ThemePreview(mode, self))

        label_ = BodyLabel(label, self)
        label_.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label_)

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
    """可点击操作卡片：图标 + 标题（+ 可换行说明），推荐样式带描边和右侧徽章"""

    def __init__(self, icon: FluentIcon, title: str, hint: str = "",
                 isRecommended: bool = False, parent=None):
        super().__init__(parent)
        self._isRecommended = isRecommended
        self.setClickEnabled(True)
        if hint:
            self.setMinimumHeight(80)  # 说明文字换行时自然增高，避免裁字
        else:
            self.setFixedHeight(48)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(12)

        layout.addWidget(IconChip(icon, NEUTRAL_CHIP_COLORS, size=30, parent=self))

        textCol = QVBoxLayout()
        textCol.setSpacing(2)
        textCol.addWidget(BodyLabel(title, self))
        if hint:
            hintLabel = CaptionLabel(hint, self)
            hintLabel.setTextColor(Qt.GlobalColor.gray, Qt.GlobalColor.gray)
            hintLabel.setWordWrap(True)
            textCol.addWidget(hintLabel)
        layout.addLayout(textCol, 1)

        chevron = IconChip(FluentIcon.CHEVRON_RIGHT_MED,
                           ("#00000000", "#999999", "#00000000", "#777777"),
                           size=16, parent=self)
        layout.addWidget(chevron)

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
    """推荐设置卡片：图标 + 标题 + 说明 + 开关"""

    def __init__(self, icon: FluentIcon, title: str, desc: str,
                 isChecked: bool = False, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 8, 18, 8)
        layout.setSpacing(14)

        layout.addWidget(IconChip(icon, NEUTRAL_CHIP_COLORS, size=34, parent=self))

        textCol = QVBoxLayout()
        textCol.setSpacing(0)
        textCol.addWidget(BodyLabel(title, self))
        descLabel = CaptionLabel(desc, self)
        descLabel.setTextColor(Qt.GlobalColor.gray, Qt.GlobalColor.gray)
        textCol.addWidget(descLabel)
        layout.addLayout(textCol, 1)

        self.switch = SwitchButton(self)
        self.switch.setOnText("")
        self.switch.setOffText("")
        self.switch.setChecked(isChecked)
        layout.addWidget(self.switch)

    def isChecked(self) -> bool:
        return self.switch.isChecked()


# ─── Individual Pages ──────────────────────────────────────────────


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
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        iconLabel = QLabel(self)
        iconLabel.setPixmap(QIcon(":/image/logo.png").pixmap(88, 88))
        iconLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        titleLabel = TitleLabel(self.tr("欢迎使用 Ghost Downloader"), self)
        titleLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitleLabel = BodyLabel(
            self.tr("快速、智能的下载管理器。\n接下来的几步将帮助你完成基本配置。"), self
        )
        subtitleLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitleLabel.setWordWrap(True)

        startButton = PrimaryPushButton(self.tr("开始配置"), self)
        startButton.setFixedWidth(200)
        startButton.clicked.connect(self.startClicked)

        layout.addStretch(3)
        layout.addWidget(iconLabel, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(16)
        layout.addWidget(titleLabel)
        layout.addWidget(subtitleLabel)
        layout.addSpacing(28)
        layout.addWidget(startButton, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(4)


class BasicSettingsPage(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(PageHeader(
            self.tr("基本设置"),
            self.tr("选择你喜欢的外观，设置下载文件的保存位置"), self,
        ))

        layout.addStretch(1)

        # Theme cards
        themeRow = QHBoxLayout()
        themeRow.setSpacing(14)
        self._themeCards: list[ThemeCard] = []
        for theme, label in [(Theme.LIGHT, self.tr("浅色")),
                              (Theme.DARK, self.tr("深色")),
                              (Theme.AUTO, self.tr("跟随系统"))]:
            card = ThemeCard(theme, label, self)
            card.clicked.connect(lambda t=theme: self._onThemePicked(t))
            themeRow.addWidget(card)
            self._themeCards.append(card)
        self._syncThemeCards()
        layout.addLayout(themeRow)

        layout.addStretch(1)

        # Language + download folder
        settingsCard = GroupHeaderCardWidget(self.tr("偏好"), self)

        self.langCombo = ComboBox(self)
        self.langCombo.setMinimumWidth(200)
        for lang in Language:
            if lang == Language.AUTO:
                self.langCombo.addItem(self.tr("跟随系统"))
            else:
                self.langCombo.addItem(lang.value.nativeLanguageName())
        self.langCombo.setCurrentIndex(list(Language).index(cfg.language.value))
        self.langCombo.currentIndexChanged.connect(self._onLanguageChanged)
        settingsCard.addGroup(
            FluentIcon.LANGUAGE, self.tr("界面语言"),
            self.tr("重启后生效"), self.langCombo,
        )

        browseButton = PushButton(self.tr("浏览..."), self)
        browseButton.clicked.connect(self._onBrowseFolder)
        self._folderGroup = settingsCard.addGroup(
            FluentIcon.FOLDER, self.tr("下载保存位置"),
            str(cfg.downloadFolder.value), browseButton,
        )

        layout.addWidget(settingsCard)
        layout.addStretch(1)

    def _onThemePicked(self, theme: Theme) -> None:
        cfg.set(cfg.themeMode, theme)
        self._syncThemeCards()

    def _syncThemeCards(self) -> None:
        current = cfg.themeMode.value
        for card in self._themeCards:
            card.setSelected(card.theme == current)

    def _onLanguageChanged(self, index: int) -> None:
        languages = list(Language)
        if 0 <= index < len(languages):
            cfg.set(cfg.language, languages[index])

    def _onBrowseFolder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, self.tr("选择下载目录"), str(cfg.downloadFolder.value)
        )
        if folder:
            cfg.set(cfg.downloadFolder, folder)
            if hasattr(self._folderGroup, "setContent"):
                self._folderGroup.setContent(folder)


class BrowserExtensionPage(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._isPaired = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(PageHeader(
            self.tr("安装浏览器扩展"),
            self.tr("让浏览器中的下载自动接管到 Ghost Downloader"), self,
        ))

        layout.addStretch(1)

        contentLayout = QHBoxLayout()
        contentLayout.setSpacing(16)

        # Left: WebP tutorial + status banner
        leftLayout = QVBoxLayout()
        leftLayout.setSpacing(10)
        self.previewLabel = QLabel(self)
        self.previewLabel.setFixedSize(PREVIEW_SIZE)
        self.previewLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._initPreview()
        leftLayout.addWidget(self.previewLabel)

        self._banner: InfoBar | None = None
        self._bannerSlot = QVBoxLayout()
        self._bannerSlot.setContentsMargins(0, 0, 0, 0)
        leftLayout.addLayout(self._bannerSlot)
        contentLayout.addLayout(leftLayout)

        # Right: install channels, manual install first (recommended)
        rightWidget = QWidget(self)
        rightWidget.setFixedWidth(STORE_COLUMN_WIDTH)
        rightLayout = QVBoxLayout(rightWidget)
        rightLayout.setContentsMargins(0, 0, 0, 0)
        rightLayout.setSpacing(10)
        rightLayout.addStretch(1)

        manualCard = ActionCard(
            FluentIcon.DOWNLOAD, self.tr("手动安装"),
            self.tr("随桌面端自动更新，适用于所有 Chromium 浏览器"),
            isRecommended=True, parent=self,
        )
        manualCard.clicked.connect(self._onManualInstall)
        rightLayout.addWidget(manualCard)

        for title, url in [
            (self.tr("Chrome 商店"), CHROME_WEBSTORE_URL),
            (self.tr("Edge 商店"), EDGE_ADDONS_URL),
            (self.tr("Firefox 商店"), FIREFOX_ADDONS_URL),
        ]:
            card = ActionCard(FluentIcon.GLOBE, title, parent=self)
            card.clicked.connect(lambda u=url: QDesktopServices.openUrl(QUrl(u)))
            rightLayout.addWidget(card)

        footnote = CaptionLabel(self.tr("商店版更新需等待审核，可能滞后于桌面端"), self)
        footnote.setTextColor(Qt.GlobalColor.gray, Qt.GlobalColor.gray)
        rightLayout.addWidget(footnote)
        rightLayout.addStretch(1)

        contentLayout.addWidget(rightWidget)
        layout.addLayout(contentLayout)
        layout.addStretch(1)

    def _initPreview(self) -> None:
        movie = QMovie(PREVIEW_GIF, parent=self)
        if movie.isValid():
            movie.setScaledSize(PREVIEW_SIZE)
            self.previewLabel.setMovie(movie)
            movie.start()
            return

        self.previewLabel.setText(self.tr("安装教程动图"))
        if isDarkTheme():
            bg, fg = "rgba(255,255,255,0.06)", "rgba(255,255,255,0.5)"
        else:
            bg, fg = "rgba(0,0,0,0.04)", "rgba(0,0,0,0.4)"
        self.previewLabel.setStyleSheet(
            f"QLabel {{ background: {bg}; color: {fg}; border-radius: 8px; }}"
        )

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
        from app.services.browser_service import browserService
        if browserService.boundPort:
            self._setBanner(
                InfoBarIcon.INFORMATION,
                self.tr("正在端口 {} 上等待扩展连接").format(browserService.boundPort),
            )
        else:
            self._setBanner(
                InfoBarIcon.WARNING,
                self.tr("端口 {} 被占用，请在设置中更换端口").format(
                    cfg.browserExtensionPort.value
                ),
            )

    def _onManualInstall(self) -> None:
        from app.services.browser_service import extractBrowserExtension
        from app.services.coroutine_runner import coroutineRunner
        coroutineRunner.submit(
            extractBrowserExtension(),
            done=self._onExtracted,
            failed=self._onExtractFailed,
            owner=self,
        )

    def _onExtracted(self, path: Path) -> None:
        from app.platform.desktop import openChromiumUrl, revealInFolder
        revealInFolder(str(path))
        if not openChromiumUrl("chrome://extensions"):
            QApplication.clipboard().setText("chrome://extensions")
            InfoBar.info(
                self.tr("请手动打开浏览器"),
                self.tr("chrome://extensions 已复制到剪贴板"),
                duration=5000, position=InfoBarPosition.TOP, parent=self,
            )

    def _onExtractFailed(self, error) -> None:
        InfoBar.error(
            self.tr("解包失败"), str(error),
            duration=5000, position=InfoBarPosition.TOP, parent=self,
        )

    def onPairRequested(self, request: dict) -> None:
        from app.services.browser_service import browserService
        browserService.approvePair(request["session"], request["requestId"])
        self._isPaired = True
        version = request.get("extensionVersion", "")
        if version:
            text = self.tr("已连接扩展 v{}").format(version)
        else:
            text = self.tr("配对成功")
        self._setBanner(InfoBarIcon.SUCCESS, text)

    def onProtocolMismatch(self) -> None:
        self._setBanner(
            InfoBarIcon.WARNING,
            self.tr("协议版本不匹配，商店版可能滞后，请尝试手动安装"),
        )


class RuntimeInstallPage(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checkBoxes: list[tuple[CheckBox, BinaryRuntime]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(PageHeader(
            self.tr("安装推荐组件"),
            self.tr("点击下一步将自动安装勾选的组件，稍后可在设置中管理"), self,
        ))

        layout.addStretch(1)
        self._card = GroupHeaderCardWidget(self.tr("推荐组件"), self)
        layout.addWidget(self._card)
        layout.addStretch(1)

    def populate(self) -> None:
        if self._checkBoxes:
            return

        from app.services.feature_service import featureService
        entries = []
        for runtime in featureService.runtimes():
            profile = RUNTIME_PROFILES.get(type(runtime).__name__)
            if profile and runtime.canInstall:
                entries.append((runtime, profile))
        entries.sort(key=lambda x: x[1]["order"])

        for runtime, profile in entries:
            trailing = QWidget(self)
            trailingLayout = QHBoxLayout(trailing)
            trailingLayout.setContentsMargins(0, 0, 0, 0)
            trailingLayout.setSpacing(12)

            tag = CaptionLabel(runtime.name, trailing)
            tag.setTextColor(Qt.GlobalColor.gray, Qt.GlobalColor.gray)

            checkBox = CheckBox(trailing)
            checkBox.setChecked(profile["defaultChecked"])

            trailingLayout.addWidget(tag)
            trailingLayout.addWidget(checkBox)

            self._card.addGroup(
                profile["icon"], self.tr(profile["title"]),
                self.tr(profile["description"]), trailing,
            )
            self._checkBoxes.append((checkBox, runtime))

    def selectedRuntimes(self) -> list[BinaryRuntime]:
        return [rt for cb, rt in self._checkBoxes if cb.isChecked()]


class AdvancedOptionsPage(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(PageHeader(
            self.tr("更多选项"),
            self.tr("按需开启以下功能，也可以稍后在设置中修改"), self,
        ))

        layout.addStretch(1)

        listLayout = QVBoxLayout()
        listLayout.setSpacing(10)

        self.fileAssocCard = OptionCard(
            FluentIcon.DOCUMENT, self.tr("关联文件类型"),
            self.tr("双击 .torrent 等文件时自动用 Ghost Downloader 打开"),
            isChecked=False, parent=self,
        )
        self.urlSchemeCard = OptionCard(
            FluentIcon.LINK, self.tr("注册 URL 协议"),
            self.tr("允许网页通过 ghostdownloader:// 链接唤起本应用"),
            isChecked=False, parent=self,
        )
        self.aria2Card = OptionCard(
            FluentIcon.COMMAND_PROMPT, self.tr("Aria2 RPC 兼容"),
            self.tr("让支持 Aria2 的工具和网站把下载任务发给 Ghost Downloader"),
            isChecked=False, parent=self,
        )
        self.runAtLoginCard = OptionCard(
            FluentIcon.POWER_BUTTON, self.tr("开机自启"),
            self.tr("登录系统时自动在后台启动，随时接管下载"),
            isChecked=False, parent=self,
        )
        self.clipboardCard = OptionCard(
            FluentIcon.PASTE, self.tr("剪贴板监听"),
            self.tr("复制下载链接时自动弹出新任务提示"),
            isChecked=cfg.isClipboardListenerEnabled.value, parent=self,
        )

        for card in [self.fileAssocCard, self.urlSchemeCard, self.aria2Card,
                     self.runAtLoginCard, self.clipboardCard]:
            listLayout.addWidget(card)

        layout.addLayout(listLayout)
        layout.addStretch(1)

    def applySettings(self) -> None:
        if self.fileAssocCard.isChecked():
            from app.services.feature_service import featureService
            for pack in featureService.packs:
                config = pack.config
                if config is not None and hasattr(config, "associateFileTypes"):
                    cfg.set(config.associateFileTypes, True)
        if self.urlSchemeCard.isChecked():
            cfg.set(cfg.isUrlSchemeRegistered, True)
            from app.platform.url_scheme import registerUrlScheme
            registerUrlScheme()
        if self.aria2Card.isChecked():
            cfg.set(cfg.isAria2RpcEnabled, True)
        if self.runAtLoginCard.isChecked():
            cfg.set(cfg.shouldRunAtLogin, True)
            from app.platform.run_at_login import setRunAtLogin
            setRunAtLogin(True)
        cfg.set(cfg.isClipboardListenerEnabled, self.clipboardCard.isChecked())


class CompletePage(QWidget):

    finishClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        checkIcon = IconChip(
            FluentIcon.ACCEPT,
            ("#E8F5E9", "#0F7B46", "#1A3A1A", "#4ADE80"),
            size=80, parent=self,
        )

        titleLabel = TitleLabel(self.tr("一切就绪"), self)
        titleLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        descLabel = BodyLabel(
            self.tr("Ghost Downloader 已准备好为你工作。\n你可以随时在设置中调整所有选项。"),
            self,
        )
        descLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        descLabel.setWordWrap(True)

        finishButton = PrimaryPushButton(self.tr("开始使用"), self)
        finishButton.setFixedWidth(200)
        finishButton.clicked.connect(self.finishClicked)

        layout.addStretch(3)
        layout.addWidget(checkIcon, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(16)
        layout.addWidget(titleLabel)
        layout.addWidget(descLabel)
        layout.addSpacing(28)
        layout.addWidget(finishButton, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(4)


# ─── OOBE Window ────────────────────────────────────────────────────


class OobeWindow(FluentWidget):

    finished = Signal()

    PAGE_COUNT = 6

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        from qfluentwidgets import MSFluentTitleBar
        self.setTitleBar(MSFluentTitleBar(self))
        self.setWindowTitle("Ghost Downloader")
        self.setWindowIcon(QIcon(":/image/logo.png"))

        self._currentIndex = 0
        self._isFinished = False

        # Pages
        self.welcomePage = WelcomePage(self)
        self.basicSettingsPage = BasicSettingsPage(self)
        self.browserExtensionPage = BrowserExtensionPage(self)
        self.runtimeInstallPage = RuntimeInstallPage(self)
        self.advancedOptionsPage = AdvancedOptionsPage(self)
        self.completePage = CompletePage(self)

        self.stackedWidget = DrillInTransitionStackedWidget(self)
        self.stackedWidget.addWidget(self.welcomePage)
        self.stackedWidget.addWidget(self.basicSettingsPage)
        self.stackedWidget.addWidget(self.browserExtensionPage)
        self.stackedWidget.addWidget(self.runtimeInstallPage)
        self.stackedWidget.addWidget(self.advancedOptionsPage)
        self.stackedWidget.addWidget(self.completePage)

        # Bottom bar
        self.backButton = PushButton(self.tr("上一步"), self)
        self.skipButton = TransparentPushButton(self.tr("跳过全部"), self)
        self.nextButton = PrimaryPushButton(self.tr("下一步"), self)
        self.pipsPager = HorizontalPipsPager(self)
        self.pipsPager.setPageNumber(self.PAGE_COUNT)
        self.pipsPager.setVisibleNumber(self.PAGE_COUNT)
        self.pipsPager.setPreviousButtonDisplayMode(PipsScrollButtonDisplayMode.NEVER)
        self.pipsPager.setNextButtonDisplayMode(PipsScrollButtonDisplayMode.NEVER)
        self.pipsPager.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._initWindow()
        self._initLayout()
        self._bind()
        self._syncNavigation()

    def _initWindow(self) -> None:
        self.titleBar.hBoxLayout.insertSpacing(2, 6)
        self.titleBar.maxBtn.hide()
        self.setFixedSize(WINDOW_SIZE)
        desktop = QApplication.primaryScreen().availableGeometry()
        self.move(desktop.center() - self.rect().center())

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
        self.welcomePage.startClicked.connect(self._goNext)
        self.completePage.finishClicked.connect(self._finish)
        self.backButton.clicked.connect(self._goBack)
        self.nextButton.clicked.connect(self._goNext)
        self.skipButton.clicked.connect(self._finish)

    def _syncNavigation(self) -> None:
        i = self._currentIndex
        isFirst = i == 0
        isLast = i == self.PAGE_COUNT - 1

        self.backButton.setVisible(not isFirst and not isLast)
        self.nextButton.setVisible(not isFirst and not isLast)
        self.skipButton.setVisible(isFirst)
        self.pipsPager.setCurrentIndex(i)

    def _goNext(self) -> None:
        if self._currentIndex >= self.PAGE_COUNT - 1:
            return

        if self._currentIndex == 3:
            self._installSelectedRuntimes()
        if self._currentIndex == 4:
            self.advancedOptionsPage.applySettings()

        self._currentIndex += 1
        self.stackedWidget.setCurrentIndex(self._currentIndex)
        self._syncNavigation()
        self._onPageEntered(self._currentIndex)

    def _goBack(self) -> None:
        if self._currentIndex <= 0:
            return
        self._currentIndex -= 1
        self.stackedWidget.setCurrentIndex(self._currentIndex, isBack=True)
        self._syncNavigation()

    def _onPageEntered(self, index: int) -> None:
        if index == 2:
            self.browserExtensionPage.refreshPortStatus()
        elif index == 3:
            self.runtimeInstallPage.populate()

    def _installSelectedRuntimes(self) -> None:
        runtimes = self.runtimeInstallPage.selectedRuntimes()
        if not runtimes:
            return

        from loguru import logger
        from app.services.task_service import taskService
        from app.services.coroutine_runner import coroutineRunner

        def onDone(task, name):
            taskService.add(task)

        def onFailed(error, name):
            logger.error("OOBE 安装 {} 失败: {}", name, error)

        for runtime in runtimes:
            if runtime.path():
                continue
            coroutineRunner.submit(
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
