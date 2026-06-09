import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from RinUI import RinUIWindow

from app.engine.downloads import Downloads
from app.engine.engine import Engine
from app.engine.store import Store
from app.gui.backend import Backend
from app.gui.task_list import TaskFilter, TaskList
from app.protocol.link import MemoryLink

QML_DIR = Path(__file__).parent / "qml"


class MainWindow(RinUIWindow):
    """Ghost Downloader 的 gui 壳：建好 gui↔engine 脉，把 backend / taskList 暴露给 QML。"""

    def __init__(self) -> None:
        super().__init__()
        self._link = MemoryLink()
        # 同进程的下载 engine（缝先行）；注意它与 RinUI 的 self.engine（QML 引擎）不是一回事
        self._engine = Engine(self._link, Downloads(), Store())
        self._taskList = TaskList()
        self._taskFilter = TaskFilter(self._taskList)
        self._backend = Backend(self._link, self._taskList)
        self._link.connect(self._engine.receive, self._backend.receive)

        context = self.engine.rootContext()
        context.setContextProperty("backend", self._backend)
        context.setContextProperty("taskFilter", self._taskFilter)

        self.load(str(QML_DIR / "Main.qml"))
        self._backend.attach()


def main() -> int:
    app = QApplication(sys.argv)
    from app.services.core_service import coreService
    from app.services.feature_service import featureService

    coreService.start()
    featureService.load(None)  # 加载所有 pack 的 matches/parse（跳过 UI setup）
    window = MainWindow()
    code = app.exec()
    coreService.stop()
    return code


if __name__ == "__main__":
    sys.exit(main())
