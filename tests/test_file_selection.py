"""文件选择标志过滤语义与动态编排的分支测试。

背景：多文件任务的选择语义从"增删 Step"统一为"标志过滤"（ADR 0008），
并支持任意状态下修改选择（taskService.applySelection）。

覆盖：
  - 基类：_isStepSelected 全分支、setSelection 纯标志翻转、
    updateStatus/setStatus/pendingSteps/currentSnapshot 的选择过滤、
    _updateFilesFromSteps 多步聚合
  - M3U8：直播任务加载校正（假暂停定案）全状态分支
  - HF/FTP：旧存档缺失 Step 补建、解析路径不重复建
  - YouTube：setVideos 步骤组、选择感知的大小/快照/待执行步骤、
    extract 兄弟步骤按 fileIndex 更新
  - Bili：三种模式重建、P 后缀与选择解耦、字幕步按稳定身份查页
  - BT：完成后补选打回 WAITING 的判定分支
  - applySelection：暂停重启/复活/直通三条路径及其边界
"""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "features"))

app = QApplication.instance() or QApplication(sys.argv)

from app.models.task import SpecialFileSize, Task, TaskFile, TaskStatus, TaskStep
from app.services.task_service import TaskQueue, taskService

from bili_pack.task import BiliPage, BilibiliSubtitleStep, BilibiliTask, DownloadMode
from bittorrent_pack.task import BTFile, BTTask, BTTaskStep
from ftp_pack.task import FtpConnectionInfo, FtpTask
from huggingface_pack.task import HuggingFaceFile, HuggingFaceStep, HuggingFaceTask
from m3u8_pack.task import M3U8Task, M3U8TaskStep
from yt_dlp_pack.task import (
    STEPS_PER_VIDEO, YouTubeExtractStep, YouTubeFile,
    YouTubeMergeStep, YouTubeResourceStep, YouTubeTask,
)


@dataclass(kw_only=True)
class IndexedStep(TaskStep):
    fileIndex: int = -1

    async def run(self):
        self.setStatus(TaskStatus.COMPLETED)


@dataclass(kw_only=True)
class PlainStep(TaskStep):
    async def run(self):
        self.setStatus(TaskStatus.COMPLETED)


def buildTask(fileStates, stepStates=None, **kwargs):
    """fileStates: [(selected, completed)]，默认每文件一个同状态 Step。"""
    files = [
        TaskFile(index=i, relativePath=f"f{i}.bin", size=10, selected=sel, completed=comp)
        for i, (sel, comp) in enumerate(fileStates)
    ]
    stepStates = stepStates or [
        TaskStatus.COMPLETED if comp else TaskStatus.WAITING for _, comp in fileStates
    ]
    steps = [
        IndexedStep(stepIndex=i + 1, fileIndex=i, status=s)
        for i, s in enumerate(stepStates)
    ]
    return Task(name="t", url="https://example.com", packId="test",
                files=files, steps=steps, **kwargs)


# ─── 基类：_isStepSelected ─────────────────────────────────


def test_step_selected_when_no_files():
    task = Task(name="t", url="u", packId="p", steps=[IndexedStep(stepIndex=1, fileIndex=0)])
    assert task._isStepSelected(task.steps[0])


def test_step_without_file_index_always_selected():
    task = buildTask([(False, False)])
    step = PlainStep(stepIndex=99)
    step._bindTask(task)
    assert task._isStepSelected(step)


def test_step_selected_follows_file_flag():
    task = buildTask([(True, False), (False, False)])
    assert task._isStepSelected(task.steps[0])
    assert not task._isStepSelected(task.steps[1])


def test_step_with_unknown_file_index_not_selected():
    task = buildTask([(True, False)])
    orphan = IndexedStep(stepIndex=9, fileIndex=42)
    orphan._bindTask(task)
    assert not task._isStepSelected(orphan)


# ─── 基类：setSelection 纯标志翻转 ─────────────────────────


def test_set_selection_flips_flags_without_step_churn():
    task = buildTask([(True, False), (True, False), (True, False)])
    stepIds = [id(s) for s in task.steps]
    task.steps[0].receivedBytes = 55
    task.setSelection({1, 2})
    assert [id(s) for s in task.steps] == stepIds
    assert [f.selected for f in task.files] == [False, True, True]
    assert task.fileSize == 20
    task.setSelection({0, 1, 2})
    assert task.steps[0].receivedBytes == 55  # 断点进度保留


def test_set_selection_noop_without_files():
    task = Task(name="t", url="u", packId="p", fileSize=77)
    task.setSelection({0})
    assert task.fileSize == 77


