from __future__ import annotations

import pytest

from app.models.task import TaskError
from tests.ffmpeg_pack.test_container import buildFragmentedMp4Header
from tests.helpers import buildFileContent, buildRangeHandler


async def test_run_without_cover_saves_no_cover_file(tmp_path, startServer):
    from yt_dlp_pack.task import YouTubeCoverStep, YouTubeTask

    url = await startServer(buildRangeHandler(buildFileContent(8)))
    task = YouTubeTask(name="片.mp4", url="https://www.youtube.com/watch?v=x", outputFolder=tmp_path)
    task.setCoverUrl(url)
    cover = next(s for s in task.steps if isinstance(s, YouTubeCoverStep))

    async def waitForSpeedLimit():
        pass

    await cover.run(lambda n: None, waitForSpeedLimit)

    assert not list(tmp_path.glob("*.jpg"))


async def test_update_segment_range_supports_large_sidx_beyond_64kb(tmp_path, startServer):
    from yt_dlp_pack.task import YouTubeResourceStep, YouTubeTask

    header = buildFragmentedMp4Header(segmentCount=6000, segmentSize=100, segmentDuration=2000)
    assert len(header) > 65536
    url = await startServer(buildRangeHandler(header + b"\x00" * 1024))

    task = YouTubeTask(name="live.mp4", url="https://www.youtube.com/watch?v=live", outputFolder=tmp_path)
    task.updateSteps()
    videoStep = next(s for s in task.steps if isinstance(s, YouTubeResourceStep) and s.role == "video")
    videoStep.url = url
    videoStep.rawFileSize = len(header) + 6000 * 100
    videoStep.fileSize = videoStep.rawFileSize
    videoStep.startTime = 3600
    videoStep.endTime = 3660

    await videoStep.updateSegmentRange()

    assert videoStep.httpByteOffset > 0
    assert videoStep.fileSize == 30 * 100
    assert videoStep.segStartTime == pytest.approx(3600.0)
    assert len(videoStep._patchedHeader) > 0


async def test_update_segment_range_raises_when_index_invalid_on_trimmed_task(tmp_path, startServer):
    from yt_dlp_pack.task import YouTubeResourceStep, YouTubeTask

    url = await startServer(buildRangeHandler(b"invalid media stream" * 500))
    task = YouTubeTask(name="broken.mp4", url="https://www.youtube.com/watch?v=broken", outputFolder=tmp_path)
    task.updateSteps()
    videoStep = next(s for s in task.steps if isinstance(s, YouTubeResourceStep) and s.role == "video")
    videoStep.url = url
    videoStep.rawFileSize = 10_000
    videoStep.fileSize = 10_000
    videoStep.startTime = 10
    videoStep.endTime = 30

    with pytest.raises(TaskError, match="无法解析媒体索引"):
        await videoStep.updateSegmentRange()


def test_merge_step_builds_per_source_trim_args(tmp_path):
    from yt_dlp_pack.task import YouTubeMergeStep, YouTubeResourceStep, YouTubeTask

    task = YouTubeTask(name="dual.mp4", url="https://www.youtube.com/watch?v=dual", outputFolder=tmp_path)
    task.updateSteps()
    videoStep = next(s for s in task.steps if isinstance(s, YouTubeResourceStep) and s.role == "video")
    audioStep = next(s for s in task.steps if isinstance(s, YouTubeResourceStep) and s.role == "audio")
    mergeStep = next(s for s in task.steps if isinstance(s, YouTubeMergeStep))

    videoStep.extension = "mp4"
    audioStep.extension = "m4a"
    mergeStep.videoExtension = "mp4"
    mergeStep.audioExtension = "m4a"
    mergeStep.startTime = 15
    mergeStep.endTime = 45
    videoStep.segStartTime = 12.0
    audioStep.segStartTime = 14.5

    assert mergeStep._buildTrimArgs(mergeStep._videoPath) == (["-ss", "3.0"], ["-t", "30"])
    assert mergeStep._buildTrimArgs(mergeStep._audioPath) == (["-ss", "0.5"], ["-t", "30"])

