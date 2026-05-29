from io import BytesIO
from typing import TYPE_CHECKING

import qrcode
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    MessageBoxBase,
    SubtitleLabel,
    PlainTextEdit,
    ConfigValidator,
    OptionsConfigItem,
    OptionsValidator,
    BoolValidator,
    ConfigItem,
    ComboBoxSettingCard,
    SettingCard,
    FluentIcon,
    SwitchSettingCard,
    BodyLabel,
    CaptionLabel,
    PushButton,
    PrimaryPushButton,
    PixmapLabel,
)
from qrcode.image.pure import PyPNGImage

from app.bases.models import PackConfig
from app.services.core_service import coreService
from app.supports.config import cfg
from app.view.components.setting_card_group import CollapsibleSettingCardGroup
from .login import (
    _QR_UNSCANNED,
    _QR_SCANNED,
    _QR_EXPIRED,
    _toCookie,
    requestQrCode,
    pollQrLogin,
    fetchLoginInfo,
    logout,
)

if TYPE_CHECKING:
    from app.view.pages.setting_page import SettingPage


def _createQrPixmap(content: str, size: int = 240) -> QPixmap:
    qrCode = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=2, box_size=10)
    qrCode.add_data(content)
    qrCode.make(fit=True)

    image = qrCode.make_image(image_factory=PyPNGImage, fill_color="black", back_color="white")
    buffer = BytesIO()
    image.save(buffer)

    pixmap = QPixmap()
    pixmap.loadFromData(buffer.getvalue(), "PNG")
    return pixmap.scaled(size, size)


class EditCookieDialog(MessageBoxBase):
    def __init__(self, parent=None, initialCookie: str = ""):
        super().__init__(parent=parent)
        self.setClosableOnMaskClicked(True)

        self.widget.setFixedSize(420, 500)
        self.yesButton.setText(self.tr("保存"))
        self.cancelButton.setText(self.tr("取消"))

        self.titleLabel = SubtitleLabel(self.tr("手动导入 Cookie"), self.widget)
        self.descriptionLabel = CaptionLabel(
            self.tr("请粘贴浏览器导出的完整 Cookie，留空后保存可清空当前 Cookie"),
            self.widget,
        )
        self.cookieTextEdit = PlainTextEdit(self.widget)
        self.cookieTextEdit.setPlaceholderText(self.tr("请在此输入用户 Cookie"))
        self.cookieTextEdit.setPlainText(initialCookie or "")

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.descriptionLabel)
        self.viewLayout.addWidget(self.cookieTextEdit)


