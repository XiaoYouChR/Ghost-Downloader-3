from __future__ import annotations

from pathlib import Path

import pytest

from app.config.cfg import cfg
from app.models.task import Task, TaskFile
from tests.conftest import FakeStep


@pytest.fixture
def setCategories(engine):
    cfg.set(cfg.isCategoryEnabled, True)


def buildTask(name: str, files: list[TaskFile] | None = None) -> Task:
    return Task(name=name, url=f"http://test/{name}", packId="test", steps=[FakeStep(stepIndex=0)], files=files)


def add(engine, task: Task) -> Task:
    engine.taskService.add(task, autoStart=False)
    return task


def test_add_without_categories_keeps_folder(engine, downloadFolder):
    task = add(engine, buildTask("movie.mp4"))

    assert (task.category, Path(task.outputPath).parent) == (None, downloadFolder)


def test_add_picks_category_by_extension(engine, setCategories, downloadFolder):
    task = add(engine, buildTask("movie.mp4"))

    assert (task.category, Path(task.outputPath).parent) == ("cat_video", downloadFolder / "Video")


def test_add_keeps_folder_chosen_by_user(engine, setCategories, downloadFolder):
    task = buildTask("movie.mp4")
    task.outputFolder = downloadFolder / "custom"

    add(engine, task)

    assert (task.category, task.outputFolder) == ("cat_video", downloadFolder / "custom")


def test_add_keeps_download_folder_for_unknown_extension(engine, setCategories, downloadFolder):
    task = add(engine, buildTask("notes.xyz"))

    assert (task.category, task.outputFolder) == ("", downloadFolder)


def test_add_keeps_category_chosen_by_user(engine, setCategories, downloadFolder):
    task = buildTask("notes.xyz")
    task.category = "cat_video"

    add(engine, task)

    assert (task.category, task.outputFolder) == ("cat_video", downloadFolder / "Video")


def test_add_folder_task_gets_no_category(engine, setCategories, downloadFolder):
    task = add(engine, buildTask("movie.mp4", files=[TaskFile(index=0, relativePath="a.mp4"),
                                                     TaskFile(index=1, relativePath="b.mp4")]))

    assert (task.category, task.outputFolder) == ("", downloadFolder)
