from __future__ import annotations

import asyncio
import json
import struct
import zipfile
from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO
from pathlib import Path
from secrets import token_urlsafe
from typing import Any, TYPE_CHECKING

from PySide6.QtCore import QObject, QResource, QTimer, QVersionNumber, Signal, Slot
from PySide6.QtNetwork import QHostAddress
from PySide6.QtWebSockets import QWebSocketServer
from loguru import logger

from app.config.cfg import cfg
from app.config.constants import LATEST_EXTENSION_VERSION, VERSION
from app.config.paths import APP_DATA_DIR
from app.services.task_service import taskService

if TYPE_CHECKING:
    from PySide6.QtWebSockets import QWebSocket
    from app.models.task import Task, TaskOptions, ResourceTaskOptions

EXTENSION_UNPACK_DIR = Path(APP_DATA_DIR) / "browser_extension"


async def extractBrowserExtension() -> Path:
    """Extract the embedded CRX resource to APP_DATA_DIR/browser_extension/."""
    def _extract() -> Path:
        resource = QResource(":/res/chrome_extension.crx")
        crxData = bytes(resource.data())

        headerSize = struct.unpack_from("<I", crxData, 8)[0]
        zipOffset = 12 + headerSize

        EXTENSION_UNPACK_DIR.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(BytesIO(crxData[zipOffset:])) as zf:
            zf.extractall(EXTENSION_UNPACK_DIR)

        return EXTENSION_UNPACK_DIR

    return await asyncio.to_thread(_extract)


@dataclass
class BrowserClientSession:
    socket: QWebSocket
    isAuthenticated: bool = False
    isSubscribedToTasks: bool = False
    lastSnapshot: str | None = None
    extensionVersion: str = ""
    installType: str = ""


class MessageType(StrEnum):
    ERROR = "error"
    HELLO = "hello"
    HELLO_ACK = "hello_ack"
    PAIR_REQUEST = "pair_request"
    PAIR_RESULT = "pair_result"
    SUBSCRIBE_TASKS = "subscribe_tasks"
    TASK_SNAPSHOT = "task_snapshot"
    CREATE_TASK = "create_task"
    CREATE_TASK_RESULT = "create_task_result"
    TASK_ACTION = "task_action"
    TASK_ACTION_RESULT = "task_action_result"
    RELOAD = "reload"


class ErrorCode(StrEnum):
    BAD_REQUEST = "bad_request"
    PROTOCOL_MISMATCH = "protocol_mismatch"
    UNAUTHORIZED = "unauthorized"


class TaskAction(StrEnum):
    TOGGLE_PAUSE = "toggle_pause"
    CANCEL = "cancel"
    REDOWNLOAD = "redownload"
    OPEN_FILE = "open_file"
    OPEN_FOLDER = "open_folder"


class TaskSource(StrEnum):
    DOWNLOAD = "download"
    RESOURCE = "resource"
    RESOURCE_MERGE = "resource_merge"
    PAGE_MEDIA = "page_media"


class CreateTaskStatus(StrEnum):
    CREATED = "created"
    DRAFTED = "drafted"
    REJECTED = "rejected"


PROTOCOL_VERSION = 2


def toStr(data: dict, key: str, default: str = "") -> str:
    value = data.get(key)
    return value if isinstance(value, str) else default


def toInt(data: dict, key: str, default: int) -> int:
    value = data.get(key)
    return value if isinstance(value, int) and value > 0 else default


