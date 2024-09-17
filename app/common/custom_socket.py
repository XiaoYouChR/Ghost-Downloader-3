import json

from PySide6.QtCore import Slot, QObject, Signal
from PySide6.QtNetwork import QHostAddress
from PySide6.QtWebSockets import QWebSocketServer
from loguru import logger


class GhostDownloaderSocketServer(QObject):
    receiveUrl = Signal(str)
    def __init__(self, parent=None):

        super().__init__(parent)
        # 创建 WebSocket 服务器
        self.server = QWebSocketServer("Ghost Downloader Socket Server", QWebSocketServer.NonSecureMode, parent)

        # 监听 localhost:14370
        if self.server.listen(QHostAddress.LocalHost, 14370):
            logger.info(f"Ghost Downloader Socket Server started on ws://{self.server.serverAddress().toString()}:{self.server.serverPort()}")

        # 信号槽连接：有新客户端连接时触发
        self.server.newConnection.connect(self.onNewConnection)

        # 存储已连接的客户端
        self.clients = []

    @Slot()
    def onNewConnection(self):
        # 接收新连接的客户端
        client = self.server.nextPendingConnection()

        logger.debug(f"New client connected: {client.peerAddress().toString()}:{client.peerPort()}")

        # 信号槽连接：接收客户端消息时触发
        client.textMessageReceived.connect(self.processTextMessage)

        # 将新客户端添加到客户端列表
        self.clients.append(client)

    @Slot(str)
    def processTextMessage(self, message: str):
        logger.debug(f"Received message from client: {message}")
        # 处理客户端发送的消息
        try:
            self.receiveUrl.emit(json.loads(message)["url"])
        except Exception as e:
            logger.error(f"Receive info Cannot Get Url, Error: {e}")