# ─── 基类：状态聚合过滤 ────────────────────────────────────


def test_update_status_ignores_unselected_failed_step():
    task = buildTask([(True, True), (False, False)],
                     stepStates=[TaskStatus.COMPLETED, TaskStatus.FAILED])
    assert task.updateStatus() == TaskStatus.COMPLETED


def test_update_status_completes_when_selected_done():
    task = buildTask([(True, True), (False, False)])
    assert task.updateStatus() == TaskStatus.COMPLETED
    assert task.completedAt > 0


def test_update_status_keeps_status_when_nothing_selected():
    task = buildTask([(False, False)], status=TaskStatus.PAUSED)
    assert task.updateStatus() == TaskStatus.PAUSED


def test_set_status_skips_unselected_and_completed():
    task = buildTask([(True, True), (True, False), (False, False)],
                     stepStates=[TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.WAITING])
    task.setStatus(TaskStatus.RUNNING)
    assert task.steps[0].status == TaskStatus.COMPLETED  # 已完成不动
    assert task.steps[1].status == TaskStatus.RUNNING    # FAILED 被 reset 后置 RUNNING
    assert task.steps[2].status == TaskStatus.WAITING    # 未选中不动


def test_pending_steps_filters_and_sorts():
    task = buildTask([(True, True), (False, False), (True, False)])
    task.steps.reverse()
    task.status = TaskStatus.RUNNING
    pending = [s.fileIndex for s in task.pendingSteps()]
    assert pending == [2]  # 跳过已完成 f0、未选中 f1，且按 stepIndex 排序


def test_pending_steps_stops_when_not_running():
    task = buildTask([(True, False)])
    assert list(task.pendingSteps()) == []


def test_current_snapshot_counts_only_selected():
    task = buildTask([(True, False), (False, False)])
    task.steps[0].progress, task.steps[0].receivedBytes = 50.0, 500
    task.steps[1].progress, task.steps[1].receivedBytes = 100.0, 999
    progress, _speed, received = task.currentSnapshot()
    assert progress == 50.0
    assert received == 500


def test_files_mirror_multi_step_group_progress():
    steps = [
        IndexedStep(stepIndex=1, fileIndex=0, status=TaskStatus.COMPLETED),
        IndexedStep(stepIndex=2, fileIndex=0, status=TaskStatus.WAITING),
    ]
    steps[0].receivedBytes, steps[1].receivedBytes = 30, 12
    task = Task(name="t", url="u", packId="p", steps=steps,
                files=[TaskFile(index=0, relativePath="a", size=42)])
    task.updateStatus()
    assert task.files[0].downloadedBytes == 42
    assert not task.files[0].completed  # 组内还有未完成步骤


# ─── M3U8：直播加载校正 ────────────────────────────────────


def buildLiveTask(status, isLive=True, tmp=None):
    return M3U8Task(
        name="live.ts", url="https://example.com/live.m3u8", isLive=isLive,
        status=status, outputFolder=tmp,
        steps=[M3U8TaskStep(stepIndex=1, status=status)],
    )


@pytest.mark.parametrize("status", [TaskStatus.PAUSED, TaskStatus.RUNNING])
def test_live_task_finalized_on_load(tmp_path, status):
    task = buildLiveTask(status, tmp=tmp_path)
    assert task.status == TaskStatus.COMPLETED
    assert task.steps[0].status == TaskStatus.COMPLETED
    assert task.completedAt > 0


@pytest.mark.parametrize("status", [TaskStatus.WAITING, TaskStatus.FAILED, TaskStatus.COMPLETED])
def test_live_task_other_statuses_untouched(tmp_path, status):
    task = buildLiveTask(status, tmp=tmp_path)
    assert task.status == status


def test_vod_task_pause_untouched(tmp_path):
    task = buildLiveTask(TaskStatus.PAUSED, isLive=False, tmp=tmp_path)
    assert task.status == TaskStatus.PAUSED


# ─── HF/FTP：旧存档补建与解析不重复 ────────────────────────


def hfRecord(fileStates, stepIndexes):
    return {
        "type": "HuggingFaceTask", "name": "repo", "url": "https://huggingface.co/a/b",
        "packId": "huggingface", "status": "PAUSED", "repoId": "a/b",
        "files": [
            {"index": i, "relativePath": f"f{i}.bin", "size": 10,
             "selected": sel, "downloadUrl": f"u{i}"}
            for i, sel in enumerate(fileStates)
        ],
        "steps": [
            {"type": "HuggingFaceStep", "stepIndex": i + 1, "fileIndex": i,
             "url": f"u{i}", "fileSize": 10, "status": "PAUSED"}
            for i in stepIndexes
        ],
    }


