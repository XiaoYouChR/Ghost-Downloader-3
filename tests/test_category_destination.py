"""分类→目录推导的唯一来源。

桌面 TaskService.add 与 Android draft() 投影共用 CategoryService.outputFolderOf。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from app.models.task import Task, TaskStep


@dataclass(kw_only=True)
class StubStep(TaskStep):
    stepIndex: int = 0

    async def run(self, reportSpeed, waitForSpeedLimit):
        pass


RULE = {
    "categoryId": "cat_video",
    "name": "视频",
    "icon": "VIDEO",
    "folder": "{default}/Video",
    "extensions": ["mp4"],
}


def makeTask(name: str, category: str | None = None, folder: Path | None = None) -> Task:
    step = StubStep(stepIndex=0)
    task = Task(name=name, url="http://example.test/x", packId="http", steps=[step])
    step._bindTask(task)
    task.category = category
    if folder is not None:
        task.outputFolder = folder
    return task


@pytest.fixture()
def service(qapp, monkeypatch, tmp_path):
    from app.config.cfg import cfg
    monkeypatch.setattr(cfg.categoryRules, "value", [RULE])
    monkeypatch.setattr(cfg.downloadFolder, "value", str(tmp_path))
    from app.services.category_service import CategoryService
    return CategoryService(), tmp_path


@pytest.fixture()
def categoriesOn(monkeypatch):
    from app.config.cfg import cfg
    monkeypatch.setattr(cfg.isCategoryEnabled, "value", True)


@pytest.fixture()
def categoriesOff(monkeypatch):
    from app.config.cfg import cfg
    monkeypatch.setattr(cfg.isCategoryEnabled, "value", False)


def test_disabled_returns_task_values_unchanged(service, categoriesOff):
    svc, tmp = service
    task = makeTask("movie.mp4", category="cat_video", folder=tmp)
    assert svc.outputFolderOf(task) == ("cat_video", tmp)


def test_auto_detects_category_and_switches_folder(service, categoriesOn):
    svc, tmp = service
    categoryId, folder = svc.outputFolderOf(makeTask("movie.mp4", folder=tmp))
    assert categoryId == "cat_video"
    assert folder == tmp / "Video"


def test_explicit_folder_is_never_overridden(service, categoriesOn):
    svc, tmp = service
    custom = tmp / "custom"
    categoryId, folder = svc.outputFolderOf(makeTask("movie.mp4", folder=custom))
    assert categoryId == "cat_video"
    assert folder == custom


def test_unmatched_name_keeps_default_folder(service, categoriesOn):
    svc, tmp = service
    categoryId, folder = svc.outputFolderOf(makeTask("archive.bin", folder=tmp))
    assert categoryId == ""
    assert folder == tmp


def test_explicit_choice_is_not_redetected(service, categoriesOn):
    svc, tmp = service
    categoryId, folder = svc.outputFolderOf(makeTask("archive.bin", category="cat_video", folder=tmp))
    assert categoryId == "cat_video"
    assert folder == tmp / "Video"


def test_multi_file_task_is_not_auto_detected(service, categoriesOn):
    svc, tmp = service
    task = makeTask("movie.mp4", folder=tmp)
    from app.models.task import TaskFile
    task.files = [TaskFile(index=0, relativePath="a.mp4"), TaskFile(index=1, relativePath="b.mp4")]
    assert svc.outputFolderOf(task) == ("", tmp)
