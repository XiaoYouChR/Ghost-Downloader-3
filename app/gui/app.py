import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QApplication
from RinUI import RinUIWindow

from app.engine.daemon import SOCKET_NAME
from app.engine.downloads import Downloads
from app.engine.engine import Engine
from app.engine.settings import makeCfgBackedConfig
from app.engine.store import Store
from app.gui.backend import Backend
from app.gui.clipboard import ClipboardWatcher
from app.gui.task_list import TaskFilter, TaskList
from app.protocol.link import MemoryLink
from app.protocol.socket_link import SocketClient

QML_DIR = Path(__file__).parent / "qml"


def _ensureDaemon() -> None:
    # 已在跑就不重复起；否则 detached 启动，让它在 gui 退出后继续下载（省内存）
    probe = QLocalSocket()
    probe.connectToServer(SOCKET_NAME)
    if probe.waitForConnected(200):
        probe.disconnectFromServer()
        return
    flags = subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0
    subprocess.Popen(
        [sys.executable, "-m", "app.engine.daemon"],
        creationflags=flags,
        start_new_session=sys.platform != "win32",
    )


class MainWindow(RinUIWindow):
    """Ghost Downloader 的 gui 壳。默认同进程跑 engine（MemoryLink）；
    GD_ENGINE=daemon 时作瘦客户端连独立 daemon 进程（SocketClient）。"""

    def __init__(self, daemon: bool = False) -> None:
        super().__init__()
        self._taskList = TaskList()
        self._taskFilter = TaskFilter(self._taskList)

        if daemon:
            _ensureDaemon()
            self._link = SocketClient(SOCKET_NAME)
            self._backend = Backend(self._link, self._taskList)
            self._link.connect(self._backend.receive)
            self._link.whenConnected(self._backend.attach)
            self._link.whenDisconnected(self._onDaemonLost)
        else:
            self._link = MemoryLink()
            self._engine = Engine(self._link, Downloads(), Store(), makeCfgBackedConfig())
            self._backend = Backend(self._link, self._taskList)
            self._link.connect(self._engine.receive, self._backend.receive)

        # 剪贴板监听：桌面 gui 功能，抓到链接转成 backend 信号给 QML 弹新建框。
        # 窗口（仅真 app）持有它，被测的 Backend 不碰系统剪贴板；在 attach 前接好以接住首份 config。
        self._clipboard = ClipboardWatcher(self._backend.clipboardUrlsDetected.emit)
        self._backend.configChanged.connect(self._updateClipboardListener)

        if daemon:
            self._link.connectToServer()
        else:
            self._backend.attach()

        context = self.engine.rootContext()
        context.setContextProperty("backend", self._backend)
        context.setContextProperty("taskFilter", self._taskFilter)
        context.setContextProperty("taskList", self._taskList)
        self.load(str(QML_DIR / "Main.qml"))

    def _updateClipboardListener(self) -> None:
        # config 到达/变动时按开关挂钩剪贴板（setEnabled 幂等，重复触发无妨）
        self._clipboard.setEnabled(bool(self._backend.configValue("enableClipboardListener")))

    def _onDaemonLost(self) -> None:
        # daemon 掉线：界面回到“连接中”，daemon 真没了就重新拉起；SocketClient 随后自己连回来
        self._backend.setDisconnected()
        _ensureDaemon()


def main() -> int:
    app = QApplication(sys.argv)
    daemon = os.environ.get("GD_ENGINE") == "daemon"
    if not daemon:
        from app.services.core_service import coreService
        from app.services.feature_service import featureService

        coreService.start()
        # QML 前端不挂 QFluentWidgets 子界面，跳过各 pack 的 GUI setup（同 daemon）
        featureService.load(None, withSetup=False)

    window = MainWindow(daemon)
    code = app.exec()

    if not daemon:
        from app.services.core_service import coreService

        coreService.stop()
    return code


if __name__ == "__main__":
    sys.exit(main())