def test_hf_rebuilds_missing_steps_from_archive():
    task = Task.fromDict(json.dumps(hfRecord([True, False, False], [0])))
    assert len(task.steps) == 3
    rebuilt = next(s for s in task.steps if s.fileIndex == 2)
    assert rebuilt.url == "u2"


def test_hf_full_archive_no_duplicates():
    task = Task.fromDict(json.dumps(hfRecord([True, True], [0, 1])))
    assert len(task.steps) == 2


def test_hf_parse_style_construction_no_duplicates():
    """回归：files+steps 一起构造时 __post_init__ 不得再补一份。"""
    files = [HuggingFaceFile(index=i, relativePath=f"f{i}", size=1, downloadUrl=f"u{i}")
             for i in range(3)]
    steps = [HuggingFaceStep(stepIndex=i + 1, url=f"u{i}", fileIndex=i) for i in range(3)]
    task = HuggingFaceTask(name="r", url="u", files=files, steps=steps)
    assert len(task.steps) == 3


def test_hf_no_files_no_reconciliation():
    task = HuggingFaceTask(name="r", url="u")
    assert task.steps == []


def test_ftp_rebuilds_missing_steps_from_archive():
    from ftp_pack.task import FtpFile
    task = FtpTask(
        name="dir", url="ftp://h/dir", sourceType="dir",
        connectionInfo=FtpConnectionInfo(
            scheme="ftp", host="h", port=21, username="", password="", sourcePath="/dir"),
        files=[
            FtpFile(index=0, relativePath="a", size=1, remotePath="/dir/a"),
            FtpFile(index=1, relativePath="b", size=2, remotePath="/dir/b", selected=False),
        ],
    )
    assert len(task.steps) == 2
    assert {s.fileIndex for s in task.steps} == {0, 1}


# ─── YouTube ───────────────────────────────────────────────


def buildYtTask(videoCount=3):
    task = YouTubeTask(name="list.mp4", url="https://youtube.com/watch?v=x&list=L",
                       isPlaylist=True, fileSize=int(SpecialFileSize.UNKNOWN))
    task.setVideos([
        {"id": f"v{i}", "title": f"Video {i}", "duration": 60 + i}
        for i in range(videoCount)
    ])
    return task


def test_yt_set_videos_builds_indexed_groups():
    task = buildYtTask(3)
    assert len(task.files) == 3 and len(task.steps) == 3 * STEPS_PER_VIDEO
    group1 = [s for s in task.steps if s.fileIndex == 1]
    assert [s.stepIndex for s in group1] == [5, 6, 7, 8]
    assert task.files[1].videoId == "v1"
    extract = next(s for s in group1 if isinstance(s, YouTubeExtractStep))
    assert extract.videoUrl == "https://www.youtube.com/watch?v=v1"


def test_yt_empty_videos_keeps_placeholder_group():
    task = YouTubeTask(name="v.mp4", url="https://youtube.com/watch?v=x")
    task.setVideos([])
    assert task.files == [] and len(task.steps) == STEPS_PER_VIDEO


def test_yt_selection_size_unknown_before_extract():
    task = buildYtTask(2)
    task.setSelection({0})
    assert task.fileSize == int(SpecialFileSize.UNKNOWN)


def test_yt_selection_size_sums_selected_resources():
    task = buildYtTask(2)
    for s in task.steps:
        if isinstance(s, YouTubeResourceStep):
            s.fileSize = 100
    task.setSelection({1})
    assert task.fileSize == 200  # 仅组1的 video+audio


def test_yt_pending_steps_always_yields_selected_extract():
    task = buildYtTask(2)
    for s in task.steps:
        s.status = TaskStatus.COMPLETED
    task.status = TaskStatus.RUNNING
    pending = list(task.pendingSteps())
    assert all(isinstance(s, YouTubeExtractStep) for s in pending)
    assert {s.fileIndex for s in pending} == {0, 1}


def test_yt_pending_steps_skips_unselected_group():
    task = buildYtTask(2)
    task.setSelection({1})
    task.status = TaskStatus.RUNNING
    assert {s.fileIndex for s in task.pendingSteps()} == {1}


def test_yt_snapshot_excludes_extract_and_unselected():
    task = buildYtTask(2)
    task.setSelection({0})
    for s in task.steps:
        s.receivedBytes = 10
    _p, _s, received = task.currentSnapshot()
    assert received == 30  # 组0的 video+audio+merge，不含 extract 与组1


