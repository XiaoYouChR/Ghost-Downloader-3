from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtQml import QQmlPropertyMap

from app.gui.autostart import applyAutoRun
from app.gui.file_selection import FileSelection
from app.gui.task_list import TaskItem, TaskList
from app.protocol.link import MemoryLink
from app.protocol.message import Command, Event
from app.supports import utils


class Backend(QObject):
    """gui 调它来支使后台，并把后台发来的 event 落到界面模型上。QML 经 @Slot 调用。"""

    globalSpeedChanged = Signal()
    filesModelChanged = Signal()
    filesRequested = Signal()
    configChanged = Signal()
    hashReady = Signal()
    connectedChanged = Signal()
    taskAddFailed = Signal(str)
    clipboardUrlsDetected = Signal(list)  # 监听剪贴板抓到可下载链接，QML 据此弹新建对话框
    updateAvailable = Signal(str)  # 启动检查发现新版本，QML 据此提示（参数为最新版本号）
    exceptionCaught = Signal(str)  # 未捕获的主线程异常摘要，QML 弹错误提示（完整 traceback 进日志）

    def __init__(self, link: MemoryLink, taskList: TaskList) -> None:
        super().__init__()
        self._link = link
        self._taskList = taskList
        self._globalSpeedText = ""
        self._filesModel: FileSelection | None = None
        self._editingTaskId = ""
        self._configMap = QQmlPropertyMap(self)  # QML 反射式读 backend.config.<key>
        self._hashText = ""
        self._connected = False

    def _config(self) -> QObject:
        return self._configMap

    config = Property(QObject, _config, constant=True)

    def _isConnected(self) -> bool:
        return self._connected

    connected = Property(bool, _isConnected, notify=connectedChanged)

    def _hash(self) -> str:
        return self._hashText

    hashText = Property(str, _hash, notify=hashReady)

    @Slot(str)
    def verifyHash(self, taskId: str) -> None:
        self._hashText = ""
        self.hashReady.emit()
        self._link.toEngine(Command("verifyHash", {"taskId": taskId}))

    def configValue(self, key: str):
        # gui 端（如剪贴板监听）读 config 当前值；以引擎回发的为准，daemon/内存两模式都对
        return self._configMap.value(key)

    @Slot(result="QVariantList")
    def userAgentOptions(self) -> list:
        # 设置页 UA 下拉的选项；选中后经 setConfig("activeUserAgent") 走配置缝（http pack 读 cfg.activeUserAgent）
        from app.supports.config import cfg
        return [{"name": ua["name"], "value": ua["value"]} for ua in cfg.userAgents.value]

    @Slot(str, "QVariant")
    def setConfig(self, key: str, value) -> None:
        if key == "autoRun":
            applyAutoRun(bool(value))  # 写 OS 开机启动项是 gui 端 OS 动作，不过缝（同 openFile/openFolder）
        self._link.toEngine(Command("setConfig", {"key": key, "value": value}))

    def _globalSpeed(self) -> str:
        return self._globalSpeedText

    globalSpeedText = Property(str, _globalSpeed, notify=globalSpeedChanged)

    def _files(self) -> QObject | None:
        return self._filesModel

    filesModel = Property(QObject, _files, notify=filesModelChanged)

    @Slot(str)
    def editFiles(self, taskId: str) -> None:
        self._editingTaskId = taskId
        self._filesModel = FileSelection(self._taskList.filesOf(taskId))
        self.filesModelChanged.emit()
        self.filesRequested.emit()

    @Slot()
    def confirmFiles(self) -> None:
        if self._filesModel is None:
            return
        indexes = self._filesModel.selectedIndexes()
        self._link.toEngine(Command("setSelection", {"taskId": self._editingTaskId, "indexes": indexes}))

    @Slot()
    def attach(self) -> None:
        self._connected = True
        self.connectedChanged.emit()
        self._link.toEngine(Command("attach"))

    def setDisconnected(self) -> None:
        # daemon 掉线：界面回到“连接后台中…”，SocketClient 会自己重连后重新 attach
        self._connected = False
        self.connectedChanged.emit()

    @Slot()
    def detach(self) -> None:
        self._link.toEngine(Command("detach"))

    @Slot(str)
    def addTask(self, url: str) -> None:
        self._link.toEngine(Command("addTask", {"url": url}))

    @Slot(str, "QVariant")
    def addTaskWithOptions(self, url: str, options) -> None:
        # 「新建任务」对话框：带 path/线程等选项；引擎合进 parse payload
        self._link.toEngine(Command("addTask", {"url": url, "options": dict(options)}))

    @Slot(str, "QVariant")
    def editTask(self, taskId: str, options) -> None:
        # 「编辑任务」对话框：改链接后引擎按新 url 重解析、替换该任务（保留 id/目录）
        self._link.toEngine(Command("editTask", {"taskId": taskId, "options": dict(options)}))

    @Slot(str)
    def pause(self, taskId: str) -> None:
        self._link.toEngine(Command("pause", {"taskId": taskId}))

    @Slot(str)
    def resume(self, taskId: str) -> None:
        self._link.toEngine(Command("resume", {"taskId": taskId}))

    @Slot(str)
    def toggle(self, taskId: str) -> None:
        self._link.toEngine(Command("toggle", {"taskId": taskId}))

    @Slot(str)
    def primaryAction(self, taskId: str) -> None:
        # 卡片主按钮的统一意图；引擎按 pack 声明的 actionKind 决定（toggle 或 直播 finalize）
        self._link.toEngine(Command("primaryAction", {"taskId": taskId}))

    @Slot()
    def startAll(self) -> None:
        self._link.toEngine(Command("startAll"))

    @Slot()
    def pauseAll(self) -> None:
        self._link.toEngine(Command("pauseAll"))

    @Slot(str)
    def remove(self, taskId: str) -> None:
        self._link.toEngine(Command("remove", {"taskId": taskId}))

    @Slot()
    def removeSelected(self) -> None:
        for taskId in self._taskList.selectedIds():
            self._link.toEngine(Command("remove", {"taskId": taskId}))
        self._taskList.setSelectionMode(False)

    @Slot()
    def clearCompleted(self) -> None:
        self._link.toEngine(Command("clearCompleted"))

    @Slot(str, str)
    def rename(self, taskId: str, title: str) -> None:
        self._link.toEngine(Command("rename", {"taskId": taskId, "title": title}))

    @Slot(str)
    def openFile(self, path: str) -> None:
        # 打开下载好的文件是 gui 端的 OS 动作，不过缝
        utils.openFile(path)

    @Slot(str)
    def openFolder(self, path: str) -> None:
        utils.openFolder(path)

    def receive(self, event: Event) -> None:
        if event.name == "snapshot":
            self._taskList.reset(event.data["tasks"])
        elif event.name == "taskAdded":
            self._taskList.add(TaskItem(event.data["task"]))
        elif event.name == "taskChanged":
            self._taskList.update(event.data["task"])
        elif event.name == "taskRemoved":
            self._taskList.remove(event.data["taskId"])
        elif event.name == "stats":
            speed = event.data["globalSpeed"]
            self._globalSpeedText = f"{utils.toReadableSize(speed)}/s" if speed else ""
            self.globalSpeedChanged.emit()
        elif event.name == "config":
            for key, value in event.data["values"].items():
                self._configMap.insert(key, value)  # 反射式：QML 绑 backend.config.<key> 自动刷新
            self.configChanged.emit()
        elif event.name == "hashResult":
            self._hashText = event.data["hash"]
            self.hashReady.emit()
        elif event.name == "addError":
            self.taskAddFailed.emit(event.data["reason"])
