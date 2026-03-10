import asyncio
from io import BytesIO
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlparse

import niquests
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
    SettingCardGroup,
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

from app.bases.models import PackConfig
from app.services.core_service import coreService
from app.supports.config import DEFAULT_HEADERS, cfg
from app.supports.utils import getProxies

if TYPE_CHECKING:
    from app.view.pages.setting_page import SettingPage


_BILIBILI_WEB_QR_GENERATE_API = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
_BILIBILI_WEB_QR_POLL_API = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
_BILIBILI_LOGIN_INFO_API = "https://api.bilibili.com/x/web-interface/nav"
_BILIBILI_LOGOUT_API = "https://passport.bilibili.com/login/exit/v2"
_BILIBILI_QR_POLL_INTERVAL_MS = 2000
_BILIBILI_QR_UNSCANNED = 86101
_BILIBILI_QR_SCANNED = 86090
_BILIBILI_QR_EXPIRED = 86038
_BILIBILI_LOGIN_COOKIE_ORDER = (
    "SESSDATA",
    "bili_jct",
    "DedeUserID",
    "DedeUserID__ckMd5",
    "sid",
)


def _parseCookieString(cookie: str) -> dict[str, str]:
    normalizedParts: dict[str, str] = {}
    if not isinstance(cookie, str):
        return normalizedParts

    for part in cookie.replace("\r", ";").replace("\n", ";").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue

        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name and value:
            normalizedParts[name] = value

    return normalizedParts


def _normalizeCookieString(cookie: str) -> str:
    normalizedParts = _parseCookieString(cookie)
    orderedNames = [name for name in _BILIBILI_LOGIN_COOKIE_ORDER if name in normalizedParts]
    extraNames = [name for name in normalizedParts if name not in _BILIBILI_LOGIN_COOKIE_ORDER]
    return "; ".join(f"{name}={normalizedParts[name]}" for name in orderedNames + extraNames)


def _buildBilibiliLoginHeaders(cookie: str = "", *, includeOrigin: bool = False) -> dict[str, str]:
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": DEFAULT_HEADERS["accept-language"],
        "user-agent": DEFAULT_HEADERS["user-agent"],
    }
    normalizedCookie = _normalizeCookieString(cookie)
    if normalizedCookie:
        headers["cookie"] = normalizedCookie
    if includeOrigin:
        headers["origin"] = "https://www.bilibili.com"
        headers["referer"] = "https://www.bilibili.com/"
    return headers


def _createQrPixmap(content: str, size: int = 240) -> QPixmap:
    if qrcode is None:
        raise RuntimeError("缺少 qrcode 依赖，无法生成登录二维码")

    qrCode = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=2, box_size=10)
    qrCode.add_data(content)
    qrCode.make(fit=True)

    image = qrCode.make_image(fill_color="black", back_color="white").convert("RGB")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    pixmap = QPixmap()
    pixmap.loadFromData(buffer.getvalue(), "PNG")
    return pixmap.scaled(size, size)


def _extractCookieItemsFromResponse(response) -> dict[str, str]:
    cookieItems: dict[str, str] = {}

    cookies = getattr(response, "cookies", None)
    if cookies is not None:
        try:
            for name, value in cookies.items():
                if name and value:
                    cookieItems[str(name)] = str(value)
        except Exception:
            try:
                for cookie in cookies:
                    name = getattr(cookie, "name", "")
                    value = getattr(cookie, "value", "")
                    if name and value:
                        cookieItems[str(name)] = str(value)
            except Exception:
                pass

    return cookieItems


def _extractCookieItemsFromSuccessUrl(successUrl: str) -> dict[str, str]:
    if not successUrl:
        return {}

    cookieItems: dict[str, str] = {}
    for name, value in parse_qsl(urlparse(successUrl).query, keep_blank_values=False):
        if name in _BILIBILI_LOGIN_COOKIE_ORDER and value:
            cookieItems[name] = value

    return cookieItems


def _extractCookieString(response, payloadData: dict) -> str:
    cookieItems = _extractCookieItemsFromResponse(response)
    if not any(name in cookieItems for name in _BILIBILI_LOGIN_COOKIE_ORDER):
        cookieItems.update(_extractCookieItemsFromSuccessUrl(str(payloadData.get("url") or "").strip()))

    orderedNames = [name for name in _BILIBILI_LOGIN_COOKIE_ORDER if name in cookieItems]
    extraNames = [name for name in cookieItems if name not in _BILIBILI_LOGIN_COOKIE_ORDER]
    cookieString = "; ".join(f"{name}={cookieItems[name]}" for name in orderedNames + extraNames)
    return _normalizeCookieString(cookieString)


