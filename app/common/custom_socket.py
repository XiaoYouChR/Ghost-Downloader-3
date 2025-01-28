import json

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtNetwork import QHostAddress
from PySide6.QtWebSockets import QWebSocketServer
from loguru import logger

from app.common.config import VERSION, LATEST_EXTENSION_VERSION
from app.common.methods import addDownloadTask
from app.view.pop_up_window import ReceivedPopUpWindow


class GhostDownloaderSocketServer(QObject):

    def __init__(self, parent=None):
        super().__init__(parent)

        # 创建 WebSocket 服务器并监听 localhost:14370
        self.server = QWebSocketServer("Ghost Downloader Socket Server", QWebSocketServer.NonSecureMode, parent)

        if self.server.listen(QHostAddress.LocalHost, 14370):
            logger.info(f"Server started on ws://{self.server.serverAddress().toString()}:{self.server.serverPort()}")

        self.server.newConnection.connect(self.onNewConnection)
        self.clients = []

    @Slot()
    def onNewConnection(self):
        client = self.server.nextPendingConnection()
        logger.debug(f"New client connected: {client.peerAddress().toString()}:{client.peerPort()}")

        client.textMessageReceived.connect(self.processTextMessage)
        client.disconnected.connect(self.onClientDisconnected)  # 连接断开时的信号

        client.sendTextMessage(json.dumps({"type": "version", "ClientVersion": VERSION, "LatestExtensionVersion": LATEST_EXTENSION_VERSION}))

        self.clients.append(client)

    @Slot()
    def onClientDisconnected(self):
        client = self.sender()  # 获取断开的客户端
        if client in self.clients:
            self.clients.remove(client)  # 从列表中移除断开的客户端
            logger.debug(f"Client disconnected: {client.peerAddress().toString()}:{client.peerPort()}")

    @Slot(str)
    def processTextMessage(self, message: str):
        """处理客户端发送的消息"""
        try:
            data = json.loads(message)
            if data.get("type") == "heartbeat":
                # logger.debug("Heartbeat received")
                return  # 忽略心跳消息
            logger.debug(f"Received message: {message}")

            url = data["url"]
            headers = data["headers"]
            if data["referer"]:
                headers["referer"] = data["referer"]
            filename = data["filename"]
            addDownloadTask(url, filename, headers=headers)

            if filename:
                ReceivedPopUpWindow.showPopUpWindow(filename, self.parent())
            else:
                ReceivedPopUpWindow.showPopUpWindow(url, self.parent())

        except Exception as e:
            logger.error(f"Error processing message: {repr(e)}")
