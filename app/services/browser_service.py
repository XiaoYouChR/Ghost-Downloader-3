from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Slot
from PySide6.QtNetwork import QHostAddress
from PySide6.QtWebSockets import QWebSocketServer
from loguru import logger
from orjson import loads, dumps
from qfluentwidgets import InfoBar, InfoBarPosition

from app.services.core_service import coreService
from app.supports.config import VERSION, LATEST_EXTENSION_VERSION, cfg
from app.supports.signal_bus import signalBus
from app.supports.utils import getProxies

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

            e = RuntimeError(self.server.errorString())
            logger.opt(exception=e).error("Failed to start browser extension server")
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

    def _showAddTaskDialog(self, url: str, headers: dict):
        dialog = self.mainWindow.getAddTaskDialog()
        signalBus.showMainWindow.emit()
        dialog.appendUrlWithPayload(url, {"headers": headers})
        if not dialog.isVisible():
            dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _sendReceiveNotification(self, url: str, filename: str):
        content = filename or url
        coreService.loop.call_soon_threadsafe(
            lambda: coreService.loop.create_task(
                coreService.desktopNotifier.send(
                    self.tr("收到浏览器下载任务"),
                    content,
                    on_clicked=lambda: signalBus.showMainWindow.emit(),
                )
            )
        )

    def _onTaskParsed(self, title: str, url: str, task, error: str | None):
        if error:
            logger.warning("浏览器任务解析失败 {}: {}", url, error)
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
            self._sendReceiveNotification(payload["url"], data["filename"])

            if cfg.enableRaiseWindowWhenReceiveMsg.value:
                self._showAddTaskDialog(payload["url"], payload["headers"])
                return

            coreService.parseUrl(
                payload,
                lambda task, error, url=payload["url"], title=data["filename"]: self._onTaskParsed(title, url, task, error),
            )

        except Exception as e:
            logger.opt(exception=e).error("处理浏览器扩展消息失败")
