from __future__ import annotations

import json
from pathlib import Path

from app.config.cfg import cfg, currentOutputFolder, saveLastOutputFolder
from app.models.task import Task, TaskOptions
from app.services.browser_service import TaskSource, toTaskOptions
from tests.conftest import FakeStep


def buildTask(name: str, folder: Path | None = None) -> Task:
    task = Task(name=name, url=f"http://test/{name}", packId="test", steps=[FakeStep(stepIndex=0)])
    if folder is not None:
        task.outputFolder = folder
    return task


def test_load_keeps_unavailable_folder_and_later_settings(config, blockedFolder, tmp_path):
    configFile = tmp_path / "UserConfig.json"
    configFile.write_text(json.dumps({"GeneralDownload": {
        "DownloadFolder": str(blockedFolder),
        "RecentFolders": [str(blockedFolder)],
        "UseLastFolder": True,
        "LastOutputFolder": str(blockedFolder),
        "MaxTaskNum": 5,
    }}), encoding="utf-8")

    cfg.load(configFile)

    assert cfg.downloadFolder.value == str(blockedFolder)
    assert cfg.recentFolders.value == [str(blockedFolder)]
    assert currentOutputFolder() == blockedFolder
    assert cfg.maxTaskNum.value == 5


def test_current_output_folder_respects_toggle_and_default_change(config, downloadFolder, tmp_path):
    work = tmp_path / "work"
    other = tmp_path / "other"

    assert currentOutputFolder() == downloadFolder

    saveLastOutputFolder(work)
    assert currentOutputFolder() == downloadFolder

    cfg.set(cfg.shouldUseLastFolder, True)
    assert currentOutputFolder() == work

    # 设为同值不清空上次目录
    cfg.set(cfg.downloadFolder, str(downloadFolder))
    assert currentOutputFolder() == work

    # 修改 Default Folder 后回到新的 Default Folder
    cfg.set(cfg.downloadFolder, str(other))
    assert currentOutputFolder() == other


def test_current_output_folder_falls_back_when_empty(config, downloadFolder):
    cfg.set(cfg.shouldUseLastFolder, True)

    assert currentOutputFolder() == downloadFolder


def test_draft_confirm_saves_pre_category_folder_and_ignores_failure(engine, draft, downloadFolder, blockedFolder, tmp_path):
    cfg.set(cfg.shouldUseLastFolder, True)
    cfg.set(cfg.isCategoryEnabled, True)
    work = tmp_path / "work"

    draft.setBaseOptions({"outputFolder": work})
    draft.addParsedTasks([buildTask("a.mp4")])
    draft.confirm(autoStart=False)

    assert currentOutputFolder() == work
    assert engine.taskService.tasks[-1].outputFolder == work

    # 回到 Default Folder 后 Category 归档到 Video/，但记住的仍是分类前的 Default Folder
    draft.setBaseOptions({"outputFolder": downloadFolder})
    draft.addParsedTasks([buildTask("b.mp4")])
    draft.confirm(autoStart=False)

    assert engine.taskService.tasks[-1].outputFolder == downloadFolder / "Video"
    assert currentOutputFolder() == downloadFolder

    # 加入失败不污染上次目录
    draft.setBaseOptions({"outputFolder": blockedFolder})
    draft.addParsedTasks([buildTask("c.mp4")])
    draft.confirm(autoStart=False)

    assert currentOutputFolder() == downloadFolder


def test_edit_saves_last_folder_only_when_folder_changed_and_succeeded(engine, downloadFolder, blockedFolder, tmp_path):
    cfg.set(cfg.shouldUseLastFolder, True)
    work = tmp_path / "work"
    moved = tmp_path / "moved"
    work.mkdir()

    task = buildTask("file.bin", downloadFolder)
    engine.taskService.add(task, autoStart=False)
    saveLastOutputFolder(work)

    # 只改非路径选项（传入相同的 outputFolder）不覆盖上次目录
    engine.taskService.edit(task, {"outputFolder": downloadFolder, "subworkerCount": 4})
    assert currentOutputFolder() == work

    # 移动失败不覆盖上次目录
    failures = []
    engine.taskService.editFailed.connect(lambda t, e: failures.append(e))
    engine.taskService.edit(task, {"outputFolder": blockedFolder})
    assert failures
    assert currentOutputFolder() == work

    # 真正改目录且成功才更新
    engine.taskService.edit(task, {"outputFolder": moved})
    assert task.outputFolder == moved
    assert currentOutputFolder() == moved


def test_task_options_and_browser_follow_current_output_folder(config, downloadFolder, tmp_path):
    work = tmp_path / "work"
    cfg.set(cfg.shouldUseLastFolder, True)
    saveLastOutputFolder(work)

    assert TaskOptions(url="http://test/a.bin").outputFolder == work
    assert toTaskOptions(TaskSource.DOWNLOAD, {"url": "http://test/a.bin"}).outputFolder == work
    assert toTaskOptions(TaskSource.DOWNLOAD, {"url": "http://test/a.bin", "path": str(downloadFolder)}).outputFolder == downloadFolder
