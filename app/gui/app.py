import os
import subprocess
import sys
import traceback
from pathlib import Path

from loguru import logger

from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
from RinUI import RinUIWindow

from app.engine.daemon import SOCKET_NAME
from app.engine.downloads import Downloads
from app.engine.engine import Engine
from app.engine.settings import makeCfgBackedConfig
from app.engine.store import Store
from app.gui.backend import Backend
from app.gui.browser_service import BrowserService, pairToken
from app.gui.clipboard import ClipboardWatcher
from app.gui.file_icons import FileIconProvider
from app.gui.plan_task import executePlanAction
from app.gui.update_check import UpdateCheck
from app.gui.task_list import TaskFilter, TaskList
from app.protocol.link import MemoryLink
from app.protocol.socket_link import SocketClient
from app.supports.config import cfg

QML_DIR = Path(__file__).parent / "qml"
LOGO = Path(__file__).parent.parent / "assets" / "logo.png"


def _daemonReachable() -> bool:
    # 探一下本地 socket：连得上说明已有 daemon 在跑（gui 重启/掉线时据此决定要不要再起一个）
    probe = QLocalSocket()
    probe.connectToServer(SOCKET_NAME)
    if probe.waitForConnected(200):
        probe.disconnectFromServer()
        return True
    return False


def _launchDaemon() -> None:
    # detached 启动后台下载进程，让它在 gui 退出后继续下载（省内存）
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
            if not _daemonReachable():
                _launchDaemon()
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

        # RinUIWindow 不是 QObject，不能作 parent；ref 自留保活。仅构造、不触网——触发在 main() 编排
        self._updateCheck = UpdateCheck()
        self._updateCheck.checked.connect(self._onUpdateChecked)

        # 计划任务：全部完成时 backend 发 planActionReady → 这里执行关机/重启/打开（gui 端 OS 动作，不过缝）
        self._backend.planActionReady.connect(executePlanAction)

        # 浏览器扩展桥：本机 WebSocket，扩展发来的下载转成 backend 命令。cfg 开关控起停（gui 端，不过缝）。
        self._browser = BrowserService(self._backend, pairToken())
        self._browser.pairRequested.connect(self._backend.browserPairRequested)  # 配对请求 → QML 弹框
        self._backend.browserPairAnswered.connect(
            lambda approved: self._browser.approvePair() if approved else self._browser.rejectPair())
        cfg.enableBrowserExtension.valueChanged.connect(self._browser.setEnabled)
        self._browser.setEnabled(cfg.enableBrowserExtension.value)

        if daemon:
            self._link.connectToServer()
        else:
            self._backend.attach()

        self.engine.addImageProvider("fileicon", FileIconProvider())  # image://fileicon/<文件名> → 真实 OS 图标
        context = self.engine.rootContext()
        context.setContextProperty("backend", self._backend)
        context.setContextProperty("taskFilter", self._taskFilter)
        context.setContextProperty("taskList", self._taskList)
        self.load(str(QML_DIR / "Main.qml"))
        self._rootWindow = self.engine.rootObjects()[0] if self.engine.rootObjects() else None
        self._tray: QSystemTrayIcon | None = None

    def setupTray(self) -> None:
        # 托盘常驻：关窗即缩进托盘（QApplication 不随末窗关闭退出），左键单击或菜单恢复，菜单可退出。
        QApplication.setQuitOnLastWindowClosed(False)
        self._trayMenu = QMenu()  # ref 自留保活（MainWindow 非 QObject 不能作 parent）
        self._trayMenu.addAction("显示主界面", self._showWindow)
        self._trayMenu.addAction("退出", QApplication.quit)
        self._tray = QSystemTrayIcon(QIcon(str(LOGO)), self.engine)
        self._tray.setToolTip("Ghost Downloader")
        self._tray.setContextMenu(self._trayMenu)
        self._tray.activated.connect(self._onTrayActivated)
        self._tray.show()

    def _showWindow(self) -> None:
        if self._rootWindow is not None:
            self._rootWindow.show()
            self._rootWindow.raise_()
            self._rootWindow.requestActivate()

    def hideWindow(self) -> None:
        if self._rootWindow is not None:
            self._rootWindow.hide()

    def _onTrayActivated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # 左键单击托盘图标
            self._showWindow()

    def _updateClipboardListener(self) -> None:
        # config 到达/变动时按开关挂钩剪贴板（setEnabled 幂等，重复触发无妨）
        self._clipboard.setEnabled(bool(self._backend.configValue("enableClipboardListener")))

    def checkForUpdates(self) -> None:
        self._updateCheck.start()

    def setupExceptionDialog(self) -> None:
        # 主线程未捕获异常：记日志 + 给界面弹摘要提示（不再静默），仍走默认 hook 打印到 stderr
        backend = self._backend

        def hook(excType, value, tb) -> None:
            logger.opt(exception=(excType, value, tb)).error("未捕获的异常")
            backend.exceptionCaught.emit(traceback.format_exception_only(excType, value)[-1].strip())
            sys.__excepthook__(excType, value, tb)

        sys.excepthook = hook

    def _onUpdateChecked(self, state, error: str) -> None:
        # 只在确有新版本时提示；查失败（error）或已是最新都静默
        if state is not None and state.outdated:
            self._backend.updateAvailable.emit(state.latestVersion)

    def _onDaemonLost(self) -> None:
        # daemon 掉线：界面回到“连接中”。掉线也可能是 gui 自己离场而 daemon 还活着，
        # 故探一下、真没了才重起（别重复起一个抢 socket）；SocketClient 随后自己连回来
        self._backend.setDisconnected()
        if not _daemonReachable():
            _launchDaemon()


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
    window.setupTray()
    window.setupExceptionDialog()
    if "--silence" in sys.argv:  # 开机自启带的标志：直接缩进托盘，不弹主界面
        window.hideWindow()
    if cfg.checkUpdateAtStartUp.value:  # 启动查更新：桌面一次性策略，读本地开关（只影响下次启动）
        window.checkForUpdates()
    code = app.exec()

    if not daemon:
        from app.services.core_service import coreService

        coreService.stop()
    return code


if __name__ == "__main__":
    sys.exit(main())
