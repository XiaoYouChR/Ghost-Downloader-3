from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self
from secrets import token_urlsafe

from PySide6.QtCore import QObject, QTimer, Slot
from PySide6.QtNetwork import QHostAddress
from PySide6.QtWebSockets import QWebSocketServer
from loguru import logger
from orjson import dumps, loads

from app.bases.models import Task, TaskStatus
from app.services.core_service import coreService
from app.supports.config import VERSION, cfg
from app.supports.recorder import taskRecorder
from app.supports.signal_bus import signalBus
from app.supports.utils import getProxies, openFile, openFolder

if TYPE_CHECKING:
    from PySide6.QtWebSockets import QWebSocket

    from app.view.windows.main_window import MainWindow


@dataclass
class _BrowserClientSession:
    socket: "QWebSocket"
    authenticated: bool = False
    subscribedTasks: bool = False
    lastTaskSnapshot: bytes | None = None


class BrowserMessageType(StrEnum):
    ERROR = "error"
    HELLO = "hello"
    HELLO_ACK = "hello_ack"
    SUBSCRIBE_TASKS = "subscribe_tasks"
    TASK_SNAPSHOT = "task_snapshot"
    CREATE_TASK = "create_task"
    CREATE_TASK_RESULT = "create_task_result"
    TASK_ACTION = "task_action"
    TASK_ACTION_RESULT = "task_action_result"


class BrowserErrorCode(StrEnum):
    BAD_REQUEST = "bad_request"
    PROTOCOL_MISMATCH = "protocol_mismatch"
    UNAUTHORIZED = "unauthorized"


class BrowserTaskAction(StrEnum):
    TOGGLE_PAUSE = "toggle_pause"
    CANCEL = "cancel"
    REDOWNLOAD = "redownload"
    OPEN_FILE = "open_file"
    OPEN_FOLDER = "open_folder"


class BrowserTaskSource(StrEnum):
    DOWNLOAD = "download"
    RESOURCE = "resource"
    RESOURCE_MERGE = "resource_merge"


class BrowserVirtualUrl(StrEnum):
    FFMPEG_MERGE = "gd3+ffmpeg://merge"


