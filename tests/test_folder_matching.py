from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config.cfg import cfg, saveLastOutputFolder
from app.config.serializers import PathSerializer
from app.models.task import TaskOptions
from app.services.browser_service import TaskSource, toTaskOptions
from app.services.folder_matching import loadRecentFolders, matchFolder
from tests.helpers import waitUntil


@pytest.mark.parametrize(("folder", "name", "url"), [
    ("artist1", "[artist1] Manga1.cbz", ""),
    ("artist2", "[ARTIST2] Manga2.cbz", ""),
    ("ProjectAlpha", "ProjectAlpha-report.pdf", ""),
    ("My Project", "[my_project]-report.pdf", ""),
    ("My-Project", "my project_report.pdf", ""),
    ("艺术家", "[艺术家] 漫画.cbz", ""),
    ("作品", "作品-report.pdf", ""),
    ("Straße", "STRASSE-report.pdf", ""),
    ("Café", "Cafe\u0301_report.pdf", ""),
    ("artist1", "report.pdf", "https://example.test/artist1/report.pdf"),
    ("My Project", "report.pdf", "https://example.test/My%20Project/report.pdf"),
    ("艺术家", "report.pdf", "https://example.test/%E8%89%BA%E6%9C%AF%E5%AE%B6/a"),
])
def test_match_selects_existing_folder(tmp_path, folder, name, url):
    target = tmp_path / folder
    target.mkdir()
    candidates = loadRecentFolders((str(target),))

    assert matchFolder(name, url, candidates) == target


@pytest.mark.parametrize("url", [
    "https://[broken/artist1/a", "not a URL/artist1/a", "file:///artist1/a",
    "magnet:?xt=artist1", "https://host:bad/artist1/a", "https://host/%ff/artist1",
    "https://host/%zz/artist1", "https://host/%2e%2e/artist1/a",
    "https://artist1:secret@host/a?folder=artist1#artist1", "https://artist1.test/a",
])
def test_match_ignores_unsupported_or_unreliable_url(tmp_path, url):
    assert matchFolder("other.pdf", url, (tmp_path / "artist1",)) is None


@pytest.mark.parametrize("name", ["cartist1.pdf", "artist10.cbz", "myartist1.cbz", "other.pdf"])
def test_match_avoids_substring_guesses(tmp_path, name):
    assert matchFolder(name, "", (tmp_path / "artist1",)) is None


def test_match_prefers_specific_filename_then_url(tmp_path):
    short = tmp_path / "Project"
    specific = tmp_path / "Project Alpha"
    urlFolder = tmp_path / "Other Project Alpha"

    assert matchFolder("Project-Alpha-report.pdf", "https://host/Other-Project-Alpha/a",
                       (short, specific, urlFolder)) == specific


def test_match_falls_back_for_equal_destinations(tmp_path):
    first = tmp_path / "one" / "artist1"
    second = tmp_path / "two" / "artist1"

    assert matchFolder("artist1.cbz", "", (first, second)) is None
    assert matchFolder("artist1.cbz", "", (second, first)) is None
    assert matchFolder("artist1.cbz", "", ()) is None


def test_load_ignores_missing_invalid_and_file_paths(tmp_path, blockedFolder):
    assert loadRecentFolders((str(tmp_path / "missing"), str(blockedFolder), "", "bad\x00path", ".")) == ()


@pytest.fixture
def recentFolder(engine, tmp_path):
    folder = tmp_path / "artist1"
    folder.mkdir()
    cfg.set(cfg.recentFolders, [str(folder)])
    cfg.set(cfg.shouldSuggestFolder, True)
    return folder


async def test_add_respects_disabled_setting(engine, recentFolder, downloadFolder):
    cfg.set(cfg.shouldSuggestFolder, False)
    task = await engine.featureService.parse(TaskOptions.fromOptions({"url": "http://test/artist1.cbz"}))
    engine.taskService.add(task, autoStart=False)

    assert task.outputFolder == downloadFolder


@pytest.mark.parametrize("shouldUseLast", [False, True])
async def test_add_prefers_match_over_automatic_fallback(engine, recentFolder, tmp_path, shouldUseLast):
    cfg.set(cfg.shouldUseLastFolder, shouldUseLast)
    saveLastOutputFolder(tmp_path / "last")
    cfg.set(cfg.isCategoryEnabled, True)
    task = await engine.featureService.parse(TaskOptions.fromOptions({"url": "http://test/artist1.pdf"}))
    engine.taskService.add(task, autoStart=False)

    assert task.outputFolder == recentFolder
    assert task.category == "cat_document"


@pytest.mark.parametrize("shouldUseLast", [False, True])
async def test_add_without_match_preserves_category_and_last_folder(engine, recentFolder, downloadFolder, tmp_path, shouldUseLast):
    last = tmp_path / "last"
    cfg.set(cfg.shouldUseLastFolder, shouldUseLast)
    saveLastOutputFolder(last)
    cfg.set(cfg.isCategoryEnabled, True)
    task = await engine.featureService.parse(TaskOptions.fromOptions({"url": "http://test/other.pdf"}))
    engine.taskService.add(task, autoStart=False)

    assert task.outputFolder == (last if shouldUseLast else downloadFolder / "Documents")


