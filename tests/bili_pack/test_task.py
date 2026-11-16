from __future__ import annotations

from pathlib import Path

import pytest

from app.models.task import TaskError
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


def buildSegmentBytes(content: str) -> bytes:
    contentBytes = content.encode("utf-8")
    elem = b"\x08\x01\x10\xe8\x07\x3a" + bytes([len(contentBytes)]) + contentBytes
    return b"\x0a" + bytes([len(elem)]) + elem


async def test_run_danmaku_side_file_and_empty_placeholder_cleanup(tmp_path, startServer, monkeypatch):
    from aiohttp import web
    from app.models.task import TaskStatus
    import bili_pack.account as account
    import bili_pack.danmaku as danmaku
    from bili_pack.task import BiliPage, BilibiliDanmakuStep, BilibiliTask

    body = buildSegmentBytes("测试弹幕")

    async def handler(request: web.Request) -> web.Response:
        return web.Response(body=body)

    async def fakeMixinKey() -> str:
        return ""

    url = await startServer(handler)
    monkeypatch.setattr(danmaku, "DANMAKU_SEG_API", url)
    monkeypatch.setattr(account, "fetchWbiMixinKey", fakeMixinKey)

    page = BiliPage(index=0, relativePath="v.mp4", cid=123, aid=456, width=1920, height=1080, _duration=10)
    task = BilibiliTask(
        name="演示.mp4",
        url="https://www.bilibili.com/video/BV1",
        outputFolder=tmp_path,
        files=[page],
        danmakuFormat="ass",
        _baseName="演示",
    )
    task.update()
    dmStep = next(s for s in task.steps if isinstance(s, BilibiliDanmakuStep))
    assert dmStep.outputPath == str(tmp_path / "演示.ass")
    for step in task.steps:
        if step is not dmStep:
            step.setStatus(TaskStatus.COMPLETED)

    await runStep(dmStep)
    assContent = Path(dmStep.outputPath).read_text(encoding="utf-8")
    assert "测试弹幕" in assContent

    # 作为 Side File 遇到空弹幕时清理空占位符
    body = b""
    taskEmpty = BilibiliTask(
        name="空弹幕.mp4",
        url="https://www.bilibili.com/video/BV2",
        outputFolder=tmp_path,
        files=[BiliPage(index=0, relativePath="v.mp4", cid=124, _duration=10)],
        danmakuFormat="xml",
        _baseName="空弹幕",
    )
    taskEmpty.update()
    dmEmptyStep = next(s for s in taskEmpty.steps if isinstance(s, BilibiliDanmakuStep))
    for step in taskEmpty.steps:
        if step is not dmEmptyStep:
            step.setStatus(TaskStatus.COMPLETED)
    Path(dmEmptyStep.outputPath).touch()
    await runStep(dmEmptyStep)
    assert not Path(dmEmptyStep.outputPath).exists()


async def test_run_standalone_danmaku_single_and_multi_page(tmp_path, startServer, monkeypatch):
    from aiohttp import web
    from app.models.task import Task
    import bili_pack.account as account
    import bili_pack.danmaku as danmaku
    from bili_pack.task import BiliPage, BilibiliDanmakuStep, BilibiliTask

    mode = "empty"

    async def handler(request: web.Request) -> web.Response:
        if mode == "412":
            return web.Response(status=412, text="blocked")
        if mode == "empty":
            return web.Response(body=b"")
        return web.Response(body=buildSegmentBytes("独立弹幕"))

    async def fakeMixinKey() -> str:
        return ""

    url = await startServer(handler)
    monkeypatch.setattr(danmaku, "DANMAKU_SEG_API", url)
    monkeypatch.setattr(account, "fetchWbiMixinKey", fakeMixinKey)

    single = BilibiliTask(
        name="占位.mp4",
        url="https://www.bilibili.com/video/BV1",
        outputFolder=tmp_path,
        files=[BiliPage(index=0, relativePath="", cid=200, _duration=10)],
        isVideoEnabled=False,
        isAudioEnabled=False,
        danmakuFormat="ass",
        _baseName="单P",
    )
    single.update()
    assert single.name == "单P.ass"
    assert single.placeholderPaths == [tmp_path / "单P.ass"]
    dmSingle = single.steps[0]
    assert isinstance(dmSingle, BilibiliDanmakuStep)

    # 独立下载空弹幕应保留合法空头，避免任务完成后变成 Missing
    await runStep(dmSingle)
    assert Path(dmSingle.outputPath).is_file()
    assert "[Events]" in Path(dmSingle.outputPath).read_text(encoding="utf-8")

    # 多 P 独立下载与持久化往返、选集同步及 412 错误边界
    mode = "text"
    multi = BilibiliTask(
        name="占位.mp4",
        url="https://www.bilibili.com/video/BV2",
        outputFolder=tmp_path,
        files=[
            BiliPage(index=0, relativePath="", cid=201, pageNumber=1, pagePart="上", selected=True, _duration=10),
            BiliPage(index=1, relativePath="", cid=202, pageNumber=2, pagePart="下", selected=False, _duration=10),
        ],
        isVideoEnabled=False,
        isAudioEnabled=False,
        danmakuFormat="xml",
        _baseName="合集",
    )
    multi.update()
    assert multi.name == "合集.xml"
    assert multi.outputPath == str(tmp_path / "合集")
    assert [p.relativePath for p in multi.files] == ["合集 - P1 上.xml", "合集 - P2 下.xml"]

    restored = Task.fromDict(multi.toDict())
    assert isinstance(restored, BilibiliTask)
    assert restored.danmakuFormat == "xml"
    assert [type(s) for s in restored.steps] == [BilibiliDanmakuStep]

    dmMulti = restored.steps[0]
    await runStep(dmMulti)
    assert "独立弹幕" in Path(dmMulti.outputPath).read_text(encoding="utf-8")

    mode = "412"
    restored.setSelection({0, 1})
    assert [s.fileIndex for s in restored.steps if isinstance(s, BilibiliDanmakuStep)] == [0, 1]

    dmSecond = next(s for s in restored.steps if isinstance(s, BilibiliDanmakuStep) and s.fileIndex == 1)
    with pytest.raises(TaskError, match="412"):
        await runStep(dmSecond)