class BrowserService(QObject):
    pairRequested = Signal(object)
    taskDraftRequested = Signal(list)
    extensionUpdated = Signal(str)
    connectionChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server = QWebSocketServer(
            "Ghost Downloader Browser Socket Server",
            QWebSocketServer.SslMode.NonSecureMode,
            self,
        )
        self._server.newConnection.connect(self._onNewConnection)
        self._sessions: dict[int, BrowserClientSession] = {}
        self._snapshotTimer = QTimer(self)
        self._snapshotTimer.setInterval(1000)
        self._snapshotTimer.timeout.connect(self._broadcastSnapshots)
        self._isUpdatingExtension = False

    @property
    def token(self) -> str:
        if not cfg.browserExtensionPairToken.value:
            cfg.set(cfg.browserExtensionPairToken, token_urlsafe(16))
        return str(cfg.browserExtensionPairToken.value)

    @property
    def boundPort(self) -> int:
        return self._server.serverPort() if self._server.isListening() else 0

    @property
    def connectionSummary(self) -> tuple[str, str]:
        for session in self._sessions.values():
            if session.isAuthenticated:
                return session.installType, session.extensionVersion
        return "", ""

    def regenerateToken(self) -> str:
        token = token_urlsafe(16)
        cfg.set(cfg.browserExtensionPairToken, token)
        self._closeAll()
        return token

    def start(self) -> None:
        if self._server.isListening():
            return
        port = cfg.browserExtensionPort.value
        if self._server.listen(QHostAddress.SpecialAddress.LocalHost, port):
            logger.info("Browser extension server started on port {}", port)
            self._snapshotTimer.start()
        else:
            logger.error("Failed to start browser extension server on port {}: {}",
                         port, self._server.errorString())

    def stop(self) -> None:
        self._closeAll()
        self._snapshotTimer.stop()
        if self._server.isListening():
            self._server.close()

    def setEnabled(self, enabled: bool) -> None:
        if enabled:
            self.start()
        else:
            self.stop()

    def approvePair(self, session: BrowserClientSession, requestId: str) -> None:
        self._send(session, {
            "type": MessageType.PAIR_RESULT,
            "requestId": requestId,
            "ok": True,
            "token": self.token,
            "message": "配对成功",
        })

    def rejectPair(self, session: BrowserClientSession, requestId: str) -> None:
        self._send(session, {
            "type": MessageType.PAIR_RESULT,
            "requestId": requestId,
            "ok": False,
            "message": "已拒绝配对请求",
        })

    def _toResourceTaskOptions(self, resource: dict) -> ResourceTaskOptions:
        from app.models.task import ResourceTaskOptions
        return ResourceTaskOptions(
            url=toStr(resource, "url"),
            name=toStr(resource, "filename"),
            size=toInt(resource, "size", 0),
            canUseRangeRequests=bool(resource.get("supportsRange")),
            headers=resource.get("headers") or {},
        )

    def _toTaskOptions(self, source: TaskSource, payload: dict) -> TaskOptions:
        from dataclasses import replace
        from app.models.task import MergeTaskOptions, PageTaskOptions

        rawPath = payload.get("path")
        outputFolder = Path(rawPath) if rawPath else Path(cfg.downloadFolder.value)

        match source:
            case TaskSource.RESOURCE_MERGE:
                resources = payload.get("resources") or []
                video = self._toResourceTaskOptions(resources[0]) if len(resources) > 0 else None
                audio = self._toResourceTaskOptions(resources[1]) if len(resources) > 1 else None
                return MergeTaskOptions(
                    url=video.url if video else "",
                    outputFolder=outputFolder,
                    video=video,
                    audio=audio,
                )
            case TaskSource.PAGE_MEDIA:
                return PageTaskOptions(
                    url=toStr(payload, "url"),
                    outputFolder=outputFolder,
                    pageUrl=toStr(payload, "pageUrl"),
                    pageTitle=toStr(payload, "pageTitle"),
                    headers=payload.get("headers") or {},
                )
            case TaskSource.RESOURCE | TaskSource.DOWNLOAD:
                return replace(
                    self._toResourceTaskOptions(payload),
                    outputFolder=outputFolder,
                    subworkerCount=toInt(payload, "preBlockNum", cfg.preBlockNum.value),
                )
            case _:
                raise ValueError(f"unsupported task source: {source}")

    def _toTaskSummary(self, task: Task) -> dict:
        progress, speed, receivedBytes = task.currentSnapshot()
        outputPath = Path(task.outputPath)
        return {
            "taskId": task.taskId,
            "name": task.name,
            "status": task.status.name.lower(),
            "progress": round(progress, 2),
            "receivedBytes": receivedBytes,
            "fileSize": task.fileSize,
            "speed": speed,
            "createdAt": task.createdAt,
            "canPause": task.canPause,
            "canOpenFile": outputPath.exists(),
            "canOpenFolder": outputPath.parent.exists(),
            "fileExt": outputPath.suffix.lstrip(".").lower(),
            "packName": task.packId,
        }

    def _closeAll(self) -> None:
        hadAuthenticated = any(s.isAuthenticated for s in self._sessions.values())
        for session in list(self._sessions.values()):
            session.socket.close()
            self._deleteSocket(session.socket)
        self._sessions.clear()
        if hadAuthenticated:
            self.connectionChanged.emit()

    def _deleteSocket(self, socket: QWebSocket) -> None:
        try:
            socket.disconnected.disconnect(self._onDisconnected)
        except (RuntimeError, TypeError):
            pass
        socket.deleteLater()

    def _send(self, session: BrowserClientSession, payload: dict) -> None:
        try:
            session.socket.sendTextMessage(json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            logger.opt(exception=e).warning("Failed to send browser payload")

    def _sendError(self, session: BrowserClientSession, message: str, *,
                   requestId: str | None = None, code: ErrorCode = ErrorCode.BAD_REQUEST) -> None:
        payload: dict[str, Any] = {"type": MessageType.ERROR, "message": message, "code": code}
        if requestId:
            payload["requestId"] = requestId
        self._send(session, payload)

    def _sendResult(self, session: BrowserClientSession, messageType: MessageType,
                    requestId: str, *, ok: bool, message: str = "", taskId: str = "") -> None:
        payload: dict[str, Any] = {"type": messageType, "requestId": requestId, "ok": ok}
        if message:
            payload["message"] = message
        if taskId:
            payload["taskId"] = taskId
        self._send(session, payload)

    def _sendCreateTaskResult(self, session: BrowserClientSession, requestId: str,
                              status: CreateTaskStatus, *,
                              taskId: str = "", message: str = "") -> None:
        payload: dict[str, Any] = {
            "type": MessageType.CREATE_TASK_RESULT,
            "requestId": requestId,
            "status": status,
        }
        if taskId:
            payload["taskId"] = taskId
        if message:
            payload["message"] = message
        self._send(session, payload)

    @Slot()
    def _onNewConnection(self) -> None:
        socket = self._server.nextPendingConnection()
        if socket is None:
            return
        self._sessions[id(socket)] = BrowserClientSession(socket=socket)
        socket.textMessageReceived.connect(self._onMessage)
        socket.disconnected.connect(self._onDisconnected)

    @Slot()
    def _onDisconnected(self) -> None:
        socket: QWebSocket = self.sender()
        if not socket:
            return
        session = self._sessions.pop(id(socket), None)
        wasAuthenticated = session.isAuthenticated if session else False
        self._deleteSocket(socket)
        if wasAuthenticated:
            self.connectionChanged.emit()

    @Slot()
    def _broadcastSnapshots(self) -> None:
        if not self._sessions:
            return
        tasks = sorted(taskService.tasks, key=lambda t: t.createdAt, reverse=True)
        snapshot = json.dumps({
            "type": MessageType.TASK_SNAPSHOT,
            "tasks": [self._toTaskSummary(t) for t in tasks],
        }, ensure_ascii=False)

        for session in list(self._sessions.values()):
            if not session.isAuthenticated or not session.isSubscribedToTasks:
                continue
            if session.lastSnapshot == snapshot:
                continue
            session.lastSnapshot = snapshot
            try:
                session.socket.sendTextMessage(snapshot)
            except Exception as e:
                logger.opt(exception=e).warning("Failed to push task snapshot")

    @Slot(str)
    def _onMessage(self, message: str) -> None:
        socket: QWebSocket = self.sender()
        session = self._sessions.get(id(socket)) if socket else None
        if session is None:
            return

        try:
            data = json.loads(message)
        except Exception:
            self._sendError(session, "无效的消息格式")
            return

        if not isinstance(data, dict):
            self._sendError(session, "无效的消息结构")
            return

        rawType = toStr(data, "type")
        try:
            msgType = MessageType(rawType)
        except ValueError:
            self._sendError(session, "未知的消息类型")
            return

        if msgType == MessageType.PAIR_REQUEST:
            self.pairRequested.emit({
                "session": session,
                "requestId": toStr(data, "requestId"),
                "protocolVersion": data.get("protocolVersion"),
                "peerAddress": f"{session.socket.peerAddress().toString()}:{session.socket.peerPort()}",
                "extensionVersion": toStr(data, "extensionVersion"),
                "clientKind": toStr(data, "clientKind"),
            })
            return

        if msgType == MessageType.HELLO:
            self._onHello(session, data)
            return

        if not session.isAuthenticated:
            self._sendError(session, "请先完成握手认证", code=ErrorCode.UNAUTHORIZED)
            session.socket.close()
            return

        if msgType == MessageType.SUBSCRIBE_TASKS:
            session.isSubscribedToTasks = True
            session.lastSnapshot = None
            self._broadcastSnapshots()
        elif msgType == MessageType.CREATE_TASK:
            self._onCreateTask(session, data)
        elif msgType == MessageType.TASK_ACTION:
            self._onTaskAction(session, data)

    def _onHello(self, session: BrowserClientSession, data: dict) -> None:
        requestId = toStr(data, "requestId") or None

        if toInt(data, "protocolVersion", 0) != PROTOCOL_VERSION:
            self._sendError(session, "协议版本不匹配", requestId=requestId, code=ErrorCode.PROTOCOL_MISMATCH)
            session.socket.close()
            return

        if toStr(data, "token") != self.token:
            self._sendError(session, "配对令牌无效", requestId=requestId, code=ErrorCode.UNAUTHORIZED)
            session.socket.close()
            return

        session.isAuthenticated = True
        session.extensionVersion = toStr(data, "extensionVersion")
        session.installType = toStr(data, "installType")
        self.connectionChanged.emit()

        self._send(session, {
            "type": MessageType.HELLO_ACK,
            "protocolVersion": PROTOCOL_VERSION,
            "appVersion": VERSION,
            "capabilities": {
                "taskSnapshots": True,
                "taskActions": [a.value for a in TaskAction],
            },
        })

        if (session.installType == "development"
                and QVersionNumber.fromString(session.extensionVersion)
                    < QVersionNumber.fromString(LATEST_EXTENSION_VERSION)
                and not self._isUpdatingExtension):
            self._isUpdatingExtension = True
            from app.services.coroutine_runner import coroutineRunner
            coroutineRunner.submit(
                extractBrowserExtension(),
                done=self._onExtensionExtracted,
                failed=self._onExtensionExtractFailed,
                session=session,
            )

    def _onExtensionExtracted(self, _path: Path, session: BrowserClientSession) -> None:
        self._isUpdatingExtension = False
        if id(session.socket) not in self._sessions:
            return
        self._send(session, {"type": MessageType.RELOAD})
        self.extensionUpdated.emit(LATEST_EXTENSION_VERSION)

    def _onExtensionExtractFailed(self, error: str, **_) -> None:
        self._isUpdatingExtension = False
        logger.warning("Browser extension extract failed: {}", error)

    def _onCreateTask(self, session: BrowserClientSession, data: dict) -> None:
        from app.services.coroutine_runner import coroutineRunner
        from app.services.feature_service import featureService

        requestId = toStr(data, "requestId")
        payload = data.get("payload")
        rawSource = toStr(data, "source", TaskSource.RESOURCE)
        title = toStr(data, "title")

        if not requestId or not isinstance(payload, dict):
            self._sendError(session, "无效的请求")
            return

        try:
            source = TaskSource(rawSource)
        except ValueError:
            self._sendError(session, "未知的任务来源")
            return

        try:
            options = self._toTaskOptions(source, payload)
        except Exception as e:
            self._sendCreateTaskResult(session, requestId, CreateTaskStatus.REJECTED, message=repr(e))
            return

        coroutineRunner.submit(
            featureService.parse(options),
            done=self._onTaskParsed,
            failed=self._onTaskParseFailed,
            session=session, requestId=requestId, source=source, title=title,
        )

    def _onTaskParsed(self, task: Task, session: BrowserClientSession, requestId: str,
                      source: TaskSource, title: str) -> None:
        if title:
            task.setName(title)

        isInteractive = source != TaskSource.DOWNLOAD
        if isInteractive and cfg.shouldRaiseWindowOnBrowserTask.value:
            self._sendCreateTaskResult(session, requestId, CreateTaskStatus.DRAFTED)
            self.taskDraftRequested.emit([task])
            return

        taskService.add(task)
        self._sendCreateTaskResult(session, requestId, CreateTaskStatus.CREATED, taskId=task.taskId)
        self._broadcastSnapshots()

    def _onTaskParseFailed(self, error: str, session: BrowserClientSession, requestId: str, **_) -> None:
        self._sendCreateTaskResult(session, requestId, CreateTaskStatus.REJECTED, message=error)

    def _onTaskAction(self, session: BrowserClientSession, data: dict) -> None:
        from app.models.task import TaskStatus
        from app.platform.desktop import requestForeground, openFile, revealInFolder

        requestId = toStr(data, "requestId")
        taskId = toStr(data, "taskId")
        rawAction = toStr(data, "action")

        if not requestId:
            self._sendError(session, "缺少 requestId")
            return

        try:
            action = TaskAction(rawAction)
        except ValueError:
            self._sendResult(session, MessageType.TASK_ACTION_RESULT, requestId, ok=False, message="不支持的操作")
            return

        task = taskService.taskById(taskId)
        if task is None:
            self._sendResult(session, MessageType.TASK_ACTION_RESULT, requestId, ok=False, message="任务不存在")
            return

        try:
            if action == TaskAction.TOGGLE_PAUSE:
                if task.status == TaskStatus.RUNNING:
                    if not task.canPause:
                        self._sendResult(session, MessageType.TASK_ACTION_RESULT, requestId,
                                         ok=False, message="当前任务不支持暂停")
                        return
                    taskService.pause(task)
                elif task.status == TaskStatus.COMPLETED:
                    self._sendResult(session, MessageType.TASK_ACTION_RESULT, requestId,
                                     ok=False, message="任务已完成")
                    return
                else:
                    taskService.start(task)

            elif action == TaskAction.CANCEL:
                taskService.delete(task, shouldDeleteFiles=True)

            elif action == TaskAction.REDOWNLOAD:
                taskService.redownload(task)

            elif action == TaskAction.OPEN_FILE:
                path = Path(task.outputPath)
                if not path.exists():
                    self._sendResult(session, MessageType.TASK_ACTION_RESULT, requestId,
                                     ok=False, message="文件尚未生成")
                    return
                requestForeground()
                openFile(path)

            elif action == TaskAction.OPEN_FOLDER:
                path = Path(task.outputPath)
                if not path.parent.exists():
                    self._sendResult(session, MessageType.TASK_ACTION_RESULT, requestId,
                                     ok=False, message="目录不存在")
                    return
                requestForeground()
                revealInFolder(path)

            self._sendResult(session, MessageType.TASK_ACTION_RESULT, requestId, ok=True)
            self._broadcastSnapshots()

        except Exception as e:
            logger.opt(exception=e).error("Browser task action failed")
            self._sendResult(session, MessageType.TASK_ACTION_RESULT, requestId, ok=False, message=repr(e))


browserService = BrowserService()
