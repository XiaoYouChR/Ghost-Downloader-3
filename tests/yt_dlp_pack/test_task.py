from __future__ import annotations

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