def test_android_adapter_danmaku_controls():
    from bili_pack.android import draftFields, setControl, taskFields
    from bili_pack.task import BiliPage, BilibiliTask

    task = BilibiliTask(
        name="v.mp4",
        url="u",
        outputFolder=Path("."),
        files=[BiliPage(index=0, relativePath="v.mp4", cid=1, _duration=10)],
        coverUrl="https://i0.hdslb.com/bfs/c.jpg",
        _baseName="v",
    )
    task.update()

    fields = draftFields(task)
    controls = {c["id"]: c for c in fields["controls"]}
    assert controls["danmaku"]["value"] == ""
    assert [o["key"] for o in controls["danmaku"]["options"]] == ["ass", "xml"]
    assert controls["danmaku"]["isOptional"] is True

    setControl(task, "danmaku", "ass")
    assert task.danmakuFormat == "ass"

    setControl(task, "video", "")
    setControl(task, "audio", "")
    assert task.name == "v.ass"
    assert taskFields(task)["canSelectFiles"] is True

    fieldsOnlyDm = draftFields(task)
    controlsOnlyDm = {c["id"]: c for c in fieldsOnlyDm["controls"]}
    assert controlsOnlyDm["danmaku"]["isOptional"] is False
    assert fieldsOnlyDm["subtitles"] == []
    assert fieldsOnlyDm["duration"] == 10

    # 不能关掉最后一个激活轨道
    setControl(task, "danmaku", "")
    assert task.danmakuFormat == "ass"

    setControl(task, "cover", "1")
    setControl(task, "danmaku", "")
    assert task.danmakuFormat == ""
    assert task.isCoverEnabled is True
    setControl(task, "cover", "")
    assert task.isCoverEnabled is True


def test_bilibili_draft_card_danmaku_controls(qtbot, engine):
    from app.config.cfg import cfg
    from bili_pack.cards import BilibiliDraftCard
    from bili_pack.task import BiliPage, BilibiliTask

    task = BilibiliTask(
        name="演示.mp4",
        url="https://www.bilibili.com/video/BV1",
        outputFolder=Path("."),
        files=[BiliPage(index=0, relativePath="演示.mp4", cid=1, _duration=120)],
        coverUrl="https://i0.hdslb.com/bfs/c.jpg",
        _baseName="演示",
    )
    task.update()
    card = BilibiliDraftCard(task, engine.categoryService, engine.coroutineRunner, lambda _: None)
    qtbot.addWidget(card)
    try:
        card._danmakuButton._onOptionPicked("ass")
        assert task.danmakuFormat == "ass"
        assert card._danmakuButton.isChecked() is True

        card._trackBar.videoButton.setChecked(False)
        card._trackBar.audioButton.setChecked(False)
        assert task.name == "演示.ass"
        assert card.nameLabel.text() == "演示.ass"
        assert not card._trimButton.isHidden()

        card._danmakuButton._onTrackDeselected()
        assert task.danmakuFormat == "ass"
        assert card._danmakuButton.isChecked() is True

        card._trackBar.coverButton.setChecked(True)
        card._danmakuButton._onTrackDeselected()
        assert task.danmakuFormat == ""
        assert task.name == "演示.jpg"
        assert card._trimButton.isHidden()
    finally:
        cfg.isCategoryEnabled.valueChanged.disconnect(card._refreshCategoryButton)