def _formatVipStatus(data: dict) -> str:
    vipPayload = data.get("vip") or {}
    vipStatus = int(data.get("vipStatus") or vipPayload.get("status") or 0)
    if vipStatus != 1:
        return "未开通"

    vipLabel = ((vipPayload.get("label") or {}).get("text") or (data.get("vip_label") or {}).get("text") or "").strip()
    if vipLabel:
        return vipLabel

    vipType = int(data.get("vipType") or vipPayload.get("type") or 0)
    if vipType == 1:
        return "月度大会员"
    if vipType == 2:
        return "年度大会员"
    return "大会员"


async def _requestBilibiliQrCode() -> dict[str, str]:
    client = niquests.AsyncSession(
        headers=_buildBilibiliLoginHeaders(),
        timeout=30,
        happy_eyeballs=True,
    )
    client.trust_env = False

    try:
        response = await client.get(
            _BILIBILI_WEB_QR_GENERATE_API,
            proxies=getProxies(),
            verify=cfg.SSLVerify.value,
            allow_redirects=True,
        )
        try:
            response.raise_for_status()
            payload = response.json()
        finally:
            response.close()

        if payload.get("code") not in {None, 0}:
            raise ValueError(payload.get("message") or "获取二维码失败")

        data = payload.get("data") or {}
        loginUrl = str(data.get("url") or "").strip()
        qrCodeKey = str(data.get("qrcode_key") or "").strip()
        if not loginUrl or not qrCodeKey:
            raise ValueError("二维码接口返回了不完整的数据")

        return {
            "url": loginUrl,
            "qrcode_key": qrCodeKey,
        }
    finally:
        await client.close()


async def _pollBilibiliQrLogin(
    qrCodeKey: str,
    statusCallback=None,
    shouldStop=None,
) -> dict[str, str | int]:
    client = niquests.AsyncSession(
        headers=_buildBilibiliLoginHeaders(),
        timeout=30,
        happy_eyeballs=True,
    )
    client.trust_env = False

    try:
        while True:
            if shouldStop is not None and shouldStop():
                return {"code": -1, "message": "cancelled", "url": "", "cookie": ""}

            response = await client.get(
                _BILIBILI_WEB_QR_POLL_API,
                params={"qrcode_key": qrCodeKey},
                proxies=getProxies(),
                verify=cfg.SSLVerify.value,
                allow_redirects=True,
            )
            try:
                response.raise_for_status()
                payload = response.json()
                data = payload.get("data") or {}
                cookieString = _extractCookieString(response, data) if data.get("code") == 0 else ""
            finally:
                response.close()

            if payload.get("code") not in {None, 0}:
                raise ValueError(payload.get("message") or "轮询扫码状态失败")

            statusCode = int(data.get("code", -1))
            statusMessage = str(data.get("message") or "").strip()
            result = {
                "code": statusCode,
                "message": statusMessage,
                "url": str(data.get("url") or "").strip(),
                "cookie": cookieString,
            }

            if statusCode in {_BILIBILI_QR_UNSCANNED, _BILIBILI_QR_SCANNED}:
                coreService._executeCallback(statusCallback, statusCode, statusMessage)
                await asyncio.sleep(_BILIBILI_QR_POLL_INTERVAL_MS / 1000)
                continue

            return result
    finally:
        await client.close()


async def _fetchBilibiliLoginInfo(cookie: str) -> dict[str, str | bool]:
    normalizedCookie = _normalizeCookieString(cookie)
    if not normalizedCookie:
        return {
            "logged_in": False,
            "status": "未登录",
            "uname": "-",
            "mid": "-",
            "vip": "未开通",
        }

    client = niquests.AsyncSession(
        headers=_buildBilibiliLoginHeaders(normalizedCookie),
        timeout=30,
        happy_eyeballs=True,
    )
    client.trust_env = False

    try:
        response = await client.get(
            _BILIBILI_LOGIN_INFO_API,
            proxies=getProxies(),
            verify=cfg.SSLVerify.value,
            allow_redirects=True,
        )
        try:
            response.raise_for_status()
            payload = response.json()
        finally:
            response.close()

        data = payload.get("data") or {}
        if payload.get("code") == -101 or not data.get("isLogin"):
            return {
                "logged_in": False,
                "status": "未登录",
                "uname": "-",
                "mid": "-",
                "vip": "未开通",
            }

        if payload.get("code") not in {None, 0}:
            raise ValueError(payload.get("message") or "获取登录信息失败")

        return {
            "logged_in": True,
            "status": "已登录",
            "uname": str(data.get("uname") or "-").strip() or "-",
            "mid": str(data.get("mid") or "-"),
            "vip": _formatVipStatus(data),
        }
    finally:
        await client.close()


