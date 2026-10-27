from __future__ import annotations

from pathlib import Path

from tests.helpers import buildFileContent, buildRangeHandler, runStep


async def test_run_audio_from_known_link(tmp_path, startServer):
    from bili_pack.task import BiliPage, BilibiliTask

    content = buildFileContent(8)
    url = await startServer(buildRangeHandler(content))
    page = BiliPage(index=0, relativePath="ep", audioUrl=url, audioSize=8)
    task = BilibiliTask(
        name="合集.m4a",
        url="https://www.bilibili.com/video/BV1",
        outputFolder=tmp_path,
        files=[page],
        isVideoEnabled=False,
        _baseName="合集",
    )
    task.update()

    await runStep(task.steps[0])

    assert Path(task.toFilePath(0)).read_bytes() == content


def test_update_steps_for_selected_pages_only():
    from pathlib import Path
    from bili_pack.task import BiliPage, BilibiliTask

    files = [
        BiliPage(
            index=i,
            relativePath=f"p{i}",
            episodeTitle=f"集{i // 2}",
            bvid=f"BV{i // 2}",
            selected=i < 2,
        )
        for i in range(4)
    ]
    task = BilibiliTask(
        name="合集.mp4",
        url="https://www.bilibili.com/video/BV1",
        outputFolder=Path("."),
        files=files,
        _baseName="合集",
    )
    task.update()
    assert {s.fileIndex for s in task.steps if s.fileIndex is not None} == {0, 1}

    task.setSelection({0, 1, 2})
    assert {s.fileIndex for s in task.steps if s.fileIndex is not None} == {0, 1, 2}

    task.setSelection({0})
    assert {s.fileIndex for s in task.steps if s.fileIndex is not None} == {0, 1, 2}

    task.update()
    assert {s.fileIndex for s in task.steps if s.fileIndex is not None} == {0}


def test_update_summary_with_one_episode():
    from pathlib import Path
    from bili_pack.task import BiliPage, BilibiliTask

    files = [
        BiliPage(index=0, relativePath="a", episodeTitle="游戏王5DS", bvid="BV1", selected=True),
        BiliPage(index=1, relativePath="b", episodeTitle="棋魂", bvid="BV2", selected=False),
    ]
    task = BilibiliTask(
        name="各种番.mp4",
        url="u",
        outputFolder=Path("."),
        files=files,
        _baseName="各种番",
    )
    assert [[p.bvid for p in g] for g in task.videoGroups()] == [["BV1"], ["BV2"]]
    assert task.videoCounts() == (1, 2)

    files[0].selected = False
    assert task.videoCounts() == (0, 2)

    files[0].selected = True
    files[1].selected = True
    assert task.videoCounts() == (2, 2)


def test_update_adds_covers_for_season_and_selected_episodes():
    from pathlib import Path
    from bili_pack.task import BiliPage, BilibiliCoverStep, BilibiliTask, setEpisodeTitle

    files = [
        BiliPage(
            index=0, relativePath="a", episodeTitle="游戏王5DS", bvid="BV1",
            selected=True, coverUrl="https://i0.hdslb.com/bfs/ep1.jpg",
        ),
        BiliPage(
            index=1, relativePath="b", episodeTitle="棋魂", bvid="BV2",
            selected=False, coverUrl="https://i0.hdslb.com/bfs/ep2.jpg",
        ),
    ]
    task = BilibiliTask(
        name="各种番.mp4",
        url="u",
        outputFolder=Path("."),
        files=files,
        _baseName="各种番",
        coverUrl="https://i0.hdslb.com/bfs/season.jpg",
        isCoverEnabled=True,
    )
    task.update()
    coverFiles = [s.outputPath for s in task.steps if isinstance(s, BilibiliCoverStep)]
    assert any(p.endswith("各种番.jpg") for p in coverFiles)
    assert any(p.endswith("各种番 - 游戏王5DS.jpg") for p in coverFiles)
    assert not any("棋魂" in p for p in coverFiles)

    task.setSelection({0, 1})
    coverFiles = [s.outputPath for s in task.steps if isinstance(s, BilibiliCoverStep)]
    assert any(p.endswith("各种番 - 棋魂.jpg") for p in coverFiles)

    setEpisodeTitle([files[0]], "新标题")
    task.updateNames()
    coverFiles = [s.outputPath for s in task.steps if isinstance(s, BilibiliCoverStep)]
    assert any(p.endswith("各种番 - 新标题.jpg") for p in coverFiles)
    assert not any("游戏王5DS" in p for p in coverFiles)