def test_yt_extract_updates_only_own_group():
    task = buildYtTask(2)
    extract = next(s for s in task.steps
                   if isinstance(s, YouTubeExtractStep) and s.fileIndex == 0)
    videoFmt = {"url": "https://cdn/video", "filesize": 500, "ext": "mp4"}
    audioFmt = {"url": "https://cdn/audio", "filesize": 100, "ext": "m4a"}
    extract._updateSiblingSteps(videoFmt, audioFmt, {"title": "T"})
    group0 = [s for s in task.steps if isinstance(s, YouTubeResourceStep) and s.fileIndex == 0]
    group1 = [s for s in task.steps if isinstance(s, YouTubeResourceStep) and s.fileIndex == 1]
    assert all(s.url for s in group0)
    assert all(not s.url for s in group1)
    assert task.fileSize == 600


def test_yt_serialization_roundtrip():
    task = buildYtTask(2)
    task.setSelection({1})
    restored = Task.fromDict(json.dumps(task.toDict()))
    assert type(restored.files[0]) is YouTubeFile
    assert [f.selected for f in restored.files] == [False, True]
    assert len(restored.steps) == 2 * STEPS_PER_VIDEO


# ─── Bilibili ──────────────────────────────────────────────


def buildBiliTask(pageCount=3, subsOnPage=(0,), **kwargs):
    pages = [
        BiliPage(index=i, relativePath=f"P{i + 1}", pagePart=f"第{i + 1}集",
                 videoUrl=f"v{i}", audioUrl=f"a{i}", videoSize=100, audioSize=10,
                 subtitles=[{"lan": "zh", "subtitle_url": "u"}] if i in subsOnPage else [])
        for i in range(pageCount)
    ]
    task = BilibiliTask(name="合集.mp4", url="https://bilibili.com/video/BVx",
                        files=pages, _baseName="合集", **kwargs)
    task._rebuildSteps()
    return task


def test_bili_video_mode_step_layout():
    task = buildBiliTask(2, subsOnPage=(0,), subtitleLanguages=["zh"])
    assert len(task.steps) == 3 + 1 + 3  # P1 三步+字幕，P2 三步
    group0 = sorted(s.stepIndex for s in task.steps if s.fileIndex == 0)
    assert group0 == [1, 2, 3, 4]
    group1 = sorted(s.stepIndex for s in task.steps if s.fileIndex == 1)
    assert group1 == [5, 6, 7]


def test_bili_no_subtitle_language_no_subtitle_steps():
    task = buildBiliTask(2, subsOnPage=(0, 1))
    assert not any(isinstance(s, BilibiliSubtitleStep) for s in task.steps)


def test_bili_audio_mode():
    task = buildBiliTask(2)
    task.setMode(DownloadMode.AUDIO)
    assert task.name == "合集.m4a"
    assert len(task.steps) == 2
    assert task.fileSize == 20
    assert all(f.size == f.audioSize for f in task.files)


def test_bili_cover_mode():
    task = buildBiliTask(2, coverUrl="https://c/pic.jpg", coverSize=5)
    task.setMode(DownloadMode.COVER)
    assert task.name == "合集.jpg"
    assert len(task.steps) == 1 and task.fileSize == 5


def test_bili_suffix_follows_total_not_selection():
    task = buildBiliTask(3)
    task.setSelection({1})
    assert len(task.steps) == 9  # 改选不重建
    suffix = next(s.pageSuffix for s in task.steps if s.fileIndex == 1)
    assert suffix == " - P2 第2集"
    assert task.fileSize == 110


def test_bili_single_page_no_suffix():
    task = buildBiliTask(1)
    assert all(s.pageSuffix == "" for s in task.steps)


def test_bili_suffix_omits_part_equal_to_base_name():
    page = BiliPage(index=1, relativePath="P2", pagePart="合集",
                    videoUrl="v", audioUrl="a")
    task = buildBiliTask(3)
    assert task._pageSuffix(page) == " - P2"


def test_bili_subtitle_step_finds_page_by_stable_index():
    task = buildBiliTask(3, subsOnPage=(2,), subtitleLanguages=["en"])
    sub = next(s for s in task.steps if isinstance(s, BilibiliSubtitleStep))
    assert sub.fileIndex == 2
    asyncio.run(sub.run())  # 页面存在但语言不匹配 -> 直接完成，不发网络请求
    assert sub.status == TaskStatus.COMPLETED


def test_bili_subtitle_step_missing_page_completes():
    task = buildBiliTask(1)
    sub = BilibiliSubtitleStep(stepIndex=99, fileIndex=42)
    sub._bindTask(task)
    asyncio.run(sub.run())
    assert sub.status == TaskStatus.COMPLETED


