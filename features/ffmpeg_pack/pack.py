from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from app.models.pack import FeaturePack, TaskParser
from app.models.task import MergeTaskOptions, Task, TaskOptions
from app.platform.filesystem import toSafeFilename
from .config import ffmpegConfig, ffmpegRuntime
from .task import FFmpegResourceStep, FFmpegStep


class MergeParser(TaskParser):
    priority = 60

    def match(self, options: TaskOptions) -> bool:
        return isinstance(options, MergeTaskOptions)

    async def parse(self, options: TaskOptions) -> Task:
        assert isinstance(options, MergeTaskOptions)

        if not ffmpegRuntime.path() or not ffmpegRuntime.ffprobePath():
            raise RuntimeError("未找到可用的 ffmpeg 和 ffprobe，请先在设置中安装或配置 FFmpeg")

        videoTask = await self.delegate(options.video)
        audioTask = await self.delegate(options.audio)

        videoStep = videoTask.steps[0]
        audioStep = audioTask.steps[0]
        videoExt = Path(videoTask.name or urlparse(videoStep.url).path).suffix.lstrip(".").lower()
        audioExt = Path(audioTask.name or urlparse(audioStep.url).path).suffix.lstrip(".").lower()

        rawName = options.video.name or videoTask.name
        stem = toSafeFilename(rawName, fallback="merged-media")
        name = stem if stem.lower().endswith(".mp4") else f"{stem}.mp4"

        task = Task(
            name=name,
            url=videoStep.url,
            packId="ffmpeg",
            fileSize=max(0, videoTask.fileSize) + max(0, audioTask.fileSize),
            outputFolder=options.outputFolder,
        )
        task.addStep(FFmpegResourceStep(
            stepIndex=1,
            url=videoStep.url,
            fileSize=videoStep.fileSize,
            headers=videoStep.headers,
            subworkerCount=videoStep.subworkerCount,
            canUseRangeRequests=videoStep.canUseRangeRequests,
            role="video",
            extension=videoExt,
        ))
        task.addStep(FFmpegResourceStep(
            stepIndex=2,
            url=audioStep.url,
            fileSize=audioStep.fileSize,
            headers=audioStep.headers,
            subworkerCount=audioStep.subworkerCount,
            canUseRangeRequests=audioStep.canUseRangeRequests,
            role="audio",
            extension=audioExt,
        ))
        task.addStep(FFmpegStep(
            stepIndex=3,
            videoExtension=videoExt,
            audioExtension=audioExt,
        ))
        return task


class FFmpegPack(FeaturePack):
    packId = "ffmpeg"
    config = ffmpegConfig
    parsers = [MergeParser]

    def runtimes(self):
        return [ffmpegRuntime]