def test_update_puts_cover_in_output_folder():
    from pathlib import Path
    from bili_pack.task import BiliPage, BilibiliCoverStep, BilibiliTask

    task = BilibiliTask(
        name="专武.mp4",
        url="u",
        outputFolder=Path("/tmp/Downloads"),
        files=[BiliPage(index=0, relativePath="a", selected=True)],
        _baseName="专武",
        coverUrl="https://i0.hdslb.com/bfs/cover.jpg",
        isCoverEnabled=True,
    )
    task.update()
    covers = [s for s in task.steps if isinstance(s, BilibiliCoverStep)]
    assert len(covers) == 1
    assert covers[0].outputPath == str(Path("/tmp/Downloads") / "专武.jpg")

    task.outputFolder = Path("/tmp/Downloads/Video")
    assert covers[0].outputPath == str(Path("/tmp/Downloads/Video") / "专武.jpg")

    task.setName("新名字.mp4")
    assert covers[0].outputPath == str(Path("/tmp/Downloads/Video") / "新名字.jpg")


def test_update_paths_follow_episode_and_page_names():
    from pathlib import Path
    from bili_pack.task import BiliPage, BilibiliTask, setFileName

    files = [
        BiliPage(index=0, relativePath="", episodeTitle="AC/DC 现场", bvid="BV1", pageNumber=1),
        BiliPage(index=1, relativePath="", episodeTitle="游戏王", bvid="BV2", pageNumber=1, pagePart="上"),
        BiliPage(index=2, relativePath="", episodeTitle="游戏王", bvid="BV2", pageNumber=2),
    ]
    task = BilibiliTask(name="合集.mp4", url="u", outputFolder=Path("."), files=files, _baseName="合集")
    task.update()
    assert [task.toDisplayPath(p) for p in files] == ["AC_DC 现场", "上", "P2"]
    assert [p.relativePath for p in files] == [
        "合集 - AC_DC 现场.mp4", "合集 - 游戏王 - P1 上.mp4", "合集 - 游戏王 - P2.mp4"]

    setFileName(task, 2, "下/集")
    assert [p.episodeTitle for p in files[1:]] == ["游戏王", "游戏王"]
    assert task.toDisplayPath(files[2]) == "下_集"
    assert files[2].relativePath == "合集 - 游戏王 - P2 下_集.mp4"

    setFileName(task, 0, "新名")
    assert task.toDisplayPath(files[0]) == "新名"
    assert files[0].relativePath == "合集 - 新名.mp4"


def test_update_names_after_rename_and_trim():
    from pathlib import Path
    from bili_pack.task import BiliPage, BilibiliTask

    files = [
        BiliPage(index=0, relativePath="a", episodeTitle="旧名", bvid="BV1", selected=True),
        BiliPage(index=1, relativePath="b", episodeTitle="另一集", bvid="BV2", selected=False),
    ]
    task = BilibiliTask(
        name="各种番.mp4", url="u", outputFolder=Path("."),
        files=files, _baseName="各种番",
    )
    task.update()
    assert files[0].relativePath == "各种番 - 旧名.mp4"

    files[0].episodeTitle = "新名"
    files[0].startTime = 10
    files[0].endTime = 20
    task.updateNames()
    assert files[0].relativePath == "各种番 - 新名 [00m10s-00m20s].mp4"


def test_set_time_range_changes_listed_pages_only():
    from bili_pack.task import BiliPage, setTimeRanges

    pages = [
        BiliPage(index=0, relativePath="a", startTime=1, endTime=2),
        BiliPage(index=1, relativePath="b", startTime=3, endTime=4),
        BiliPage(index=2, relativePath="c", startTime=5, endTime=6),
    ]
    setTimeRanges(pages, {0: (10, 20), 1: (0, 0)})
    assert (pages[0].startTime, pages[0].endTime) == (10, 20)
    assert (pages[1].startTime, pages[1].endTime) == (0, 0)
    assert (pages[2].startTime, pages[2].endTime) == (5, 6)