# ─── BT：完成后补选 ────────────────────────────────────────


def buildBTTask(fileStates):
    return BTTask(
        name="t", url="magnet:?xt=urn:btih:x",
        files=[
            BTFile(index=i, relativePath=f"t/f{i}", size=10, selected=sel, completed=comp)
            for i, (sel, comp) in enumerate(fileStates)
        ],
        steps=[BTTaskStep(stepIndex=0, status=TaskStatus.COMPLETED)],
        status=TaskStatus.COMPLETED,
    )


def test_bt_reselect_uncompleted_revives_step():
    task = buildBTTask([(True, True), (False, False)])
    task.setSelection({0, 1})
    assert task.step.status == TaskStatus.WAITING
    assert task.status == TaskStatus.WAITING


def test_bt_deselect_completed_stays_completed():
    task = buildBTTask([(True, True), (True, True)])
    task.setSelection({0})
    assert task.step.status == TaskStatus.COMPLETED


def test_bt_unchanged_selection_early_return():
    task = buildBTTask([(True, True), (False, False)])
    task.files[1].priority = 0  # 与未选中状态一致，构成真正的"无变化"
    version = task._fileSelectionVersion
    task.setSelection({0})
    assert task._fileSelectionVersion == version


def test_bt_empty_selection_rejected():
    task = buildBTTask([(True, True)])
    with pytest.raises(ValueError):
        task.setSelection(set())


# ─── taskService.applySelection ────────────────────────────


@pytest.fixture()
def serviceProbe(monkeypatch):
    calls = []
    monkeypatch.setattr(taskService, "_queue", TaskQueue())
    monkeypatch.setattr(taskService, "_pump", lambda: calls.append("pump"))
    monkeypatch.setattr(taskService, "_schedule",
                        lambda t: calls.append("schedule"))
    monkeypatch.setattr(taskService, "_unwatchFile",
                        lambda t: calls.append("unwatch"))
    monkeypatch.setattr(
        taskService, "_cancelRun",
        lambda t, finished=None: (calls.append("cancel"), finished and finished()))
    return calls


def test_apply_selection_waiting_passthrough(serviceProbe):
    task = buildTask([(True, False), (True, False)])
    taskService.applySelection(task, {0})
    assert serviceProbe == []
    assert not task.files[1].selected


def test_apply_selection_revives_completed(serviceProbe):
    task = buildTask([(True, True), (False, False)], completedAt=123)
    task.status = TaskStatus.COMPLETED
    taskService.applySelection(task, {0, 1})
    assert serviceProbe == ["unwatch", "schedule"]
    assert task.completedAt == 0
    assert task.status == TaskStatus.WAITING


def test_apply_selection_completed_no_new_work_no_revive(serviceProbe):
    task = buildTask([(True, True), (True, True)], completedAt=123)
    task.status = TaskStatus.COMPLETED
    taskService.applySelection(task, {0})
    assert serviceProbe == []
    assert task.completedAt == 123
    assert task.status == TaskStatus.COMPLETED


def test_apply_selection_restarts_when_running_step_deselected(serviceProbe):
    task = buildTask([(True, False), (True, False)],
                     stepStates=[TaskStatus.RUNNING, TaskStatus.WAITING])
    task.status = TaskStatus.RUNNING
    taskService._queue.run(task.taskId, "w")
    taskService.applySelection(task, {1})
    assert serviceProbe == ["cancel", "schedule"]
    assert not task.files[0].selected


def test_apply_selection_keeps_running_when_other_deselected(serviceProbe):
    task = buildTask([(True, False), (True, False)],
                     stepStates=[TaskStatus.RUNNING, TaskStatus.WAITING])
    task.status = TaskStatus.RUNNING
    taskService._queue.run(task.taskId, "w")
    taskService.applySelection(task, {0})
    assert serviceProbe == []
    assert not task.files[1].selected


def test_apply_selection_running_step_without_file_index_not_interrupted(serviceProbe):
    step = PlainStep(stepIndex=1, status=TaskStatus.RUNNING)
    task = Task(name="t", url="u", packId="p", steps=[step],
                files=[TaskFile(index=0, relativePath="a", size=1)])
    task.status = TaskStatus.RUNNING
    taskService._queue.run(task.taskId, "w")
    taskService.applySelection(task, set())
    assert serviceProbe == []


def test_apply_selection_files_none_safe(serviceProbe):
    task = Task(name="t", url="u", packId="p")
    taskService.applySelection(task, {0})
    assert serviceProbe == []
