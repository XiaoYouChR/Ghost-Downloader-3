from __future__ import annotations

import asyncio

import pytest

from app.models.pack import PackServices
from app.models.task import TaskOptions, TaskStatus
from http_pack.pack import HttpPack
from tests.helpers import waitUntil

A, B, C = "http://test/a.zip", "http://test/b.zip", "http://test/c.zip"


@pytest.fixture
def pack(engine):
    return engine.featureService.packById("test")


@pytest.fixture
def httpPack(engine):
    services = PackServices(coroutineRunner=engine.coroutineRunner, speedMeter=engine.speedMeter)
    engine.featureService.register(HttpPack(services))




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


async def test_refresh_failed_parses_every_failed_link_again(draft, pack):
    pack.failingUrls.update([A, B])
    draft.setUrls([A, B, C])
    await waitUntil(lambda: draft.failCount() == 2)

    pack.failingUrls.clear()
    draft.refreshFailed()

    await waitUntil(lambda: all(draft.taskByUrl(url) is not None for url in [A, B, C]))
    assert draft.failCount() == 0


async def test_parse_links_from_one_site_five_at_a_time(draft, pack):
    urls = [f"http://test/{i}.zip" for i in range(7)]
    pack.heldUrls.update(urls)
    draft.setUrls(urls)

    await waitUntil(lambda: len(pack.parsedOptions) == 5)
    await asyncio.sleep(0.1)
    assert len(pack.parsedOptions) == 5
    pack.heldUrls.clear()

    await waitUntil(lambda: all(draft.taskByUrl(url) is not None for url in urls))


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


async def test_add_keeps_failed_links_in_draft(engine, draft, pack):
    pack.failingUrls.add(B)
    draft.setUrls([A, B])
    await waitUntil(lambda: draft.taskByUrl(A) is not None and draft.failCount() == 1)

    draft.confirm()

    assert [task.name for task in engine.taskService.tasks] == ["a.zip"]
    assert draft.urls() == [B]
    assert draft.failCount() == 1


async def test_add_link_failing_after_confirm_returns_to_draft(engine, draft, pack):
    failures = []
    draft.parseFailed.connect(lambda url, error: failures.append(url))
    pack.heldUrls.add(A)
    pack.failingUrls.add(A)
    draft.setUrls([A])

    draft.confirm()
    assert draft.urls() == []
    pack.heldUrls.clear()

    await waitUntil(lambda: failures == [A])
    assert draft.urls() == [A]
    assert draft.failCount() == 1
    assert engine.taskService.tasks == []


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


async def test_add_into_blocked_folder_keeps_task_in_draft(engine, draft, blockedFolder):
    draft.addFailed.connect(lambda tasks, error: draft.addParsedTasks(tasks))
    draft.setUrls([A, B])
    await waitUntil(lambda: all(draft.taskByUrl(url) is not None for url in [A, B]))
    draft.setBaseOptions({"outputFolder": str(blockedFolder)})

    draft.confirm()

    assert draft.urls() == [A, B]
    assert engine.taskService.tasks == []


async def test_add_into_blocked_folder_after_parsing_returns_task_to_draft(engine, draft, pack, blockedFolder):
    draft.addFailed.connect(lambda tasks, error: draft.addParsedTasks(tasks))
    pack.heldUrls.add(A)
    draft.setUrls([A])
    draft.setBaseOptions({"outputFolder": str(blockedFolder)})

    draft.confirm()
    pack.heldUrls.clear()

    await waitUntil(lambda: draft.urls() == [A])
    assert engine.taskService.tasks == []


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


async def test_parse_broken_link_shows_unsupported(draft, httpPack):
    failures = []
    draft.parseFailed.connect(lambda url, error: failures.append(str(error)))

    draft.setUrls(["http://[abc"])

    await waitUntil(lambda: failures == ["不支持该链接"])
