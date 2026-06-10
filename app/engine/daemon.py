import sys

from PySide6.QtCore import QCoreApplication

from app.engine.downloads import Downloads
from app.engine.engine import Engine
from app.engine.settings import makeCfgBackedConfig
from app.engine.store import Store
from app.protocol.socket_link import SocketServer
from app.services.core_service import coreService
from app.services.feature_service import featureService

SOCKET_NAME = "ghost_downloader_engine"


def main() -> int:
    # 后台下载进程：无 GUI（QCoreApplication），gui 被杀也照常下载、省内存。
    app = QCoreApplication(sys.argv)
    coreService.start()
    featureService.load(None, withSetup=False)  # headless：只要 matches/parse，不跑 GUI setup

    server = SocketServer(SOCKET_NAME)
    engine = Engine(server, Downloads(), Store(), makeCfgBackedConfig())
    server.connect(engine.receive)
    server.listen()
    print(f"engine daemon listening on {SOCKET_NAME}", flush=True)

    code = app.exec()
    coreService.stop()
    return code


if __name__ == "__main__":
    sys.exit(main())
