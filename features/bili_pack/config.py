from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap

from qfluentwidgets import (
    BoolValidator,
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    MessageBoxBase,
    OptionsConfigItem,
    OptionsValidator,
    PixmapLabel,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    SettingCard,
    SubtitleLabel,
)

from app.config.cfg import ConfigItem
from app.models.pack import PackConfig

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
    from app.view.components.setting_card_group import CollapsibleSettingCardGroup


def _toQrPixmap(content: str, size: int = 240) -> QPixmap:
    import qrcode
    from qrcode.image.pure import PyPNGImage

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=2, box_size=10)
    qr.add_data(content)
    qr.make(fit=True)
    buf = BytesIO()
    qr.make_image(image_factory=PyPNGImage).save(buf)
    pixmap = QPixmap()
    pixmap.loadFromData(buf.getvalue(), "PNG")
    return pixmap.scaled(size, size)


class ScanLoginDialog(MessageBoxBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._loginUrl = ""


        self.widget.setFixedSize(430, 560)
        self.yesButton.hide()
        self.cancelButton.setText(self.tr("关闭"))

        self.titleLabel = SubtitleLabel(self.tr("扫码登录"), self.widget)
        self.descriptionLabel = CaptionLabel(
            self.tr("使用哔哩哔哩手机客户端扫描下方二维码，并在手机端确认登录"),
            self.widget,
        )
        self.qrLabel = PixmapLabel(self.widget)
        self.qrLabel.setFixedSize(240, 240)
        self.qrLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qrLabel.setScaledContents(True)

        self.statusLabel = BodyLabel(self.tr("正在获取二维码..."), self.widget)
        self.tipLabel = CaptionLabel(
            self.tr('二维码有效期约 180 秒，失效后可点击"刷新二维码"重新生成'),
            self.widget,
        )

        self.refreshButton = PrimaryPushButton(FluentIcon.SYNC, self.tr("刷新二维码"), self.widget)
        self.openBrowserButton = PushButton(FluentIcon.LINK, self.tr("打开登录链接"), self.widget)
        self.openBrowserButton.setEnabled(False)

        self._initWidget()
        self._initLayout()
        self._bind()
        self.reloadQrCode()

    def _initWidget(self):
        self.statusLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.statusLabel.setWordWrap(True)
        self.tipLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tipLabel.setWordWrap(True)

    def _initLayout(self):
        from PySide6.QtWidgets import QHBoxLayout
        buttonLayout = QHBoxLayout()
        buttonLayout.setSpacing(12)
        buttonLayout.addWidget(self.refreshButton)
        buttonLayout.addWidget(self.openBrowserButton)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.descriptionLabel)
        self.viewLayout.addSpacing(12)
        self.viewLayout.addWidget(self.qrLabel, 0, Qt.AlignmentFlag.AlignCenter)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.statusLabel)
        self.viewLayout.addWidget(self.tipLabel)
        self.viewLayout.addSpacing(6)
        self.viewLayout.addLayout(buttonLayout)

    def _bind(self):
        from .account import bilibiliAccount
        self.refreshButton.clicked.connect(self.reloadQrCode)
        self.openBrowserButton.clicked.connect(self._onOpenBrowser)
        bilibiliAccount.qrStateChanged.connect(self._onQrState)

    def reloadQrCode(self):
        from .account import bilibiliAccount
        self.qrLabel.setPixmap(QPixmap())
        self.qrLabel.setFixedSize(240, 240)
        self.statusLabel.setText(self.tr("正在获取二维码..."))
        self.openBrowserButton.setEnabled(False)
        self._loginUrl = ""
        bilibiliAccount.startQrLogin()

    def _onQrState(self, statusCode: int, text: str):
        from .account import QR_EXPIRED, QR_LOGIN_SUCCESS, QR_UNSCANNED, QR_SCANNED
        if statusCode == QR_LOGIN_SUCCESS:
            self.statusLabel.setText(self.tr("登录成功，正在导入 Cookie..."))
            self.accept()
        elif statusCode == 0:
            self._loginUrl = text
            self.qrLabel.setPixmap(_toQrPixmap(text))
            self.qrLabel.setFixedSize(240, 240)
            self.statusLabel.setText(self.tr("请使用哔哩哔哩客户端扫码"))
            self.openBrowserButton.setEnabled(True)
        elif statusCode == QR_UNSCANNED:
            self.statusLabel.setText(self.tr("等待扫码"))
        elif statusCode == QR_SCANNED:
            self.statusLabel.setText(self.tr("二维码已扫码，请在手机端确认登录"))
        elif statusCode == QR_EXPIRED:
            self.statusLabel.setText(self.tr('二维码已失效，请点击"刷新二维码"重新生成'))
        else:
            self.statusLabel.setText(text or str(statusCode))

    def _onOpenBrowser(self):
        if self._loginUrl:
            QDesktopServices.openUrl(QUrl(self._loginUrl))

    def done(self, code):
        from .account import bilibiliAccount
        bilibiliAccount.cancelQrLogin()
        super().done(code)


