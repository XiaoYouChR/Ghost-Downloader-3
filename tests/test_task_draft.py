from __future__ import annotations

import pytest

from app.models.task import TaskOptions, TaskStatus
from tests.helpers import waitUntil

A, B, C = "http://test/a.zip", "http://test/b.zip", "http://test/c.zip"


@pytest.fixture
def pack(engine):
    return engine.featureService.packById("test")




async def test_parse_pasted_links(draft):
    parsed = []
    draft.parseSucceeded.connect(lambda url, task: parsed.append((url, task.name)))

    draft.setUrls([A, B])

    await waitUntil(lambda: sorted(parsed) == [(A, "a.zip"), (B, "b.zip")])


async def test_update_links_keeps_unchanged(draft, pack):
    parsed = []
    draft.parseSucceeded.connect(lambda url, task: parsed.append(url))
    pack.heldUrls.add(A)
    draft.setUrls([A, B])
    await waitUntil(lambda: all(draft.taskByUrl(url) is not None for url in [B]))

    draft.setUrls([B, C])
    pack.heldUrls.clear()

    await waitUntil(lambda: all(draft.taskByUrl(url) is not None for url in [C]))
    assert draft.urls() == [B, C]
    assert sorted(parsed) == [B, C]


async def test_parse_failure_shows_error(draft, pack):
    failures = []
    draft.parseFailed.connect(lambda url, error: failures.append((url, str(error))))
    pack.failingUrls.add(A)
    pack.heldUrls.add(A)
    draft.setUrls([A])

    assert draft.failCount() == 0
    pack.heldUrls.clear()

    await waitUntil(lambda: failures == [(A, "network error")])
    assert draft.failCount() == 1


async def test_parse_failed_link_again(draft, pack):
    pack.failingUrls.add(A)
    draft.setUrls([A])
    await waitUntil(lambda: draft.failCount() == 1)

    pack.failingUrls.clear()
    draft.refresh(A)

    await waitUntil(lambda: all(draft.taskByUrl(url) is not None for url in [A]))
    assert draft.failCount() == 0


async def test_parse_busy_only_while_parsing(draft):
    busy = []
    draft.parsingBusyChanged.connect(busy.append)

    draft.setUrls([A])

    await waitUntil(lambda: busy == [True, False])


async def test_add_parsed_tasks_on_confirm(engine, draft):
    draft.setUrls([A, B])
    await waitUntil(lambda: all(draft.taskByUrl(url) is not None for url in [A, B]))

    draft.confirm()

    assert sorted(task.name for task in engine.taskService.tasks) == ["a.zip", "b.zip"]


@pytest.mark.parametrize(("autoStart", "status"), [(True, TaskStatus.COMPLETED), (False, TaskStatus.WAITING)])
async def test_add_link_confirmed_while_parsing(engine, draft, pack, autoStart, status):
    pack.heldUrls.add(A)
    draft.setUrls([A])

    draft.confirm(autoStart=autoStart)
    assert engine.taskService.tasks == []
    pack.heldUrls.clear()

    await waitUntil(lambda: [task.status for task in engine.taskService.tasks] == [status])


async def test_add_applies_chosen_folder_and_category(engine, draft, downloadFolder):
    draft.setUrls([A])
    await waitUntil(lambda: all(draft.taskByUrl(url) is not None for url in [A]))
    draft.setBaseOptions({"outputFolder": str(downloadFolder / "chosen")})
    draft.setUrlCategory(A, "cat_video")

    draft.confirm(autoStart=False)

    [task] = engine.taskService.tasks
    assert (task.category, task.outputFolder) == ("cat_video", downloadFolder / "chosen")


async def test_clear_drops_links_being_parsed(draft, pack):
    parsed = []
    draft.parseSucceeded.connect(lambda url, task: parsed.append(url))
    pack.heldUrls.add(A)
    draft.setUrls([A])

    draft.clear()
    pack.heldUrls.clear()
    draft.setUrls([B])

    await waitUntil(lambda: all(draft.taskByUrl(url) is not None for url in [B]))
    assert parsed == [B]
    assert draft.urls() == [B]


def test_add_allowed_once_links_exist(draft):
    assert not draft.canConfirm()

    draft.setUrls([A])

    assert draft.canConfirm()


@pytest.mark.parametrize("change", [
    lambda draft: draft.setBaseOptions({"outputFolder": "/tmp"}),
    lambda draft: draft.setUrlCategory(A, "cat_video"),
    lambda draft: draft.update(A, lambda task: task.setName("renamed.zip")),
])
async def test_update_announces_every_link_change(draft, change):
    draft.setUrls([A])
    await waitUntil(lambda: all(draft.taskByUrl(url) is not None for url in [A]))
    changes = []
    draft.itemsChanged.connect(lambda: changes.append(True))

    change(draft)

    assert changes == [True]


async def test_update_ignores_link_not_yet_parsed(draft, pack):
    pack.heldUrls.add(A)
    draft.setUrls([A])
    changes = []
    draft.itemsChanged.connect(lambda: changes.append(True))

    draft.update(A, lambda task: task.setName("too early.zip"))
    draft.update("http://test/unknown.zip", lambda task: task.setName("unknown.zip"))

    assert changes == []


async def test_parse_success_clears_earlier_error(engine, draft, pack):
    pack.failingUrls.add(A)
    draft.setUrls([A])
    await waitUntil(lambda: draft.failCount() == 1)
    pack.failingUrls.clear()
    task = await engine.featureService.parse(TaskOptions(url=A))

    draft.addParsedTasks([task])

    assert draft.failCount() == 0
    assert draft.taskByUrl(A) is task
