from __future__ import annotations

import asyncio
import json
import socket
import struct
import zipfile
from dataclasses import dataclass, replace
from enum import StrEnum
from io import BytesIO
from pathlib import Path
from secrets import token_urlsafe
from typing import Any, TYPE_CHECKING

import websockets
from loguru import logger

from app.config.cfg import cfg
from app.config.constants import LATEST_EXTENSION_VERSION, VERSION
from app.config.paths import APP_DATA_DIR
from app.signal import Signal
from app.update import isNewer

from app.models.task import MergeTaskOptions, PageTaskOptions

if TYPE_CHECKING:
    from app.models.task import Task, TaskOptions, ResourceTaskOptions

EXTENSION_UNPACK_DIR = APP_DATA_DIR / "browser_extension"


async def extractBrowserExtension(loadCrx) -> Path:
    def _extract() -> Path:
        crxData = loadCrx()

        headerSize = struct.unpack_from("<I", crxData, 8)[0]
        zipOffset = 12 + headerSize

        EXTENSION_UNPACK_DIR.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(BytesIO(crxData[zipOffset:])) as zf:
            zf.extractall(EXTENSION_UNPACK_DIR)

        return EXTENSION_UNPACK_DIR

    return await asyncio.to_thread(_extract)


@dataclass
class BrowserClientSession:
    ws: object
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
    REMOVE = "remove"
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


def toResourceTaskOptions(resource: dict) -> ResourceTaskOptions:
    from app.models.task import ResourceTaskOptions
    hdrs = resource.get("headers") or {}
    return ResourceTaskOptions(
        url=toStr(resource, "url"),
        name=toStr(resource, "filename"),
        size=toInt(resource, "size", 0),
        canUseRangeRequests=bool(resource.get("supportsRange")),
        headers=hdrs,
        sourceUserAgent=hdrs.get("user-agent", ""),
    )


def toTaskOptions(source: TaskSource, payload: dict) -> TaskOptions:
    rawPath = payload.get("path")
    outputFolder = Path(rawPath) if rawPath else Path(cfg.downloadFolder.value)

    match source:
        case TaskSource.RESOURCE_MERGE:
            resources = payload.get("resources") or []
            video = toResourceTaskOptions(resources[0]) if len(resources) > 0 else None
            audio = toResourceTaskOptions(resources[1]) if len(resources) > 1 else None
            return MergeTaskOptions(
                url=video.url if video else "",
                outputFolder=outputFolder,
                video=video,
                audio=audio,
            )
        case TaskSource.PAGE_MEDIA:
            hdrs = payload.get("headers") or {}
            return PageTaskOptions(
                url=toStr(payload, "url"),
                outputFolder=outputFolder,
                pageUrl=toStr(payload, "pageUrl"),
                pageTitle=toStr(payload, "pageTitle"),
                headers=hdrs,
                sourceUserAgent=hdrs.get("user-agent", ""),
            )
        case TaskSource.RESOURCE | TaskSource.DOWNLOAD:
            return replace(
                toResourceTaskOptions(payload),
                outputFolder=outputFolder,
                subworkerCount=toInt(payload, "preBlockNum", cfg.preBlockNum.value),
            )
        case _:
            raise ValueError(f"unsupported task source: {source}")


def toTaskSummary(task: Task) -> dict:
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


