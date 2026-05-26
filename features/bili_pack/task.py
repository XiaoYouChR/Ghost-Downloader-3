from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from features.ffmpeg_pack.task import FFmpegStage
    from features.http_pack.task import HttpTaskStage
else:
    from ffmpeg_pack.task import FFmpegStage
    from http_pack.task import HttpTaskStage


@dataclass(kw_only=True)
class BilibiliVideoStage(HttpTaskStage):
    pageIndex: int = 0
    pageSuffix: str = ""

    def updateOutputFile(self, taskPath: Path, taskTitle: str):
        baseTitle = taskTitle[:-4] if taskTitle.lower().endswith(".mp4") else taskTitle
        stem = f"{baseTitle}{self.pageSuffix}" if self.pageSuffix else baseTitle
        self.outputFile = str(taskPath / f"{stem}.video.m4s")


@dataclass(kw_only=True)
class BilibiliAudioStage(HttpTaskStage):
    pageIndex: int = 0
    pageSuffix: str = ""

    def updateOutputFile(self, taskPath: Path, taskTitle: str):
        baseTitle = taskTitle[:-4] if taskTitle.lower().endswith(".mp4") else taskTitle
        stem = f"{baseTitle}{self.pageSuffix}" if self.pageSuffix else baseTitle
        self.outputFile = str(taskPath / f"{stem}.audio.m4s")


@dataclass(kw_only=True)
class BilibiliMergeStage(FFmpegStage):
    pageIndex: int = 0
    pageSuffix: str = ""

    def updateOutputFile(self, taskPath: Path, taskTitle: str):
        baseTitle = taskTitle[:-4] if taskTitle.lower().endswith(".mp4") else taskTitle
        stem = f"{baseTitle}{self.pageSuffix}" if self.pageSuffix else baseTitle
        self.outputFile = str(taskPath / f"{stem}.mp4")
        self.videoPath = str(taskPath / f"{stem}.video.m4s")
        self.audioPath = str(taskPath / f"{stem}.audio.m4s")