class ScanLoginDialog(MessageBoxBase):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.cookie = ""
        self._qrCodeKey = ""
        self._loginUrl = ""
        self._generation = 0
        self._generating = False
        self._closed = False

        self.setClosableOnMaskClicked(True)
        self.widget.setFixedSize(430, 560)
        self.yesButton.hide()
        self.cancelButton.setText(self.tr("关闭"))

        self.titleLabel = SubtitleLabel(self.tr("扫码登录"), self.widget)
        self.descriptionLabel = CaptionLabel(
            self.tr("使用哔哩哔哩手机客户端扫描下方二维码，并在手机端确认登录"),
            self.widget,
        )
        self.qrPixmapLabel = PixmapLabel(self.widget)
        self.qrPixmapLabel.setFixedSize(240, 240)
        self.qrPixmapLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qrPixmapLabel.setScaledContents(True)

        self.statusLabel = BodyLabel(self.tr("正在获取二维码..."), self.widget)
        self.statusLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.statusLabel.setWordWrap(True)

        self.tipLabel = CaptionLabel(
            self.tr('二维码有效期约 180 秒，失效后可点击"刷新二维码"重新生成'),
            self.widget,
        )
        self.tipLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tipLabel.setWordWrap(True)

        self.buttonContainer = QVBoxLayout()
        self.buttonContainer.setContentsMargins(0, 0, 0, 0)
        self.buttonContainer.setSpacing(10)

        self.actionLayout = QHBoxLayout()
        self.actionLayout.setContentsMargins(0, 0, 0, 0)
        self.actionLayout.setSpacing(12)

        self.refreshButton = PrimaryPushButton(FluentIcon.SYNC, self.tr("刷新二维码"), self.widget)
        self.openBrowserButton = PushButton(FluentIcon.LINK, self.tr("打开登录链接"), self.widget)
        self.openBrowserButton.setEnabled(False)

        self.actionLayout.addWidget(self.refreshButton)
        self.actionLayout.addWidget(self.openBrowserButton)
        self.buttonContainer.addLayout(self.actionLayout)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.descriptionLabel)
        self.viewLayout.addSpacing(12)
        self.viewLayout.addWidget(self.qrPixmapLabel, 0, Qt.AlignmentFlag.AlignCenter)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.statusLabel)
        self.viewLayout.addWidget(self.tipLabel)
        self.viewLayout.addSpacing(6)
        self.viewLayout.addLayout(self.buttonContainer)

        self.refreshButton.clicked.connect(self.reloadQrCode)
        self.openBrowserButton.clicked.connect(self._openLoginUrl)

        self.reloadQrCode()

    def done(self, code):
        self._closed = True
        super().done(code)

    def reloadQrCode(self):
        if self._closed or self._generating:
            return

        self._generation += 1
        self._generating = True
        self.cookie = ""
        self._qrCodeKey = ""
        self._loginUrl = ""
        self.openBrowserButton.setEnabled(False)
        self.qrPixmapLabel.setPixmap(QPixmap())
        self.statusLabel.setText(self.tr("正在获取二维码..."))

        generation = self._generation
        coreService.runCoroutine(
            requestQrCode(),
            lambda result, error: self._onQrCodeGenerated(generation, result, error),
        )

    def _onQrCodeGenerated(self, generation: int, result: dict | None, error: str | None):
        if self._closed or generation != self._generation:
            return

        self._generating = False
        self.refreshButton.setEnabled(True)

        if error:
            self.statusLabel.setText(self.tr(f"二维码获取失败：{error}"))
            return

        self._loginUrl = str((result or {}).get("url") or "").strip()
        self._qrCodeKey = str((result or {}).get("qrcode_key") or "").strip()
        if not self._loginUrl or not self._qrCodeKey:
            self.statusLabel.setText(self.tr("二维码获取失败：接口未返回有效的登录地址"))
            return

        try:
            self.qrPixmapLabel.setPixmap(_createQrPixmap(self._loginUrl))
        except Exception as e:
            self.statusLabel.setText(self.tr(f"二维码生成失败：{e}"))
            raise

        self.openBrowserButton.setEnabled(True)
        self.statusLabel.setText(self.tr("等待扫码并在手机端确认登录"))
        generation = self._generation
        coreService.runCoroutine(
            pollQrLogin(
                self._qrCodeKey,
                lambda statusCode, statusMessage: self._onLoginPollingStatus(generation, statusCode, statusMessage),
                lambda: self._closed or generation != self._generation,
            ),
            lambda result, error: self._onLoginPolled(generation, result, error),
        )

    def _onLoginPollingStatus(self, generation: int, statusCode: int, statusMessage: str):
        if self._closed or generation != self._generation:
            return

        if statusCode == _QR_UNSCANNED:
            self.statusLabel.setText(self.tr("等待扫码"))
            return

        if statusCode == _QR_SCANNED:
            self.statusLabel.setText(self.tr("二维码已扫码，请在手机端确认登录"))
            return

        if statusMessage:
            self.statusLabel.setText(statusMessage)

    def _onLoginPolled(self, generation: int, result: dict | None, error: str | None):
        if self._closed or generation != self._generation:
            return

        if error:
            self.statusLabel.setText(self.tr('轮询扫码状态失败，请点击"刷新二维码"重试'))
            return

        payload = result or {}
        statusCode = int(payload.get("code", -1))
        statusMessage = str(payload.get("message") or "").strip()

        if statusCode == -1:
            return

        if statusCode == _QR_EXPIRED:
            self.statusLabel.setText(self.tr('二维码已失效，请点击"刷新二维码"重新生成'))
            return

        if statusCode == 0:
            self.cookie = str(payload.get("cookie") or "")
            if not self.cookie:
                self.statusLabel.setText(self.tr("登录成功，但未能提取到有效 Cookie"))
                return

            self.statusLabel.setText(self.tr("登录成功，正在导入 Cookie..."))
            self.accept()
            return

        self.statusLabel.setText(self.tr(statusMessage or f"未知扫码状态：{statusCode}"))

    def _openLoginUrl(self):
        if self._loginUrl:
            QDesktopServices.openUrl(QUrl(self._loginUrl))


