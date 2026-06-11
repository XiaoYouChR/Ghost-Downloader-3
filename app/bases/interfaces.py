from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication

from app.bases.models import TaskStage

if TYPE_CHECKING:
    from app.view.windows.main_window import MainWindow
    from app.view.components.cards import TaskCard
    from app.view.components.cards import ResultCard
    from app.bases.models import Task, PackConfig


@dataclass(frozen=True)
class FileType:
    extensions: tuple[str, ...]
    displayName: str
    mimeType: str
    icon: str


class Worker:
    def __init__(self, stage: TaskStage):
        self.stage = stage

    async def run(self):
        raise NotImplementedError


class FeaturePack:
    packId: str = ""
    priority: int = 0
    config: "PackConfig | None" = None

    def matches(self, url: str) -> bool:
        return False

    async def parse(self, payload: dict) -> "Task":
        raise NotImplementedError

    def taskCard(self, task: "Task", parent=None) -> "TaskCard":
        from app.view.components.cards import UniversalTaskCard
        return UniversalTaskCard(task, parent)

    def resultCard(self, task: "Task", parent=None) -> "ResultCard":
        from app.view.components.cards import UniversalResultCard
        return UniversalResultCard(task, parent)

    def fileTypes(self) -> list[FileType]:
        return []

    def cardChips(self, task: "Task") -> list[str]:
        # pack 专属的展示串列表（如 BT 的 Peers/Seeds、↑上传）；过缝进 wire，gui 卡片用 Repeater 渲染。
        # 核心卡不认识具体 pack，只渲染这些 chip——pack 想加专属展示就实现这个。
        return []

    def cardActionKind(self, task: "Task") -> str:
        # 卡片主按钮的语义动作：默认 "toggle"（暂停/继续）；直播这类无暂停语义的 pack 返回 "finalize"（停止收尾）。
        # 核心卡按此选图标 + 发统一 primaryAction 意图，引擎据此分派——核心不认识具体 pack。
        return "toggle"

    def cardSegments(self, task: "Task") -> list[dict]:
        # pack 专属的分段进度（如 HTTP 多线程各连接的区间），每段 {start,width} 为占总长的百分比。
        # 过缝进 wire，gui 卡片画成一排分段矩形（复刻原版 SegmentedProgressBar）；非分段 pack 返回 []，卡片走普通进度条。
        return []

    async def buildInstallTask(self) -> "Task | None":
        # 一键安装该 pack 依赖的二进制（如 N_m3u8DL-RE / FFmpeg）：返回一个下载任务，引擎当普通任务跑。
        # 默认无需安装。schema 的 action 项触发——只在该 pack 此平台支持安装时才出按钮。
        return None

    def setup(self, mainWindow: "MainWindow"):
        pass

    def tr(self, text: str) -> str:
        return QCoreApplication.translate(self.__class__.__name__, text)