class BrowserService(QObject):
    _instance: Self | None = None
    SERVER_HOST = QHostAddress.SpecialAddress.LocalHost
    SERVER_PORT = 14370
    PROTOCOL_VERSION = 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mainWindow: "MainWindow" = parent
        self.server = QWebSocketServer(
            "Ghost Downloader Browser Socket Server",
            QWebSocketServer.SslMode.NonSecureMode,
            parent,
        )
        self.server.newConnection.connect(self._onNewConnection)
        self._clientSessions: dict[int, _BrowserClientSession] = {}
        self._snapshotTimer = QTimer(self)
        self._snapshotTimer.setInterval(1000)
        self._snapshotTimer.timeout.connect(self._broadcastTaskSnapshots)
        self._snapshotTimer.start()

        self._ensurePairToken()
        cfg.enableBrowserExtension.valueChanged.connect(self._syncEnabled)
        self._syncEnabled(cfg.enableBrowserExtension.value)

    def _ensurePairToken(self):
        if cfg.browserExtensionPairToken.value:
            return

        cfg.set(cfg.browserExtensionPairToken, token_urlsafe(16))

    @property
    def pairToken(self) -> str:
        self._ensurePairToken()
        return str(cfg.browserExtensionPairToken.value)

    def regeneratePairToken(self) -> str:
        token = token_urlsafe(16)
        cfg.set(cfg.browserExtensionPairToken, token)
        self._closeAllClients()
        return token

    @classmethod
    def initialize(cls, parent=None) -> Self:
        if cls._instance is None:
            cls._instance = cls(parent)

        return cls._instance

    @classmethod
    def instance(cls) -> Self:
        if cls._instance is None:
            raise RuntimeError("BrowserService has not been initialized")

        return cls._instance

    def _sessionKey(self, socket: "QWebSocket") -> int:
        return id(socket)

    def _getSession(self, socket: "QWebSocket | None") -> _BrowserClientSession | None:
        if socket is None:
            return None
        return self._clientSessions.get(self._sessionKey(socket))

    def _closeAllClients(self):
        for session in list(self._clientSessions.values()):
            session.socket.close()
        self._clientSessions.clear()

    @Slot(bool)
    def _syncEnabled(self, enabled: bool):
        if enabled:
            if self.server.isListening():
                return

            if self.server.listen(self.SERVER_HOST, self.SERVER_PORT):
                logger.info(
                    "Browser extension server started on ws://{}:{}",
                    self.server.serverAddress().toString(),
                    self.server.serverPort(),
                )
                return

            error = RuntimeError(self.server.errorString())
            logger.opt(exception=error).error("Failed to start browser extension server")
            return

        self._closeAllClients()
        if self.server.isListening():
            self.server.close()
            logger.info("Browser extension server stopped")

    @Slot()
    def _onNewConnection(self):
        socket = self.server.nextPendingConnection()
        if socket is None:
            return

        session = _BrowserClientSession(socket=socket)
        self._clientSessions[self._sessionKey(socket)] = session

        socket.textMessageReceived.connect(self._onReceiveMessage)
        socket.disconnected.connect(self._onClientDisconnected)
        logger.debug("Browser client connected: {}:{}", socket.peerAddress().toString(), socket.peerPort())

    @Slot()
    def _onClientDisconnected(self):
        socket: "QWebSocket" = self.sender()
        if socket is None:
            return

        self._clientSessions.pop(self._sessionKey(socket), None)
        logger.debug("Browser client disconnected: {}:{}", socket.peerAddress().toString(), socket.peerPort())

    def _send(self, session: _BrowserClientSession, payload: dict[str, Any]):
        try:
            session.socket.sendTextMessage(dumps(payload).decode("utf-8"))
        except Exception as error:
            logger.opt(exception=error).warning("Failed to send browser payload {}", payload.get("type"))

    def _sendError(
        self,
        session: _BrowserClientSession,
        message: str,
        *,
        requestId: str | None = None,
        code: BrowserErrorCode = BrowserErrorCode.BAD_REQUEST,
    ):
        payload: dict[str, Any] = {
            "type": BrowserMessageType.ERROR,
            "message": message,
            "code": code,
        }
        if requestId:
            payload["requestId"] = requestId
        self._send(session, payload)

    @staticmethod
    def _stringField(data: dict[str, Any], key: str, default: str = "") -> str:
        value = data.get(key)
        return value if isinstance(value, str) else default

    @staticmethod
    def _positiveIntField(data: dict[str, Any], key: str, default: int) -> int:
        value = data.get(key)
        return value if isinstance(value, int) and value > 0 else default

    def _serializeTask(self, task: Task) -> dict[str, Any]:
        resolvePath = Path(task.resolvePath)
        parentPath = resolvePath.parent
        stages = task.stages
        progress = (
            100.0 if task.status == TaskStatus.COMPLETED else 0.0
        ) if not stages else sum(stage.progress for stage in stages) / len(stages)
        packName = next((part for part in task.__module__.split(".") if part.endswith("_pack")), "")
        return {
            "taskId": task.taskId,
            "title": task.title,
            "status": task.status.name.lower(),
            "progress": round(progress, 2),
            "receivedBytes": sum(stage.receivedBytes for stage in stages),
            "fileSize": int(task.fileSize),
            "speed": sum(stage.speed for stage in stages),
            "createdAt": task.createdAt,
            "resolvePath": str(resolvePath),
            "parentPath": str(parentPath),
            "canPause": bool(task.canPause()),
            "canOpenFile": resolvePath.exists(),
            "canOpenFolder": parentPath.exists(),
            "fileExt": resolvePath.suffix.lstrip(".").lower(),
            "packName": packName,
        }

    def _allTrackedTasks(self) -> list[Task]:
        tasksById: dict[str, Task] = {
            task.taskId: task for task in taskRecorder.memorizedTasks.values()
        }
        for task in coreService.getAllTaskInfo():
            tasksById[task.taskId] = task
        return list(tasksById.values())

    def _findTrackedTask(self, taskId: str) -> Task | None:
        task = coreService.getTaskById(taskId)
        if task is not None:
            return task
        return taskRecorder.memorizedTasks.get(taskId)

    def _buildTaskSnapshot(self) -> bytes:
        tasks = sorted(self._allTrackedTasks(), key=lambda item: item.createdAt, reverse=True)
        return dumps(
            {
                "type": BrowserMessageType.TASK_SNAPSHOT,
                "tasks": [self._serializeTask(task) for task in tasks],
            }
        )

    @Slot()
    def _broadcastTaskSnapshots(self):
        if not self._clientSessions:
            return

        snapshot = self._buildTaskSnapshot()
        for session in list(self._clientSessions.values()):
            if not session.authenticated or not session.subscribedTasks:
                continue
            if session.lastTaskSnapshot == snapshot:
                continue

            session.lastTaskSnapshot = snapshot
            try:
                session.socket.sendTextMessage(snapshot.decode("utf-8"))
            except Exception as error:
                logger.opt(exception=error).warning("Failed to push browser task snapshot")

    def _buildParsePayload(self, rawPayload: dict[str, Any]) -> dict[str, Any]:
        rawPath = rawPayload.get("path")
        return {
            "url": self._stringField(rawPayload, "url"),
            "headers": rawPayload.get("headers") or {},
            "filename": self._stringField(rawPayload, "filename"),
            "size": self._positiveIntField(rawPayload, "size", 0),
            "supportsRange": bool(rawPayload.get("supportsRange")),
            "proxies": getProxies(),
            "path": Path(rawPath) if rawPath else Path(cfg.downloadFolder.value),
            "preBlockNum": self._positiveIntField(rawPayload, "preBlockNum", cfg.preBlockNum.value),
        }

    def _buildMergePayload(self, rawPayload: dict[str, Any]) -> dict[str, Any]:
        rawPath = rawPayload.get("path")
        return {
            "url": BrowserVirtualUrl.FFMPEG_MERGE,
            "outputTitle": self._stringField(rawPayload, "outputTitle"),
            "resources": rawPayload.get("resources") or [],
            "proxies": getProxies(),
            "path": Path(rawPath) if rawPath else Path(cfg.downloadFolder.value),
            "preBlockNum": self._positiveIntField(rawPayload, "preBlockNum", cfg.preBlockNum.value),
        }

    def _sendResult(
        self,
        session: _BrowserClientSession,
        messageType: BrowserMessageType,
        requestId: str,
        *,
        ok: bool,
        message: str = "",
        taskId: str = "",
    ):
        payload: dict[str, Any] = {
            "type": messageType,
            "requestId": requestId,
            "ok": ok,
        }
        if message:
            payload["message"] = message
        if taskId:
            payload["taskId"] = taskId
        self._send(session, payload)

    def _onTaskParsed(
        self,
        session: _BrowserClientSession,
        requestId: str,
        title: str,
        task: Task | None,
        error: str | None,
    ):
        if error or task is None:
            logger.warning("Browser task parse failed: {}", error or "unknown error")
            self._sendResult(
                session,
                BrowserMessageType.CREATE_TASK_RESULT,
                requestId,
                ok=False,
                message=error or self.tr("无法解析该链接"),
            )
            return

        if title:
            task.setTitle(title)

        if not self.mainWindow.addTask(task):
            self._sendResult(
                session,
                BrowserMessageType.CREATE_TASK_RESULT,
                requestId,
                ok=False,
                message=self.tr("创建任务失败"),
            )
            return

        if cfg.enableRaiseWindowWhenReceiveMsg.value:
            signalBus.showMainWindow.emit()

        self._sendResult(session, BrowserMessageType.CREATE_TASK_RESULT, requestId, ok=True, taskId=task.taskId)
        self._broadcastTaskSnapshots()

    def _handleCreateTask(self, session: _BrowserClientSession, data: dict[str, Any]):
        requestId = self._stringField(data, "requestId")
        payload = data.get("payload")
        rawSource = self._stringField(data, "source", BrowserTaskSource.RESOURCE)
        title = self._stringField(data, "title")
        if not requestId:
            self._sendError(session, self.tr("缺少 requestId"))
            return
        if not isinstance(payload, dict):
            self._sendResult(
                session,
                BrowserMessageType.CREATE_TASK_RESULT,
                requestId,
                ok=False,
                message=self.tr("无效的任务负载"),
            )
            return

        try:
            source = BrowserTaskSource(rawSource)
        except ValueError:
            source = BrowserTaskSource.RESOURCE

        if source == BrowserTaskSource.RESOURCE_MERGE:
            mergePayload = self._buildMergePayload(payload)
            mergePayload["outputTitle"] = title
            if len(mergePayload["resources"]) != 2:
                self._sendResult(
                    session,
                    BrowserMessageType.CREATE_TASK_RESULT,
                    requestId,
                    ok=False,
                    message=self.tr("在线合并暂时只支持 2 个资源"),
                )
                return

            coreService.runCoroutine(
                coreService._parseUrl(mergePayload),
                lambda task, error, session=session, requestId=requestId: self._onTaskParsed(
                    session,
                    requestId,
                    "",
                    task,
                    error,
                ),
            )
            return

        parsePayload = self._buildParsePayload(payload)
        if not parsePayload["url"]:
            self._sendResult(
                session,
                BrowserMessageType.CREATE_TASK_RESULT,
                requestId,
                ok=False,
                message=self.tr("缺少下载链接"),
            )
            return

        coreService.runCoroutine(
            coreService._createTaskFromPayload(parsePayload),
            lambda task, error, session=session, requestId=requestId, title=title: self._onTaskParsed(
                session,
                requestId,
                title,
                task,
                error,
            ),
        )

    def _handleRemoveTaskFinished(
        self,
        session: _BrowserClientSession,
        requestId: str,
        task: Task,
        error: str | None,
    ):
        if error:
            self._sendResult(
                session,
                BrowserMessageType.TASK_ACTION_RESULT,
                requestId,
                ok=False,
                message=error,
            )
            return

        card = self.mainWindow.taskPage.findCardByTaskId(task.taskId)
        if card is not None:
            card.deleted.emit()
            card.onTaskDeleted(True)
        else:
            taskRecorder.remove(task)
            taskRecorder.flush()
            self._removeTaskArtifacts(task)

        self._sendResult(session, BrowserMessageType.TASK_ACTION_RESULT, requestId, ok=True)
        self._broadcastTaskSnapshots()

    def _removeTaskArtifacts(self, task: Task):
        candidates: set[Path] = set()
        if task.resolvePath:
            candidates.add(Path(task.resolvePath))

        for stage in task.stages:
            try:
                resolvePath = stage.resolvePath
            except AttributeError:
                continue
            if resolvePath:
                candidates.add(Path(resolvePath))

        for target in candidates:
            for path in (target, Path(str(target) + ".ghd")):
                try:
                    if path.is_file() or path.is_symlink():
                        path.unlink()
                except FileNotFoundError:
                    continue
                except PermissionError:
                    logger.warning("skip removing busy file {}", path)
                except Exception as error:
                    logger.opt(exception=error).error("failed to remove task file {}", path)

    def _handleRedownloadFinished(
        self,
        session: _BrowserClientSession,
        requestId: str,
        task: Task,
        error: str | None,
    ):
        if error:
            self._sendResult(
                session,
                BrowserMessageType.TASK_ACTION_RESULT,
                requestId,
                ok=False,
                message=error,
            )
            return

        try:
            card = self.mainWindow.taskPage.findCardByTaskId(task.taskId)
            if card is not None:
                card.onTaskDeleted(True)
            else:
                self._removeTaskArtifacts(task)

            task.reset()
            taskRecorder.flush()
            coreService.createTask(task)
        except Exception as actionError:
            logger.opt(exception=actionError).error("Browser task redownload failed")
            self._sendResult(
                session,
                BrowserMessageType.TASK_ACTION_RESULT,
                requestId,
                ok=False,
                message=repr(actionError),
            )
            return

        self._sendResult(session, BrowserMessageType.TASK_ACTION_RESULT, requestId, ok=True)
        self._broadcastTaskSnapshots()

    def _handleTaskAction(self, session: _BrowserClientSession, data: dict[str, Any]):
        requestId = self._stringField(data, "requestId")
        taskId = self._stringField(data, "taskId")
        rawAction = self._stringField(data, "action")

        if not requestId:
            self._sendError(session, self.tr("缺少 requestId"))
            return

        try:
            action = BrowserTaskAction(rawAction)
        except ValueError:
            self._sendResult(
                session,
                BrowserMessageType.TASK_ACTION_RESULT,
                requestId,
                ok=False,
                message=self.tr("不支持的任务操作"),
            )
            return

        task = self._findTrackedTask(taskId)
        if task is None:
            self._sendResult(
                session,
                BrowserMessageType.TASK_ACTION_RESULT,
                requestId,
                ok=False,
                message=self.tr("任务不存在"),
            )
            return

        try:
            if action == BrowserTaskAction.TOGGLE_PAUSE:
                if task.status == TaskStatus.RUNNING:
                    if not task.canPause():
                        self._sendResult(
                            session,
                            BrowserMessageType.TASK_ACTION_RESULT,
                            requestId,
                            ok=False,
                            message=self.tr("当前任务不支持暂停"),
                        )
                        return
                    coreService.stopTask(task)
                elif task.status == TaskStatus.COMPLETED:
                    self._sendResult(
                        session,
                        BrowserMessageType.TASK_ACTION_RESULT,
                        requestId,
                        ok=False,
                        message=self.tr("任务已完成"),
                    )
                    return
                else:
                    coreService.createTask(task)

                self._sendResult(session, BrowserMessageType.TASK_ACTION_RESULT, requestId, ok=True)
                return

            if action == BrowserTaskAction.CANCEL:
                if coreService.getTaskById(task.taskId) is None:
                    self._handleRemoveTaskFinished(session, requestId, task, None)
                    return
                coreService.runCoroutine(
                    coreService._stopTask(task),
                    lambda _result, error, session=session, requestId=requestId, task=task: self._handleRemoveTaskFinished(
                        session,
                        requestId,
                        task,
                        error,
                    ),
                )
                return

            if action == BrowserTaskAction.REDOWNLOAD:
                coreService.runCoroutine(
                    coreService._stopTask(task),
                    lambda _result, error, session=session, requestId=requestId, task=task: self._handleRedownloadFinished(
                        session,
                        requestId,
                        task,
                        error,
                    ),
                )
                return

            if action == BrowserTaskAction.OPEN_FILE:
                path = Path(task.resolvePath)
                if not path.exists():
                    self._sendResult(
                        session,
                        BrowserMessageType.TASK_ACTION_RESULT,
                        requestId,
                        ok=False,
                        message=self.tr("文件尚未生成"),
                    )
                    return
                openFile(path)
                self._sendResult(session, BrowserMessageType.TASK_ACTION_RESULT, requestId, ok=True)
                return

            if action == BrowserTaskAction.OPEN_FOLDER:
                path = Path(task.resolvePath)
                if not path.parent.exists():
                    self._sendResult(
                        session,
                        BrowserMessageType.TASK_ACTION_RESULT,
                        requestId,
                        ok=False,
                        message=self.tr("目录不存在"),
                    )
                    return
                openFolder(path)
                self._sendResult(session, BrowserMessageType.TASK_ACTION_RESULT, requestId, ok=True)
                return
        except Exception as error:
            logger.opt(exception=error).error("Browser task action failed")
            self._sendResult(
                session,
                BrowserMessageType.TASK_ACTION_RESULT,
                requestId,
                ok=False,
                message=repr(error),
            )

    @Slot(str)
    def _onReceiveMessage(self, message: str):
        socket: "QWebSocket" = self.sender()
        session = self._getSession(socket)
        if session is None:
            return

        try:
            data = loads(message)
        except Exception as error:
            logger.opt(exception=error).warning("Invalid browser message payload")
            self._sendError(session, self.tr("无效的消息格式"))
            return

        if not isinstance(data, dict):
            self._sendError(session, self.tr("无效的消息结构"))
            return

        rawMessageType = self._stringField(data, "type")
        try:
            messageType = BrowserMessageType(rawMessageType)
        except ValueError:
            self._sendError(session, self.tr("未知的消息类型"))
            return

        if messageType == BrowserMessageType.HELLO:
            requestId = self._stringField(data, "requestId") or None
            if int(data.get("protocolVersion") or 0) != self.PROTOCOL_VERSION:
                self._sendError(
                    session,
                    self.tr("协议版本不匹配"),
                    requestId=requestId,
                    code=BrowserErrorCode.PROTOCOL_MISMATCH,
                )
                session.socket.close()
                return

            token = self._stringField(data, "token")
            if token != self.pairToken:
                self._sendError(
                    session,
                    self.tr("配对令牌无效"),
                    requestId=requestId,
                    code=BrowserErrorCode.UNAUTHORIZED,
                )
                session.socket.close()
                return

            session.authenticated = True
            self._send(
                session,
                {
                    "type": BrowserMessageType.HELLO_ACK,
                    "protocolVersion": self.PROTOCOL_VERSION,
                    "appVersion": VERSION,
                    "capabilities": {
                        "taskSnapshots": True,
                        "taskActions": [action.value for action in BrowserTaskAction],
                    },
                },
            )
            return

        if not session.authenticated:
            self._sendError(session, self.tr("请先完成握手认证"), code=BrowserErrorCode.UNAUTHORIZED)
            session.socket.close()
            return

        if messageType == BrowserMessageType.SUBSCRIBE_TASKS:
            session.subscribedTasks = True
            session.lastTaskSnapshot = None
            self._broadcastTaskSnapshots()
            return

        if messageType == BrowserMessageType.CREATE_TASK:
            self._handleCreateTask(session, data)
            return

        if messageType == BrowserMessageType.TASK_ACTION:
            self._handleTaskAction(session, data)
            return

        self._sendError(session, self.tr("未知的消息类型"))