class BilibiliLoginSettingCard(SettingCard):
    def __init__(self, userCookieItem: ConfigItem, parent=None):
        super().__init__(
            FluentIcon.VIEW,
            self.tr("账号登录"),
            "状态：未登录 用户名：- UID：- 会员状态：未开通",
            parent,
        )
        self.userCookieItem = userCookieItem
        self._infoGeneration = 0
        self._statusText = "未登录"
        self._uname = "-"
        self._mid = "-"
        self._vipText = "未开通"

        self.operationWidget = QWidget(self)
        self.operationLayout = QHBoxLayout(self.operationWidget)
        self.operationLayout.setContentsMargins(0, 0, 0, 0)
        self.operationLayout.setSpacing(8)

        self.scanLoginButton = PrimaryPushButton(self.tr("扫码登录"), self.operationWidget)
        self.editCookieButton = PushButton(self.tr("手动设置 Cookie"), self.operationWidget)
        self.logoutButton = PushButton(self.tr("退出登录"), self.operationWidget)

        self.operationLayout.addWidget(self.scanLoginButton)
        self.operationLayout.addWidget(self.editCookieButton)
        self.operationLayout.addWidget(self.logoutButton)

        self.hBoxLayout.addWidget(self.operationWidget, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.hBoxLayout.addSpacing(16)

        self.scanLoginButton.clicked.connect(self._onScanLogin)
        self.editCookieButton.clicked.connect(self._onEditCookie)
        self.logoutButton.clicked.connect(self._onLogout)

        self._syncButtonsEnabled()
        self.refreshLoginInfo()

    def _renderAccountInfo(self):
        self.setContent(
            f"状态：{self._statusText} "
            f"用户名：{self._uname} "
            f"UID：{self._mid} "
            f"会员状态：{self._vipText}"
        )

    def _syncButtonsEnabled(self, busy: bool = False):
        self.scanLoginButton.setEnabled(not busy)
        self.editCookieButton.setEnabled(not busy)
        self.logoutButton.setEnabled(not busy and bool(self.userCookieItem.value))

    def _setAccountInfo(self, status: str, uname: str | None = None, mid: str | None = None, vip: str | None = None):
        self._statusText = status
        if uname is not None:
            self._uname = uname
        if mid is not None:
            self._mid = mid
        if vip is not None:
            self._vipText = vip
        self._renderAccountInfo()

    def refreshLoginInfo(self):
        cookie = self.userCookieItem.value
        self._syncButtonsEnabled()
        if not cookie:
            self._setAccountInfo("未登录", "-", "-", "未开通")
            return

        self._setAccountInfo("正在获取账号信息...", "-", "-", "-")
        self._infoGeneration += 1
        generation = self._infoGeneration
        coreService.runCoroutine(
            fetchLoginInfo(cookie),
            lambda result, error: self._onLoginInfoLoaded(generation, result, error),
        )

    def _onLoginInfoLoaded(self, generation: int, result: dict | None, error: str | None):
        if generation != self._infoGeneration:
            return

        self._syncButtonsEnabled()
        if error:
            self._setAccountInfo("账号信息获取失败", "-", "-", "-")
            return

        payload = result or {}
        self._setAccountInfo(
            str(payload.get("status") or "未登录"),
            str(payload.get("uname") or "-"),
            str(payload.get("mid") or "-"),
            str(payload.get("vip") or "未开通"),
        )

    def _updateCookie(self, newCookie: str):
        normalizedCookie = _toCookie(newCookie)
        if not normalizedCookie:
            cfg.set(self.userCookieItem, "")
            self.refreshLoginInfo()
            return

        currentCookie = self.userCookieItem.value
        self._syncButtonsEnabled(True)
        if currentCookie and currentCookie != normalizedCookie:
            self._setAccountInfo("正在退出旧账号并导入新账号...", "-", "-", "-")
            coreService.runCoroutine(
                logout(currentCookie),
                lambda _result, _error: self._onCookieUpdated(normalizedCookie),
            )
        else:
            self._onCookieUpdated(normalizedCookie)

    def _onCookieUpdated(self, cookie: str):
        cfg.set(self.userCookieItem, cookie)
        self.refreshLoginInfo()

    def _onScanLogin(self):
        dialog = ScanLoginDialog(self.window())
        if dialog.exec():
            self._updateCookie(dialog.cookie)

    def _onEditCookie(self):
        dialog = EditCookieDialog(self.window(), self.userCookieItem.value)
        try:
            if dialog.exec():
                self._updateCookie(dialog.cookieTextEdit.toPlainText())
        finally:
            dialog.deleteLater()

    def _onLogout(self):
        cookie = self.userCookieItem.value
        if not cookie:
            self.refreshLoginInfo()
            return

        self._syncButtonsEnabled(True)
        self._setAccountInfo("正在退出登录...")
        coreService.runCoroutine(logout(cookie), self._onLoggedOut)

    def _onLoggedOut(self, result: dict | None, error: str | None):
        if error:
            self._syncButtonsEnabled()
            self._setAccountInfo("退出登录失败")
            return

        payload = result or {}
        if payload.get("clear_local"):
            cfg.set(self.userCookieItem, "")
        self.refreshLoginInfo()


class CookieValidator(ConfigValidator):
    def validate(self, value) -> bool:
        return isinstance(value, str)

    def correct(self, value) -> str:
        if not isinstance(value, str):
            return ""
        return _toCookie(value)


class BilibiliConfig(PackConfig):
    defaultQuality = OptionsConfigItem(
        "Download",
        "DefaultQuality",
        16,
        OptionsValidator([127, 120, 116, 112, 80, 74, 64, 32, 16]),
    )
    alternativeQuality = OptionsConfigItem("Download", "AlternativeQuality", "max", OptionsValidator(["max", "min"]))
    parseHDR = ConfigItem("Download", "ParseHDR", False, BoolValidator())
    parseDolby = ConfigItem("Download", "ParseDolby", False, BoolValidator())
    userCookie = ConfigItem("Download", "UserCookie", "", CookieValidator())

    def setupSettings(self, settingPage: "SettingPage"):
        self.parseBilibiliGroup = CollapsibleSettingCardGroup(self.tr("哔哩哔哩视频下载"), "bili", settingPage.container)

        self.defaultQualityCard = ComboBoxSettingCard(
            self.defaultQuality,
            FluentIcon.VIDEO,
            self.tr("默认清晰度"),
            self.tr("下载视频时默认的清晰度"),
            ["8K", "4K", "1080P60", "1080P+", "1080P", "720P60", "720P", "480P", "360P"],
            self.parseBilibiliGroup,
        )

        self.alternativeQualityCard = ComboBoxSettingCard(
            self.alternativeQuality,
            FluentIcon.VIDEO,
            self.tr("备选清晰度"),
            self.tr("下载视频时备选的清晰度"),
            [self.tr("可以下载的最高画质"), self.tr("可以下载的最低画质")],
            self.parseBilibiliGroup,
        )

        self.parseHDRCard = SwitchSettingCard(
            FluentIcon.VIDEO,
            self.tr("HDR"),
            self.tr("下载 HDR 视频"),
            self.parseHDR,
            self.parseBilibiliGroup,
        )

        self.parseDolbyCard = SwitchSettingCard(
            FluentIcon.VIDEO,
            self.tr("杜比视界"),
            self.tr("下载杜比视界视频"),
            self.parseDolby,
            self.parseBilibiliGroup,
        )

        self.loginCard = BilibiliLoginSettingCard(
            self.userCookie,
            self.parseBilibiliGroup,
        )

        self.parseBilibiliGroup.addSettingCard(self.defaultQualityCard)
        self.parseBilibiliGroup.addSettingCard(self.alternativeQualityCard)
        self.parseBilibiliGroup.addSettingCard(self.parseHDRCard)
        self.parseBilibiliGroup.addSettingCard(self.parseDolbyCard)
        self.parseBilibiliGroup.addSettingCard(self.loginCard)

        settingPage.addSettingGroup(self.parseBilibiliGroup)


bilibiliConfig = BilibiliConfig()
