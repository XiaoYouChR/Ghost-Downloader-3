from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from features.ffmpeg_pack.task import FFmpegStage
    from features.http_pack.task import HttpTaskStage
else:
    from ffmpeg_pack.task import FFmpegStage
    from http_pack.task import HttpTaskStage


def _bilibiliStem(taskTitle: str, pageSuffix: str) -> str:
    baseTitle = taskTitle[:-4] if taskTitle.lower().endswith(".mp4") else taskTitle
    return f"{baseTitle}{pageSuffix}" if pageSuffix else baseTitle


@dataclass(kw_only=True)
class BilibiliVideoStage(HttpTaskStage):
    pageIndex: int = 0
    pageSuffix: str = ""

    @property
    def outputFile(self) -> str:
        stem = _bilibiliStem(self.task.title, self.pageSuffix)
        return str(Path(self.task.path) / f"{stem}.video.m4s")


@dataclass(kw_only=True)
class BilibiliAudioStage(HttpTaskStage):
    pageIndex: int = 0
    pageSuffix: str = ""

    @property
    def outputFile(self) -> str:
        stem = _bilibiliStem(self.task.title, self.pageSuffix)
        return str(Path(self.task.path) / f"{stem}.audio.m4s")


@dataclass(kw_only=True)
class BilibiliMergeStage(FFmpegStage):
    pageIndex: int = 0
    pageSuffix: str = ""

    @property
    def outputFile(self) -> Path:
        stem = _bilibiliStem(self.task.title, self.pageSuffix)
        return Path(self.task.path) / f"{stem}.mp4"

    @property
    def videoPath(self) -> Path:
        stem = _bilibiliStem(self.task.title, self.pageSuffix)
        return Path(self.task.path) / f"{stem}.video.m4s"

    @property
    def audioPath(self) -> Path:
        stem = _bilibiliStem(self.task.title, self.pageSuffix)
        return Path(self.task.path) / f"{stem}.audio.m4s"
