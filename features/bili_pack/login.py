import asyncio
from urllib.parse import parse_qsl, urlparse

import niquests

from app.supports.config import activeUserAgent, cfg
from app.supports.utils import getProxies

_QR_GENERATE_API = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
_QR_POLL_API = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
_LOGIN_INFO_API = "https://api.bilibili.com/x/web-interface/nav"
_LOGOUT_API = "https://passport.bilibili.com/login/exit/v2"
_QR_POLL_INTERVAL_MS = 2000
_QR_UNSCANNED = 86101
_QR_SCANNED = 86090
_QR_EXPIRED = 86038
_COOKIE_ORDER = (
    "SESSDATA",
    "bili_jct",
    "DedeUserID",
    "DedeUserID__ckMd5",
    "sid",
)


def _toCookie(raw: str) -> str:
    parts: dict[str, str] = {}
    if not isinstance(raw, str):
        return ""

    for part in raw.replace("\r", ";").replace("\n", ";").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name and value:
            parts[name] = value

    if not parts:
        return ""

    ordered = [name for name in _COOKIE_ORDER if name in parts]
    extra = [name for name in parts if name not in _COOKIE_ORDER]
    return "; ".join(f"{name}={parts[name]}" for name in ordered + extra)


def _headers(cookie: str = "", origin: bool = False) -> dict[str, str]:
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "user-agent": activeUserAgent(),
    }
    if cookie:
        headers["cookie"] = cookie
    if origin:
        headers["origin"] = "https://www.bilibili.com"
        headers["referer"] = "https://www.bilibili.com/"
    return headers


def _extractCookie(response, successUrl: str) -> str:
    items = {str(k): str(v) for k, v in response.cookies.items() if k and v}
    if not any(name in items for name in _COOKIE_ORDER):
        for name, value in parse_qsl(urlparse(successUrl).query, keep_blank_values=False):
            if name in _COOKIE_ORDER and value:
                items[name] = value

    if not items:
        return ""
    return _toCookie("; ".join(f"{k}={v}" for k, v in items.items()))


async def requestQrCode() -> dict[str, str]:
    async with niquests.AsyncSession(
        headers=_headers(),
        timeout=30,
        happy_eyeballs=True,
    ) as client:
        client.trust_env = False
        response = await client.get(
            _QR_GENERATE_API,
            proxies=getProxies(),
            verify=cfg.SSLVerify.value,
            allow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()

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


async def pollQrLogin(
    qrCodeKey: str,
    statusCallback=None,
    shouldStop=None,
) -> dict[str, str | int]:
    from app.services.core_service import coreService

    async with niquests.AsyncSession(
        headers=_headers(),
        timeout=30,
        happy_eyeballs=True,
    ) as client:
        client.trust_env = False

        while True:
            if shouldStop is not None and shouldStop():
                return {"code": -1, "message": "cancelled", "url": "", "cookie": ""}

            response = await client.get(
                _QR_POLL_API,
                params={"qrcode_key": qrCodeKey},
                proxies=getProxies(),
                verify=cfg.SSLVerify.value,
                allow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data") or {}
            cookieString = _extractCookie(response, str(data.get("url") or "")) if data.get("code") == 0 else ""

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

            if statusCode in {_QR_UNSCANNED, _QR_SCANNED}:
                coreService._executeCallback(statusCallback, statusCode, statusMessage)
                await asyncio.sleep(_QR_POLL_INTERVAL_MS / 1000)
                continue

            return result


async def fetchLoginInfo(cookie: str) -> dict[str, str | bool]:
    if not cookie:
        return {
            "logged_in": False,
            "status": "未登录",
            "uname": "-",
            "mid": "-",
            "vip": "未开通",
        }

    async with niquests.AsyncSession(
        headers=_headers(cookie),
        timeout=30,
        happy_eyeballs=True,
    ) as client:
        client.trust_env = False
        response = await client.get(
            _LOGIN_INFO_API,
            proxies=getProxies(),
            verify=cfg.SSLVerify.value,
            allow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()

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

        vipPayload = data.get("vip") or {}
        vipStatus = int(data.get("vipStatus") or vipPayload.get("status") or 0)
        if vipStatus != 1:
            vipText = "未开通"
        else:
            vipLabel = ((vipPayload.get("label") or {}).get("text") or (data.get("vip_label") or {}).get("text") or "").strip()
            if vipLabel:
                vipText = vipLabel
            else:
                vipType = int(data.get("vipType") or vipPayload.get("type") or 0)
                vipText = {1: "月度大会员", 2: "年度大会员"}.get(vipType, "大会员")

        return {
            "logged_in": True,
            "status": "已登录",
            "uname": str(data.get("uname") or "-").strip() or "-",
            "mid": str(data.get("mid") or "-"),
            "vip": vipText,
        }


async def logout(cookie: str) -> dict[str, str | bool]:
    parts: dict[str, str] = {}
    for part in cookie.split(";"):
        part = part.strip()
        if "=" in part:
            name, value = part.split("=", 1)
            parts[name.strip()] = value.strip()

    requiredCookies = ("DedeUserID", "bili_jct", "SESSDATA")
    missingCookies = [name for name in requiredCookies if not parts.get(name)]
    if missingCookies:
        return {
            "remote_logout": False,
            "clear_local": True,
            "message": f"Cookie 缺少 {', '.join(missingCookies)}，已清除本地登录状态",
        }

    async with niquests.AsyncSession(
        headers=_headers(cookie, origin=True),
        timeout=30,
        happy_eyeballs=True,
    ) as client:
        client.trust_env = False
        response = await client.post(
            _LOGOUT_API,
            data={
                "biliCSRF": parts["bili_jct"],
                "gourl": "https://www.bilibili.com/",
            },
            proxies=getProxies(),
            verify=cfg.SSLVerify.value,
            allow_redirects=True,
        )
        response.raise_for_status()
        contentType = str(response.headers.get("content-type") or "").lower()
        if "application/json" not in contentType:
            return {
                "remote_logout": False,
                "clear_local": True,
                "message": "当前 Cookie 可能已失效，已清除本地登录状态",
            }

        payload = response.json()

        if payload.get("code") == 0 and payload.get("status") is True:
            return {
                "remote_logout": True,
                "clear_local": True,
                "message": "已退出登录",
            }

        raise ValueError(payload.get("message") or "退出登录失败")