class EditCookieDialog(MessageBoxBase):
    def __init__(self, parent=None, initialCookie: str = ""):
        super().__init__(parent)

        self.widget.setFixedSize(420, 500)
        self.yesButton.setText(self.tr("保存"))
        self.cancelButton.setText(self.tr("取消"))

        self.titleLabel = SubtitleLabel(self.tr("手动导入 Cookie"), self.widget)
        self.descriptionLabel = CaptionLabel(
            self.tr("请粘贴浏览器导出的完整 Cookie，留空后保存可清空当前 Cookie"), self.widget,
        )
        self.cookieTextEdit = PlainTextEdit(self.widget)
        self.cookieTextEdit.setPlaceholderText(self.tr("请在此输入用户 Cookie"))
        self.cookieTextEdit.setPlainText(initialCookie or "")

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.descriptionLabel)
        self.viewLayout.addWidget(self.cookieTextEdit)


class BilibiliLoginSettingCard(SettingCard):
    def __init__(self, parent=None):
        super().__init__(
            FluentIcon.VIEW, self.tr("账号登录"),
            self.tr("状态：未登录"), parent,
        )
        self.scanButton = PrimaryPushButton(self.tr("扫码登录"), self)
        self.editButton = PushButton(self.tr("导入 Cookie"), self)
        self.logoutButton = PushButton(self.tr("退出登录"), self)

        self._initLayout()
        self._bind()
        self.refreshLoginInfo()

    def _initLayout(self):
        self.hBoxLayout.addWidget(self.scanButton, 0)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.editButton, 0)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.logoutButton, 0)
        self.hBoxLayout.addSpacing(16)

    def _bind(self):
        from .account import bilibiliAccount
        self.scanButton.clicked.connect(self._onScanLogin)
        self.editButton.clicked.connect(self._onEditCookie)
        self.logoutButton.clicked.connect(self._onLogout)
        bilibiliAccount.accountChanged.connect(self.refreshLoginInfo)

    def refreshLoginInfo(self):
        from .account import bilibiliAccount
        if bilibiliAccount.isLoggedIn:
            uname = bilibiliAccount.username or "-"
            mid = bilibiliAccount.mid or "-"
            vip = bilibiliAccount.vip or "未开通"
            self.setContent(
                self.tr("状态：已登录 用户名：{0} UID：{1} 会员状态：{2}").format(uname, mid, vip)
            )
        else:
            self.setContent(self.tr("状态：未登录"))
        self.scanButton.setEnabled(True)
        self.editButton.setEnabled(True)
        self.logoutButton.setEnabled(bilibiliAccount.isLoggedIn)

    def _onScanLogin(self):
        dialog = ScanLoginDialog(self.window())
        dialog.exec()
        dialog.deleteLater()

    def _onEditCookie(self):
        from .account import bilibiliAccount, toCookie
        dialog = EditCookieDialog(self.window(), bilibiliAccount.cookie)
        if not dialog.exec():
            dialog.deleteLater()
            return

        newCookie = toCookie(dialog.cookieTextEdit.toPlainText())
        dialog.deleteLater()
        if not newCookie:
            bilibiliAccount.setCookie("")
            return

        bilibiliAccount.setCookie(newCookie)

    def _onLogout(self):
        from .account import bilibiliAccount
        self.scanButton.setEnabled(False)
        self.editButton.setEnabled(False)
        self.logoutButton.setEnabled(False)
        self.setContent(self.tr("正在退出登录..."))
        bilibiliAccount.logout()


class BilibiliConfig(PackConfig):
    userCookie = ConfigItem("Bilibili", "UserCookie", "")
    defaultQuality = OptionsConfigItem(
        "Bilibili", "DefaultQuality", 80,
        OptionsValidator([16, 32, 64, 80, 112, 116, 120, 125, 126, 127, 128]),
    )
    alternativeQuality = OptionsConfigItem(
        "Bilibili", "AlternativeQuality", "max",
        OptionsValidator(["max", "min"]),
    )
    shouldIncludeHdr = ConfigItem("Bilibili", "ParseHDR", False, BoolValidator())
    shouldIncludeDolby = ConfigItem("Bilibili", "ParseDolby", False, BoolValidator())

    def settingGroups(self, parent: QWidget) -> list[CollapsibleSettingCardGroup]:
        from qfluentwidgets import ComboBoxSettingCard, FluentIcon, SwitchSettingCard
        from app.view.components.setting_card_group import CollapsibleSettingCardGroup

        biliGroup = CollapsibleSettingCardGroup(self.tr("Bilibili 下载"), "bilibili", parent)
        loginCard = BilibiliLoginSettingCard(biliGroup)
        biliGroup.addSettingCards([
            loginCard,
            ComboBoxSettingCard(self.defaultQuality, FluentIcon.VIDEO, self.tr("默认画质"),
                                self.tr("选择偏好的视频画质"),
                                texts=["240P", "360P", "480P", "720P", "720P60", "1080P",
                                       "1080P+", "1080P60", "4K", "HDR", "杜比视界"],
                                parent=biliGroup),
            ComboBoxSettingCard(self.alternativeQuality, FluentIcon.SPEED_HIGH, self.tr("画质不可用时"),
                                self.tr("当选择的画质不可用时的替代策略"),
                                texts=[self.tr("选择最高画质"), self.tr("选择最低画质")],
                                parent=biliGroup),
            SwitchSettingCard(FluentIcon.PALETTE, self.tr("HDR"),
                              self.tr("请求 HDR 视频流（需要大会员）"),
                              self.shouldIncludeHdr, biliGroup),
            SwitchSettingCard(FluentIcon.HEADPHONE, self.tr("杜比全景声/视界"),
                              self.tr("请求杜比全景声和杜比视界（需要大会员）"),
                              self.shouldIncludeDolby, biliGroup),
        ])
        return [biliGroup]


bilibiliConfig = BilibiliConfig()