async def _logoutBilibili(cookie: str) -> dict[str, str | bool]:
    normalizedCookie = _normalizeCookieString(cookie)
    cookieItems = _parseCookieString(normalizedCookie)
    requiredCookies = ("DedeUserID", "bili_jct", "SESSDATA")
    missingCookies = [name for name in requiredCookies if not cookieItems.get(name)]
    if missingCookies:
        return {
            "remote_logout": False,
            "clear_local": True,
            "message": f"Cookie 缺少 {', '.join(missingCookies)}，已清除本地登录状态",
        }

    client = niquests.AsyncSession(
        headers=_buildBilibiliLoginHeaders(normalizedCookie, includeOrigin=True),
        timeout=30,
        happy_eyeballs=True,
    )
    client.trust_env = False

    try:
        response = await client.post(
            _BILIBILI_LOGOUT_API,
            data={
                "biliCSRF": cookieItems["bili_jct"],
                "gourl": "https://www.bilibili.com/",
            },
            proxies=getProxies(),
            verify=cfg.SSLVerify.value,
            allow_redirects=True,
        )
        try:
            response.raise_for_status()
            contentType = str(response.headers.get("content-type") or "").lower()
            if "application/json" not in contentType:
                return {
                    "remote_logout": False,
                    "clear_local": True,
                    "message": "当前 Cookie 可能已失效，已清除本地登录状态",
                }

            payload = response.json()
        finally:
            response.close()

        if payload.get("code") == 0 and payload.get("status") is True:
            return {
                "remote_logout": True,
                "clear_local": True,
                "message": "已退出登录",
            }

        raise ValueError(payload.get("message") or "退出登录失败")
    finally:
        await client.close()