@pytest.mark.parametrize("category", ["cat_video", ""])
async def test_add_keeps_explicit_category(engine, recentFolder, downloadFolder, category):
    cfg.set(cfg.isCategoryEnabled, True)
    task = await engine.featureService.parse(TaskOptions.fromOptions({"url": "http://test/artist1.pdf"}))
    task.setOptions({"category": category})
    engine.taskService.add(task, autoStart=False)

    assert task.category == category
    assert task.outputFolder == (downloadFolder / "Video" if category else downloadFolder)


async def test_add_keeps_explicit_default_folder(engine, recentFolder, downloadFolder):
    task = await engine.featureService.parse(TaskOptions.fromOptions({
        "url": "http://test/artist1.cbz", "outputFolder": downloadFolder,
    }))
    engine.taskService.add(task, autoStart=False)

    assert task.outputFolder == downloadFolder


async def test_draft_keeps_manual_folder_when_other_options_change(engine, draft, recentFolder, tmp_path, downloadFolder):
    url = "http://test/artist1.cbz"
    draft.setBaseOptions({"outputFolder": downloadFolder, "shouldSuggestFolder": True})
    draft.setUrls([url])
    await waitUntil(lambda: draft.taskByUrl(url) is not None)
    chosen = tmp_path / "chosen"
    draft.update(url, lambda task: task.setOptions({"outputFolder": chosen}))
    draft.setBaseOptions({"outputFolder": downloadFolder, "shouldSuggestFolder": True, "subworkerCount": 4})
    draft.confirm(autoStart=False)

    assert engine.taskService.tasks[-1].outputFolder == chosen


async def test_draft_suggests_individual_batch_folders(engine, draft, recentFolder, tmp_path):
    second = tmp_path / "artist2"
    second.mkdir()
    cfg.set(cfg.recentFolders, [str(recentFolder), str(second)])
    urls = ["http://test/artist1.cbz", "http://test/artist2.cbz"]
    draft.setUrls(urls)
    await waitUntil(lambda: all(draft.taskByUrl(url) for url in urls))
    draft.confirm(autoStart=False)

    assert [task.outputFolder for task in engine.taskService.tasks] == [recentFolder, second]


async def test_add_ignores_folder_removed_after_parse(engine, recentFolder, downloadFolder):
    task = await engine.featureService.parse(TaskOptions.fromOptions({"url": "http://test/artist1.cbz"}))
    recentFolder.rmdir()
    engine.taskService.add(task, autoStart=False)

    assert task.outputFolder == downloadFolder
    assert not recentFolder.exists()


async def test_add_matches_final_name_without_constructing_paths(engine, recentFolder):
    task = await engine.featureService.parse(TaskOptions.fromOptions({"url": "http://test/unknown"}))
    task.setName("../[artist1] report.pdf")
    engine.taskService.add(task, autoStart=False)

    assert task.outputFolder == recentFolder
    assert Path(task.outputPath).parent == recentFolder


@pytest.mark.parametrize("explicit", [False, True])
async def test_browser_preserves_explicit_folder(engine, recentFolder, downloadFolder, explicit):
    payload = {"url": "http://test/artist1.cbz"}
    if explicit:
        payload["path"] = str(downloadFolder)
    task = await engine.featureService.parse(toTaskOptions(TaskSource.DOWNLOAD, payload))
    engine.taskService.add(task, autoStart=False)

    assert task.outputFolder == (downloadFolder if explicit else recentFolder)


def test_load_persists_toggle_and_portable_history(config, tmp_path):
    data = tmp_path / "GhostDownloader"
    target = data / "artist1"
    target.mkdir(parents=True)
    serializer = PathSerializer(data)
    portable = serializer.serialize([str(target)])
    assert portable == ["{data}/artist1"]
    assert loadRecentFolders(tuple(serializer.deserialize(portable))) == (target,)
    configFile = tmp_path / "config.json"
    configFile.write_text("{}", encoding="utf-8")
    cfg.load(configFile)
    cfg.set(cfg.shouldSuggestFolder, True)
    cfg.set(cfg.shouldSuggestFolder, False, save=False)
    cfg.load(configFile)

    assert cfg.shouldSuggestFolder.value is True
    assert json.loads(configFile.read_text(encoding="utf-8"))["GeneralDownload"]["SuggestFolder"] is True


async def test_add_keeps_directly_supplied_path(engine, recentFolder, downloadFolder):
    task = await engine.featureService.parse(TaskOptions(
        url="http://test/artist1.cbz", outputFolder=downloadFolder,
    ))
    engine.taskService.add(task, autoStart=False)

    assert task.outputFolder == downloadFolder


@pytest.mark.parametrize("name,url", [
    ("other.pdf", ""), ("unknown", "https://host/other.pdf"),
])
def test_match_ignores_extension_only_folder(tmp_path, name, url):
    assert matchFolder(name, url, (tmp_path / "pdf",)) is None