class BrowserService:
    pairRequested = Signal(object)
    taskDraftRequested = Signal(list)
    extensionUpdated = Signal(str)
    connectionChanged = Signal()
    protocolMismatched = Signal()

    def __init__(self, coroutineRunner, taskService, parse, loadCrx):
        self._coroutineRunner = coroutineRunner
        self._taskService = taskService
        self._parse = parse
        self._loadCrx = loadCrx
        self._serveWorkId: str | None = None
        self._boundPort = 0
        self._sessions: dict[object, BrowserClientSession] = {}
        self._snapshotWorkId: str | None = None
        self._isUpdatingExtension = False

    @property
    def token(self) -> str:
        if not cfg.browserExtensionPairToken.value:
            cfg.set(cfg.browserExtensionPairToken, token_urlsafe(16))
        return str(cfg.browserExtensionPairToken.value)

    @property
    def isRunning(self) -> bool:
        return self._serveWorkId is not None

    @property
    def boundPort(self) -> int:
        return self._boundPort

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
        if self._serveWorkId is not None:
            return
        port = cfg.browserExtensionPort.value
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(('127.0.0.1', port))
            sock.listen()
        except OSError as e:
            logger.error("Failed to start browser extension server on port {}: {}",
                         port, e)
            sock.close()
            return
        sock.setblocking(False)
        self._boundPort = sock.getsockname()[1]
        self._serveWorkId = self._coroutineRunner.submit(
            self._run(sock), failed=self._onServeFailed)
        logger.info("Browser extension server started on port {}", self._boundPort)
        self._snapshotWorkId = self._coroutineRunner.submit(
            self._broadcastLoop(), failed=self._onBroadcastFailed)

    def stop(self) -> None:
        if self._snapshotWorkId is not None:
            self._coroutineRunner.cancel(self._snapshotWorkId)
            self._snapshotWorkId = None
        self._closeAll()
        if self._serveWorkId is not None:
            self._coroutineRunner.cancel(self._serveWorkId)
            self._serveWorkId = None
        self._boundPort = 0

    def _onServeFailed(self, error) -> None:
        self._serveWorkId = None
        self._boundPort = 0
        if self._snapshotWorkId is not None:
            self._coroutineRunner.cancel(self._snapshotWorkId)
            self._snapshotWorkId = None
        logger.error("Browser extension server crashed: {}", error)

    def _onBroadcastFailed(self, error) -> None:
        self._snapshotWorkId = None
        logger.error("Snapshot broadcast loop crashed: {}", error)

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

    async def _broadcastLoop(self) -> None:
        while True:
            await asyncio.sleep(1)
            self._coroutineRunner.post(self._broadcastSnapshots)

    async def _run(self, sock: socket.socket) -> None:
        try:
            server = await websockets.serve(self._onConnection, sock=sock)
        except Exception:
            sock.close()
            raise
        async with server:
            await server.serve_forever()

    async def _onConnection(self, ws) -> None:
        self._coroutineRunner.post(self._onConnected, ws)
        try:
            async for message in ws:
                self._coroutineRunner.post(self._onMessageReceived, ws, message)
        finally:
            self._coroutineRunner.post(self._onDisconnected, ws)

    def _closeAll(self) -> None:
        hadAuthenticated = any(s.isAuthenticated for s in self._sessions.values())
        for session in list(self._sessions.values()):
            self._coroutineRunner.submit(session.ws.close())
        self._sessions.clear()
        if hadAuthenticated:
            self.connectionChanged.emit()

    def _send(self, session: BrowserClientSession, payload: dict) -> None:
        try:
            data = json.dumps(payload, ensure_ascii=False)
            self._coroutineRunner.submit(session.ws.send(data))
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

    def _onConnected(self, ws) -> None:
        self._sessions[ws] = BrowserClientSession(ws=ws)

    def _onDisconnected(self, ws) -> None:
        session = self._sessions.pop(ws, None)
        if session is None:
            return
        if session.isAuthenticated:
            self.connectionChanged.emit()

    def _broadcastSnapshots(self) -> None:
        if not self._sessions:
            return
        tasks = sorted(self._taskService.tasks, key=lambda t: t.createdAt, reverse=True)
        snapshot = json.dumps({
            "type": MessageType.TASK_SNAPSHOT,
            "tasks": [toTaskSummary(t) for t in tasks],
        }, ensure_ascii=False)

        for session in list(self._sessions.values()):
            if not session.isAuthenticated or not session.isSubscribedToTasks:
                continue
            if session.lastSnapshot == snapshot:
                continue
            session.lastSnapshot = snapshot
            try:
                self._coroutineRunner.submit(session.ws.send(snapshot))
            except Exception as e:
                logger.opt(exception=e).warning("Failed to push task snapshot")

    def _onMessageReceived(self, ws, message: str) -> None:
        session = self._sessions.get(ws)
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
            peerAddress = f"{session.ws.remote_address[0]}:{session.ws.remote_address[1]}"
            self.pairRequested.emit({
                "session": session,
                "requestId": toStr(data, "requestId"),
                "protocolVersion": data.get("protocolVersion"),
                "peerAddress": peerAddress,
                "extensionVersion": toStr(data, "extensionVersion"),
                "clientKind": toStr(data, "clientKind"),
            })
            return

        if msgType == MessageType.HELLO:
            self._onHello(session, data)
            return

        if not session.isAuthenticated:
            self._sendError(session, "请先完成握手认证", code=ErrorCode.UNAUTHORIZED)
            self._coroutineRunner.submit(session.ws.close())
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
            self._coroutineRunner.submit(session.ws.close())
            self.protocolMismatched.emit()
            return

        if toStr(data, "token") != self.token:
            self._sendError(session, "配对令牌无效", requestId=requestId, code=ErrorCode.UNAUTHORIZED)
            self._coroutineRunner.submit(session.ws.close())
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
                and isNewer(session.extensionVersion, LATEST_EXTENSION_VERSION)
                and not self._isUpdatingExtension):
            self._isUpdatingExtension = True
            self._coroutineRunner.submit(
                extractBrowserExtension(self._loadCrx),
                done=self._onExtensionExtracted,
                failed=self._onExtensionExtractFailed,
                session=session,
            )

    def _onExtensionExtracted(self, _path: Path, session: BrowserClientSession) -> None:
        if session.ws not in self._sessions:
            return
        self._send(session, {"type": MessageType.RELOAD})
        self.extensionUpdated.emit(LATEST_EXTENSION_VERSION)

    def _onExtensionExtractFailed(self, error: str, **_) -> None:
        self._isUpdatingExtension = False
        logger.warning("Browser extension extract failed: {}", error)

    def _onCreateTask(self, session: BrowserClientSession, data: dict) -> None:

        requestId = toStr(data, "requestId")
        payload = data.get("payload")
        rawSource = toStr(data, "source", TaskSource.RESOURCE)
        title = toStr(data, "title")
        draft = data.get("draft")

        if not requestId or not isinstance(payload, dict):
            self._sendError(session, "无效的请求")
            return

        try:
            source = TaskSource(rawSource)
        except ValueError:
            self._sendError(session, "未知的任务来源")
            return

        try:
            options = toTaskOptions(source, payload)
        except Exception as e:
            self._sendCreateTaskResult(session, requestId, CreateTaskStatus.REJECTED, message=repr(e))
            return

        decryptionKeys = payload.get("decryptionKeys") or []

        self._coroutineRunner.submit(
            self._parse(options),
            done=self._onTaskParsed,
            failed=self._onTaskParseFailed,
            session=session, requestId=requestId, title=title, draft=draft,
            decryptionKeys=decryptionKeys,
        )

    def _onTaskParsed(self, task: Task, session: BrowserClientSession, requestId: str,
                      title: str, draft: bool | None = None,
                      decryptionKeys: list | None = None) -> None:
        if decryptionKeys and hasattr(task.step, "setOptions"):
            task.step.setOptions({"decryptionKeys": decryptionKeys})

        if title:
            existingSuffix = Path(task.name).suffix
            if existingSuffix and not title.lower().endswith(existingSuffix.lower()):
                task.setName(title + existingSuffix)
            else:
                task.setName(title)

        shouldDraft = draft if draft is not None else cfg.shouldDraftTakenDownload.value
        if shouldDraft:
            self._sendCreateTaskResult(session, requestId, CreateTaskStatus.DRAFTED)
            self.taskDraftRequested.emit([task])
            return

        self._taskService.add(task)
        self._sendCreateTaskResult(session, requestId, CreateTaskStatus.CREATED, taskId=task.taskId)
        self._broadcastSnapshots()

    def _onTaskParseFailed(self, error, session: BrowserClientSession, requestId: str, **_) -> None:
        self._sendCreateTaskResult(session, requestId, CreateTaskStatus.REJECTED, message=str(error))

    def _onTaskAction(self, session: BrowserClientSession, data: dict) -> None:
        from app.models.task import TaskStatus
        from app.platform.desktop import openFile, revealInFolder

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

        task = self._taskService.taskById(taskId)
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
                    self._taskService.pause(task)
                elif task.status == TaskStatus.COMPLETED:
                    self._sendResult(session, MessageType.TASK_ACTION_RESULT, requestId,
                                     ok=False, message="任务已完成")
                    return
                else:
                    self._taskService.start(task)

            elif action == TaskAction.CANCEL:
                self._taskService.delete(task, shouldDeleteFiles=True)

            elif action == TaskAction.REMOVE:
                self._taskService.delete(task, shouldDeleteFiles=False)

            elif action == TaskAction.REDOWNLOAD:
                self._taskService.redownload(task)

            elif action == TaskAction.OPEN_FILE:
                path = Path(task.outputPath)
                if not path.exists():
                    self._sendResult(session, MessageType.TASK_ACTION_RESULT, requestId,
                                     ok=False, message="文件尚未生成")
                    return
                openFile(path)

            elif action == TaskAction.OPEN_FOLDER:
                path = Path(task.outputPath)
                if not path.parent.exists():
                    self._sendResult(session, MessageType.TASK_ACTION_RESULT, requestId,
                                     ok=False, message="目录不存在")
                    return
                revealInFolder(path)

            self._sendResult(session, MessageType.TASK_ACTION_RESULT, requestId, ok=True)
            self._broadcastSnapshots()

        except Exception as e:
            logger.opt(exception=e).error("Browser task action failed")
            self._sendResult(session, MessageType.TASK_ACTION_RESULT, requestId, ok=False, message=repr(e))
