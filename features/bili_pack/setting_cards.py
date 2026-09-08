from __future__ import annotations

from io import BytesIO

from PySide6.QtCore import QCoreApplication, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QHBoxLayout

from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    MessageBoxBase,
    PixmapLabel,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    SettingCard,
    SubtitleLabel,
)


def toQrPixmap(content: str, size: int = 240) -> QPixmap:
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
    def __init__(self, account, parent=None):
        super().__init__(parent)
        self._account = account
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
        self.refreshButton.clicked.connect(self.reloadQrCode)
        self.openBrowserButton.clicked.connect(self._onOpenBrowser)
        self._account.qrStateChanged.connect(self._onQrState)

    def reloadQrCode(self):
        self.qrLabel.setPixmap(QPixmap())
        self.qrLabel.setFixedSize(240, 240)
        self.statusLabel.setText(self.tr("正在获取二维码..."))
        self.openBrowserButton.setEnabled(False)
        self._loginUrl = ""
        self._account.startQrLogin()

    def _onQrState(self, statusCode: int, text: str):
        from .account import QR_EXPIRED, QR_LOGIN_SUCCESS, QR_UNSCANNED, QR_SCANNED
        if statusCode == QR_LOGIN_SUCCESS:
            self.statusLabel.setText(self.tr("登录成功，正在导入 Cookie..."))
            self.accept()
        elif statusCode == 0:
            self._loginUrl = text
            self.qrLabel.setPixmap(toQrPixmap(text))
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
            self.statusLabel.setText(
                QCoreApplication.translate("BilibiliErrors", text) if text else str(statusCode)
            )

    def _onOpenBrowser(self):
        if self._loginUrl:
            QDesktopServices.openUrl(QUrl(self._loginUrl))

    def done(self, code):
        self._account.cancelQrLogin()
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
    def __init__(self, account, parent=None):
        self._account = account
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
        self.scanButton.clicked.connect(self._onScanLogin)
        self.editButton.clicked.connect(self._onEditCookie)
        self.logoutButton.clicked.connect(self._onLogout)
        self._account.accountChanged.connect(self.refreshLoginInfo)

    def refreshLoginInfo(self):
        if self._account.isLoggedIn:
            uname = self._account.username or "-"
            mid = self._account.mid or "-"
            vip = self._account.vip or "未开通"
            self.setContent(
                self.tr("状态：已登录 用户名：{0} UID：{1} 会员状态：{2}").format(uname, mid, vip)
            )
        else:
            self.setContent(self.tr("状态：未登录"))
        self.scanButton.setEnabled(True)
        self.editButton.setEnabled(True)
        self.logoutButton.setEnabled(self._account.isLoggedIn)

    def _onScanLogin(self):
        dialog = ScanLoginDialog(self._account, self.window())
        dialog.exec()
        dialog.deleteLater()

    def _onEditCookie(self):
        from .account import toCookie
        dialog = EditCookieDialog(self.window(), self._account.cookie)
        if not dialog.exec():
            dialog.deleteLater()
            return

        newCookie = toCookie(dialog.cookieTextEdit.toPlainText())
        dialog.deleteLater()
        if not newCookie:
            self._account.setCookie("")
            return

        self._account.setCookie(newCookie)

    def _onLogout(self):
        self.scanButton.setEnabled(False)
        self.editButton.setEnabled(False)
        self.logoutButton.setEnabled(False)
        self.setContent(self.tr("正在退出登录..."))
        self._account.logout()
