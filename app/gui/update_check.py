import asyncio

from PySide6.QtCore import QThread, Signal

from app.supports.update import checkUpdate


class UpdateCheck(QThread):
    """gui 端启动时查一次 GitHub 最新版。独立线程跑 async——gui 在 daemon 模式下不起 coreService
    的事件循环，故自带 asyncio.run；结果用跨线程 Signal 回主线程（Signal 正是为真跨线程而用）。
    best-effort：查不动（断网等）就静默放过，不打扰用户。"""

    checked = Signal(object, str)  # UpdateState | None, error

    def run(self) -> None:
        try:
            self.checked.emit(asyncio.run(checkUpdate()), "")
        except Exception as error:  # 网络/解析失败是预期内的，单点兜住、降级为不提示
            self.checked.emit(None, str(error))