async def _replaceBilibiliCookie(currentCookie: str, newCookie: str) -> dict[str, str]:
    normalizedCurrentCookie = _normalizeCookieString(currentCookie)
    normalizedNewCookie = _normalizeCookieString(newCookie)

    if not normalizedNewCookie:
        return {"cookie": ""}

    if normalizedCurrentCookie and normalizedCurrentCookie != normalizedNewCookie:
        await _logoutBilibili(normalizedCurrentCookie)

    return {"cookie": normalizedNewCookie}


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
        self._polling = False
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
            self.tr("二维码有效期约 180 秒，失效后可点击“刷新二维码”重新生成"),
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
        self._polling = False
        self.cookie = ""
        self._qrCodeKey = ""
        self._loginUrl = ""
        self.openBrowserButton.setEnabled(False)
        self.qrPixmapLabel.setPixmap(QPixmap())
        self.statusLabel.setText(self.tr("正在获取二维码..."))

        generation = self._generation
        coreService.runCoroutine(
            _requestBilibiliQrCode(),
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
            return

        self.openBrowserButton.setEnabled(True)
        self.statusLabel.setText(self.tr("等待扫码并在手机端确认登录"))
        self._polling = True
        generation = self._generation
        coreService.runCoroutine(
            _pollBilibiliQrLogin(
                self._qrCodeKey,
                lambda statusCode, statusMessage: self._onLoginPollingStatus(generation, statusCode, statusMessage),
                lambda: self._closed or generation != self._generation,
            ),
            lambda result, error: self._onLoginPolled(generation, result, error),
        )

    def _onLoginPollingStatus(self, generation: int, statusCode: int, statusMessage: str):
        if self._closed or generation != self._generation:
            return

        if statusCode == _BILIBILI_QR_UNSCANNED:
            self.statusLabel.setText(self.tr("等待扫码"))
            return

        if statusCode == _BILIBILI_QR_SCANNED:
            self.statusLabel.setText(self.tr("二维码已扫码，请在手机端确认登录"))
            return

        if statusMessage:
            self.statusLabel.setText(statusMessage)

    def _onLoginPolled(self, generation: int, result: dict | None, error: str | None):
        if self._closed or generation != self._generation:
            return

        self._polling = False

        if error:
            self.statusLabel.setText(self.tr("轮询扫码状态失败，请点击“刷新二维码”重试"))
            return

        payload = result or {}
        statusCode = int(payload.get("code", -1))
        statusMessage = str(payload.get("message") or "").strip()

        if statusCode == -1:
            return

        if statusCode == _BILIBILI_QR_EXPIRED:
            self.statusLabel.setText(self.tr("二维码已失效，请点击“刷新二维码”重新生成"))
            return

        if statusCode == 0:
            self.cookie = _normalizeCookieString(str(payload.get("cookie") or ""))
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
            "账号登录",
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

        self.scanLoginButton = PrimaryPushButton("扫码登录", self.operationWidget)
        self.editCookieButton = PushButton("手动设置 Cookie", self.operationWidget)
        self.logoutButton = PushButton("退出登录", self.operationWidget)

        self.operationLayout.addWidget(self.scanLoginButton)
        self.operationLayout.addWidget(self.editCookieButton)
        self.operationLayout.addWidget(self.logoutButton)

        self.hBoxLayout.addWidget(self.operationWidget, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.hBoxLayout.addSpacing(16)

        self.scanLoginButton.clicked.connect(self._onScanLoginButtonClicked)
        self.editCookieButton.clicked.connect(self._onEditCookieButtonClicked)
        self.logoutButton.clicked.connect(self._onLogoutButtonClicked)

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
        self.logoutButton.setEnabled(not busy and bool(_normalizeCookieString(self.userCookieItem.value)))

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
        cookie = _normalizeCookieString(self.userCookieItem.value)
        if cookie != self.userCookieItem.value:
            cfg.set(self.userCookieItem, cookie)

        self._syncButtonsEnabled()
        if not cookie:
            self._setAccountInfo("未登录", "-", "-", "未开通")
            return

        self._setAccountInfo("正在获取账号信息...", "-", "-", "-")
        self._infoGeneration += 1
        generation = self._infoGeneration
        coreService.runCoroutine(
            _fetchBilibiliLoginInfo(cookie),
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

    def _applyNewCookie(self, newCookie: str):
        normalizedNewCookie = _normalizeCookieString(newCookie)
        if not normalizedNewCookie:
            cfg.set(self.userCookieItem, "")
            self.refreshLoginInfo()
            return

        currentCookie = _normalizeCookieString(self.userCookieItem.value)
        self._syncButtonsEnabled(True)
        if currentCookie and currentCookie != normalizedNewCookie:
            self._setAccountInfo("正在退出旧账号并导入新账号...", "-", "-", "-")
        else:
            self._setAccountInfo("正在导入 Cookie...", "-", "-", "-")

        coreService.runCoroutine(
            _replaceBilibiliCookie(currentCookie, normalizedNewCookie),
            self._onCookieApplied,
        )

    def _onCookieApplied(self, result: dict | None, error: str | None):
        if error:
            self._syncButtonsEnabled()
            self._setAccountInfo("切换账号失败", "-", "-", "-")
            return

        payload = result or {}
        cfg.set(self.userCookieItem, _normalizeCookieString(str(payload.get("cookie") or "")))
        self.refreshLoginInfo()

    def _onScanLoginButtonClicked(self):
        dialog = ScanLoginDialog(self.window())
        if dialog.exec():
            self._applyNewCookie(dialog.cookie)

    def _onEditCookieButtonClicked(self):
        dialog = EditCookieDialog(self.window(), self.userCookieItem.value)
        try:
            if dialog.exec():
                self._applyNewCookie(dialog.cookieTextEdit.toPlainText())
        finally:
            dialog.deleteLater()

    def _onLogoutButtonClicked(self):
        cookie = _normalizeCookieString(self.userCookieItem.value)
        if not cookie:
            self.refreshLoginInfo()
            return

        self._syncButtonsEnabled(True)
        self._setAccountInfo("正在退出登录...")
        coreService.runCoroutine(_logoutBilibili(cookie), self._onLoggedOut)

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
        if type(value) == str:
            return True
        return False

    def correct(self, value) -> str:
        return value if self.validate(value) else ""


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

    def loadSettingCards(self, settingPage: "SettingPage"):
        self.parseBilibiliGroup = SettingCardGroup("哔哩哔哩视频下载", settingPage.container)

        self.defaultQualityCard = ComboBoxSettingCard(
            self.defaultQuality,
            FluentIcon.VIDEO,
            "默认清晰度",
            "下载视频时默认的清晰度",
            ["8K", "4K", "1080P60", "1080P+", "1080P", "720P60", "720P", "480P", "360P"],
            self.parseBilibiliGroup,
        )

        self.alternativeQualityCard = ComboBoxSettingCard(
            self.alternativeQuality,
            FluentIcon.VIDEO,
            "备选清晰度",
            "下载视频时备选的清晰度",
            ["可以下载的最高画质", "可以下载的最低画质"],
            self.parseBilibiliGroup,
        )

        self.parseHDRCard = SwitchSettingCard(
            FluentIcon.VIDEO,
            "HDR",
            "下载 HDR 视频",
            self.parseHDR,
            self.parseBilibiliGroup,
        )

        self.parseDolbyCard = SwitchSettingCard(
            FluentIcon.VIDEO,
            "杜比视界",
            "下载杜比视界视频",
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

        settingPage.vBoxLayout.addWidget(self.parseBilibiliGroup)


bilibiliConfig = BilibiliConfig()
