from pathlib import Path
from typing import TYPE_CHECKING

from orjson import loads, dumps
from PySide6.QtCore import QObject, Slot
from PySide6.QtNetwork import QHostAddress
from PySide6.QtWebSockets import QWebSocketServer
from loguru import logger
from qfluentwidgets import InfoBar, InfoBarPosition

from app.services.core_service import coreService
from app.supports.config import VERSION, LATEST_EXTENSION_VERSION, cfg
from app.supports.utils import getProxies, bringWindowToTop

if TYPE_CHECKING:
    from app.view.windows.main_window import MainWindow
    from PySide6.QtWebSockets import QWebSocket


class BrowserService(QObject):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.mainWindow: "MainWindow" = parent
        self.server = QWebSocketServer("Ghost Downloader Socket Server", QWebSocketServer.SslMode.NonSecureMode, parent)
        self.server.newConnection.connect(self._onNewConnection)
        self.clients = []
        cfg.enableBrowserExtension.valueChanged.connect(self._syncEnabled)
        self._syncEnabled(cfg.enableBrowserExtension.value)

    @Slot(bool)
    def _syncEnabled(self, enabled: bool):
        if enabled:
            if self.server.isListening():
                return

            if self.server.listen(QHostAddress.SpecialAddress.LocalHost, 14370):
                logger.info(
                    f"Browser extension server started on "
                    f"ws://{self.server.serverAddress().toString()}:{self.server.serverPort()}"
                )
                return

            logger.error(f"Failed to start browser extension server: {self.server.errorString()}")
            return

        for client in self.clients.copy():
            client.close()

        if self.server.isListening():
            self.server.close()
            logger.info("Browser extension server stopped")

    @Slot()
    def _onNewConnection(self):
        client = self.server.nextPendingConnection()
        logger.debug(f"New client connected: {client.peerAddress().toString()}:{client.peerPort()}")

        client.textMessageReceived.connect(self._onReceiveMessage)
        client.disconnected.connect(self._onClientDisconnected)

        client.sendTextMessage(dumps({"type": "version", "ClientVersion": VERSION, "LatestExtensionVersion": LATEST_EXTENSION_VERSION}).decode("utf-8"))

        self.clients.append(client)

    @Slot()
    def _onClientDisconnected(self):
        client: "QWebSocket" = self.sender()  # 获取断开的客户端
        if client in self.clients:
            self.clients.remove(client)
        logger.debug(f"Client disconnected: {client.peerAddress().toString()}:{client.peerPort()}")

    def _buildPayload(self, data: dict) -> dict:
        headers = data["headers"]
        headers.pop("range", None)
        if data["referer"]:
            headers["referer"] = data["referer"]

        return {
            "url": data["url"],
            "headers": headers,
            "proxies": getProxies(),
            "path": Path(cfg.downloadFolder.value),
            "preBlockNum": cfg.preBlockNum.value,
        }

    def _onTaskParsed(self, title: str, url: str, task, error: str | None):
        if error:
            logger.error(f"Failed to parse browser task {url}: {error}")
            if self.mainWindow.isVisible():
                InfoBar.error(
                    self.tr("浏览器任务解析失败"),
                    url,
                    duration=3000,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    parent=self.mainWindow,
                )
            return

        if title:
            task.setTitle(title)

        if self.mainWindow.addTask(task) and self.mainWindow.isVisible():
            InfoBar.success(
                self.tr("已接收浏览器下载任务"),
                task.title,
                duration=2000,
                position=InfoBarPosition.BOTTOM_RIGHT,
                parent=self.mainWindow,
            )

    @Slot(str)
    def _onReceiveMessage(self, message: str):
        """处理客户端发送的消息"""
        try:
            data = loads(message)
            if data.get("type") == "heartbeat":
                return  # 忽略心跳消息

            logger.debug(f"Received message: {message}")
            payload = self._buildPayload(data)

            if cfg.enableRaiseWindowWhenReceiveMsg.value:
                bringWindowToTop(self.mainWindow)

            coreService.parseUrl(
                payload,
                lambda task, error, url=payload["url"], title=data["filename"]: self._onTaskParsed(title, url, task, error),
            )

        except Exception as e:
            logger.opt(exception=e).error("Error processing message: {}")
