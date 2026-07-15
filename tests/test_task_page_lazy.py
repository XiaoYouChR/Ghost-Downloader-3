"""TaskPage 懒加载重构的逐分支测试。

覆盖：
  - 视口卡片生命周期（创建/销毁）
  - 选择状态提升（_selectedIds）
  - selectAll / invertSelection / selectMissing
  - Shift+Click 范围选择
  - CommandView 批量操作（重下载/删除/移动分类）
  - 筛选切换后选择态保留与恢复
  - 空状态判断
  - _onTaskAdded / _onTaskRemoved
  - _onFileDisappeared
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from typing import ClassVar, Type
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Signal, QObject
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)


# ─── 轻量 stub ───────────────────────────────────────────────


class StubTaskStore:
    def __init__(self):
        self._tasks: dict[str, StubTask] = {}

    def tasks(self):
        return dict(self._tasks)

    def taskById(self, taskId):
        return self._tasks.get(taskId)

    def flush(self):
        pass


class StubTaskService(QObject):
    taskAdded = Signal(object)
    taskRemoved = Signal(str)
    taskStarted = Signal(object)
    taskPaused = Signal(object)
    taskCompleted = Signal(object)
    taskFailed = Signal(object)
    fileDisappeared = Signal(object)

    def __init__(self):
        super().__init__()
        self._store = StubTaskStore()
        self._redownloaded: list[str] = []
        self._deleted: list[tuple[str, bool]] = []
        self._categories: dict[str, str] = {}

    @property
    def tasks(self) -> list[StubTask]:
        return list(self._store._tasks.values())

    def taskById(self, taskId: str):
        return self._store.taskById(taskId)

    def addTask(self, task: StubTask):
        self._store._tasks[task.taskId] = task
        self.taskAdded.emit(task)

    def removeTask(self, taskId: str):
        self._store._tasks.pop(taskId, None)
        self.taskRemoved.emit(taskId)

    def redownload(self, task):
        self._redownloaded.append(task.taskId)

    def delete(self, task, shouldDeleteFiles: bool):
        self._deleted.append((task.taskId, shouldDeleteFiles))
        self.removeTask(task.taskId)

    def setCategory(self, task, categoryId: str):
        task.category = categoryId
        self._categories[task.taskId] = categoryId

    def startAll(self):
        pass

    def pauseAll(self):
        pass


class StubTask:
    hasOutputFile: ClassVar[bool] = True

    def __init__(self, taskId: str, name: str = "", status=None, fileSize: int = 100,
                 createdAt: int = 0, completedAt: int = 0, category: str = ""):
        from app.models.task import TaskStatus
        self.taskId = taskId
        self.name = name or taskId
        self.url = f"https://example.com/{taskId}"
        self.packId = "stub"
        self.status = status or TaskStatus.WAITING
        self.fileSize = fileSize
        self.createdAt = createdAt or int(time())
        self.completedAt = completedAt
        self.outputFolder = Path("C:/tmp/downloads")
        self.category = category
        self.steps = []

    @property
    def outputPath(self) -> str:
        return str(self.outputFolder / self.name)

    @property
    def canPause(self) -> bool:
        return True

    @property
    def lastError(self):
        return None

    def currentSnapshot(self):
        return 50.0, 1024, self.fileSize // 2


class StubSpeedMeter(QObject):
    speedChanged = Signal(int)


class StubCategoryService(QObject):
    categoriesChanged = Signal()

    def categories(self):
        return []

    def categoryById(self, cid):
        return None


# ─── fixtures ────────────────────────────────────────────────

@pytest.fixture()
def env(monkeypatch):
    """搭建完整的 stub 环境，返回 (taskPage, stubTaskService)。"""
    stubService = StubTaskService()
    stubSpeed = StubSpeedMeter()
    stubCategory = StubCategoryService()

    monkeypatch.setattr("app.services.task_service.taskService", stubService)
    monkeypatch.setattr("app.view.pages.task_page.taskService", stubService)
    monkeypatch.setattr("app.view.pages.task_page.speedMeter", stubSpeed)
    monkeypatch.setattr("app.services.category_service.categoryService", stubCategory)

    from app.view.cards.task_cards import UniversalTaskCard

    def fakeTaskCard(task, parent=None):
        return UniversalTaskCard(task, parent)

    monkeypatch.setattr("app.view.pages.task_page.featureService",
                         MagicMock(taskCard=MagicMock(side_effect=fakeTaskCard)))

    # cfg stubs
    monkeypatch.setattr("app.view.pages.task_page.cfg.isCategoryEnabled",
                         MagicMock(value=False, valueChanged=MagicMock(connect=MagicMock())))
    monkeypatch.setattr("app.view.pages.task_page.cfg.isSpeedLimitEnabled",
                         MagicMock(value=False))

    from app.view.pages.task_page import TaskPage
    page = TaskPage()
    page.resize(400, 800)
    page.show()

    app.processEvents()

    return page, stubService


def _addTasks(svc: StubTaskService, count: int, **kwargs) -> list[StubTask]:
    tasks = []
    for i in range(count):
        t = StubTask(taskId=f"t{i}", name=f"file_{i}.zip", createdAt=1000 + i, **kwargs)
        tasks.append(t)
    for t in tasks:
        svc.addTask(t)
    app.processEvents()
    return tasks


def _visibleIds(page) -> set[str]:
    return set(page._liveCards.keys())


# ─── 视口生命周期 ─────────────────────────────────────────────

class TestViewportLifecycle:

    def test_only_viewport_cards_created(self, env):
        page, svc = env
        tasks = _addTasks(svc, 50)
        assert len(page._liveCards) < 50
        assert len(page._liveCards) > 0

    def test_scroll_creates_and_destroys(self, env):
        page, svc = env
        _addTasks(svc, 50)
        initialIds = set(page._liveCards.keys())

        page.scrollArea.verticalScrollBar().setValue(
            page.scrollArea.verticalScrollBar().maximum()
        )
        app.processEvents()
        page._refreshViewport()

        afterScrollIds = set(page._liveCards.keys())
        assert afterScrollIds != initialIds

    def test_empty_state_no_tasks(self, env):
        page, svc = env
        app.processEvents()
        assert page.emptyStatusWidget.isVisible()

    def test_empty_state_with_filter(self, env):
        from app.models.task import TaskStatus
        page, svc = env
        _addTasks(svc, 3, status=TaskStatus.COMPLETED)
        from app.view.pages.task_page import FilterMode
        page.setFilterMode(FilterMode.ACTIVE)
        assert page.emptyStatusWidget.isVisible()

    def test_task_added_creates_card_in_viewport(self, env):
        page, svc = env
        t = StubTask(taskId="new1", createdAt=9999)
        svc.addTask(t)
        app.processEvents()
        assert "new1" in page._displayOrder

    def test_task_removed_destroys_card(self, env):
        page, svc = env
        _addTasks(svc, 5)
        assert "t0" in page._liveCards
        svc.removeTask("t0")
        app.processEvents()
        assert "t0" not in page._liveCards

    def test_create_card_returns_none(self, env):
        """pack 不可用时 featureService.taskCard 返回 None，不崩溃。"""
        page, svc = env
        from app.view.pages.task_page import featureService
        featureService.taskCard.side_effect = lambda task, parent=None: None
        t = StubTask(taskId="orphan", createdAt=9999)
        svc.addTask(t)
        app.processEvents()
        assert "orphan" not in page._liveCards


# ─── 选择状态提升 ─────────────────────────────────────────────

class TestSelectionState:

    def test_select_all_includes_offscreen(self, env):
        page, svc = env
        _addTasks(svc, 50)
        page.setSelectionMode(True)
        page.selectAll()
        assert page._selectedIds == set(page._displayOrder)
        assert len(page._selectedIds) == 50

    def test_invert_selection(self, env):
        page, svc = env
        _addTasks(svc, 50)
        page.setSelectionMode(True)
        page._selectedIds.add("t0")
        page._selectedIds.add("t1")
        page.invertSelection()
        assert "t0" not in page._selectedIds
        assert "t1" not in page._selectedIds
        assert "t2" in page._selectedIds

    def test_select_missing_checks_filesystem(self, env, tmp_path):
        page, svc = env
        tasks = _addTasks(svc, 5)
        for t in tasks:
            t.outputFolder = tmp_path
        existing = tmp_path / "file_0.zip"
        existing.write_bytes(b"data")

        page.setSelectionMode(True)
        page.selectMissing()

        assert "t0" not in page._selectedIds
        assert "t1" in page._selectedIds
        assert "t2" in page._selectedIds

    def test_exit_selection_clears_selectedIds(self, env):
        page, svc = env
        _addTasks(svc, 5)
        page.setSelectionMode(True)
        page.selectAll()
        assert len(page._selectedIds) > 0
        page.setSelectionMode(False)
        assert len(page._selectedIds) == 0

    def test_selection_restored_on_scroll(self, env):
        page, svc = env
        _addTasks(svc, 50)
        page.setSelectionMode(True)
        page.selectAll()

        page.scrollArea.verticalScrollBar().setValue(
            page.scrollArea.verticalScrollBar().maximum()
        )
        app.processEvents()
        page._refreshViewport()

        for taskId, card in page._liveCards.items():
            assert card.isChecked(), f"Card {taskId} should be checked after scroll"

    def test_shift_click_range(self, env):
        page, svc = env
        _addTasks(svc, 10)
        page.setSelectionMode(True)

        page._onCardSelectionChanged("t2", True, False)
        assert page._selectionAnchor == "t2"

        page._onCardSelectionChanged("t5", True, True)
        assert page._selectedIds == {"t2", "t3", "t4", "t5"}

    def test_uncheck_last_exits_selection_mode(self, env):
        page, svc = env
        _addTasks(svc, 3)
        page._onCardSelectionChanged("t0", True, False)
        assert page._isSelectionMode is True
        page._onCardSelectionChanged("t0", False, False)
        assert page._isSelectionMode is False

    def test_selection_survives_filter_change(self, env):
        from app.models.task import TaskStatus
        from app.view.pages.task_page import FilterMode
        page, svc = env
        tasks = _addTasks(svc, 10)
        tasks[0].status = TaskStatus.COMPLETED
        tasks[1].status = TaskStatus.COMPLETED
        for t in tasks[2:]:
            t.status = TaskStatus.WAITING

        page.setSelectionMode(True)
        page.selectAll()
        allSelected = set(page._selectedIds)

        page.setFilterMode(FilterMode.ACTIVE)
        assert page._selectedIds == allSelected

        page.setFilterMode(FilterMode.ALL)
        for taskId in page._liveCards:
            card = page._liveCards[taskId]
            if taskId in allSelected:
                assert card.isChecked()


# ─── CommandView 批量操作 ────────────────────────────────────

class TestCommandViewActions:

    def test_redownload_selected(self, env):
        page, svc = env
        _addTasks(svc, 5)
        page.setSelectionMode(True)
        page._selectedIds.update(["t1", "t3"])
        for tid, card in page._liveCards.items():
            card.setChecked(tid in page._selectedIds)

        page._onRedownloadSelected()
        assert set(svc._redownloaded) == {"t1", "t3"}
        assert page._isSelectionMode is False

    def test_delete_selected(self, env):
        page, svc = env
        _addTasks(svc, 5)
        page.setSelectionMode(True)
        page._selectedIds.update(["t0", "t2", "t4"])
        for tid, card in page._liveCards.items():
            card.setChecked(tid in page._selectedIds)

        page._onDeleteConfirmed(shouldDeleteFiles=True)
        deletedIds = {tid for tid, _ in svc._deleted}
        assert deletedIds == {"t0", "t2", "t4"}
        assert page._isSelectionMode is False

    def test_delete_scoped_to_display_order(self, env):
        """只删除 _displayOrder 中的选中任务，不删除被筛选掉的。"""
        from app.models.task import TaskStatus
        from app.view.pages.task_page import FilterMode
        page, svc = env
        tasks = _addTasks(svc, 5)
        tasks[0].status = TaskStatus.COMPLETED
        for t in tasks[1:]:
            t.status = TaskStatus.WAITING

        page.setSelectionMode(True)
        page.selectAll()
        page.setFilterMode(FilterMode.ACTIVE)

        page._onDeleteConfirmed(shouldDeleteFiles=False)
        deletedIds = {tid for tid, _ in svc._deleted}
        assert "t0" not in deletedIds

    def test_move_category_selected(self, env):
        page, svc = env
        _addTasks(svc, 3)
        page.setSelectionMode(True)
        page._selectedIds.update(["t0", "t2"])

        targets = [
            task for taskId in page._displayOrder
            if taskId in page._selectedIds and (task := svc.taskById(taskId))
        ]
        assert len(targets) == 2
        for task in targets:
            svc.setCategory(task, "cat1")
        assert svc._categories["t0"] == "cat1"
        assert svc._categories["t2"] == "cat1"

    def test_redownload_only_displayed(self, env):
        """重下载只操作当前 displayOrder 中的选中任务。"""
        from app.models.task import TaskStatus
        from app.view.pages.task_page import FilterMode
        page, svc = env
        tasks = _addTasks(svc, 5)
        tasks[0].status = TaskStatus.COMPLETED
        for t in tasks[1:]:
            t.status = TaskStatus.WAITING

        page.setSelectionMode(True)
        page.selectAll()
        page.setFilterMode(FilterMode.ACTIVE)

        page._onRedownloadSelected()
        assert "t0" not in svc._redownloaded


# ─── _onFileDisappeared ──────────────────────────────────────

class TestFileDisappeared:

    def test_refresh_visible_card(self, env):
        page, svc = env
        tasks = _addTasks(svc, 3)
        card = page._liveCards.get("t0")
        assert card is not None
        card.refresh = MagicMock()
        svc.fileDisappeared.emit(tasks[0])
        assert card.refresh.called
        assert card.refresh.call_args == ((True,),) or \
               card.refresh.call_args.kwargs.get("force") is True

    def test_ignore_offscreen_card(self, env):
        page, svc = env
        tasks = _addTasks(svc, 50)
        # 默认 createdAt 降序，最早创建的 t0 排在最底部（index 49），应在视口外
        offscreen = tasks[0]
        assert offscreen.taskId not in page._liveCards
        svc.fileDisappeared.emit(offscreen)


# ─── _refreshVisibleCards ────────────────────────────────────

class TestRefreshVisibleCards:

    def test_refreshes_all_live_cards(self, env):
        page, svc = env
        _addTasks(svc, 5)
        mocks = {}
        for tid, card in page._liveCards.items():
            m = MagicMock()
            card.refresh = m
            mocks[tid] = m

        page._refreshVisibleCards()
        for tid, m in mocks.items():
            assert m.called, f"Card {tid} should have been refreshed"


# ─── Delete 快捷键 ───────────────────────────────────────────

class TestDeleteShortcut:

    def test_delete_key_triggers_delete_dialog(self, env):
        from unittest.mock import patch as _patch
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent
        page, svc = env
        _addTasks(svc, 3)
        page.setSelectionMode(True)
        page._selectedIds.update(["t0", "t1"])

        with _patch.object(page, "_onDeleteSelected") as mock:
            event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
            page.keyPressEvent(event)
            assert mock.called

    def test_delete_key_ignored_outside_selection_mode(self, env):
        from unittest.mock import patch as _patch
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent
        page, svc = env
        _addTasks(svc, 3)

        with _patch.object(page, "_onDeleteSelected") as mock:
            event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
            page.keyPressEvent(event)
            assert not mock.called


# ─── BandSelector ────────────────────────────────────────────

class TestBandSelector:

    def test_band_selector_exists(self, env):
        page, svc = env
        assert hasattr(page, "_bandSelector")
        from app.view.components.band_selector import BandSelector
        assert isinstance(page._bandSelector, BandSelector)

    def test_band_drag_started_enters_selection_mode(self, env):
        page, svc = env
        _addTasks(svc, 10)
        assert page._isSelectionMode is False
        page._onBandDragStarted(False)
        assert page._isSelectionMode is True

    def test_band_drag_started_with_shift_saves_snapshot(self, env):
        page, svc = env
        _addTasks(svc, 10)
        page.setSelectionMode(True)
        page._selectedIds.update(["t8", "t9"])
        page._onBandDragStarted(True)
        assert page._bandSnapshot == {"t8", "t9"}

    def test_band_drag_started_without_shift_clears_snapshot(self, env):
        page, svc = env
        _addTasks(svc, 10)
        page.setSelectionMode(True)
        page._selectedIds.update(["t8", "t9"])
        page._onBandDragStarted(False)
        assert page._bandSnapshot == set()

    def test_band_changed_selects_range(self, env):
        page, svc = env
        _addTasks(svc, 10)
        page._onBandDragStarted(False)
        # 选中 displayOrder 中 index 0..2（降序排列: t9, t8, t7）
        page._onBandChanged(0, 2)
        assert len(page._selectedIds) == 3
        assert page._displayOrder[0] in page._selectedIds
        assert page._displayOrder[1] in page._selectedIds
        assert page._displayOrder[2] in page._selectedIds

    def test_band_changed_replaces_previous(self, env):
        page, svc = env
        _addTasks(svc, 10)
        page._onBandDragStarted(False)
        page._onBandChanged(0, 4)
        assert len(page._selectedIds) == 5
        page._onBandChanged(2, 3)
        assert len(page._selectedIds) == 2

    def test_band_changed_with_shift_appends(self, env):
        page, svc = env
        _addTasks(svc, 10)
        page.setSelectionMode(True)
        page._selectedIds.update(["t0", "t1"])
        page._onBandDragStarted(True)
        page._onBandChanged(0, 2)
        # 原来的 t0, t1 + band 选中的 3 个
        assert "t0" in page._selectedIds
        assert "t1" in page._selectedIds
        assert len(page._selectedIds) >= 3

    def test_band_changed_negative_clears(self, env):
        page, svc = env
        _addTasks(svc, 10)
        page._onBandDragStarted(False)
        page._onBandChanged(0, 2)
        assert len(page._selectedIds) == 3
        page._onBandChanged(-1, -1)
        assert len(page._selectedIds) == 0

    def test_band_finished_exits_if_empty(self, env):
        page, svc = env
        _addTasks(svc, 10)
        page._onBandDragStarted(False)
        page._onBandChanged(-1, -1)
        page._onBandDragFinished()
        assert page._isSelectionMode is False

    def test_band_finished_stays_if_selected(self, env):
        page, svc = env
        _addTasks(svc, 10)
        page._onBandDragStarted(False)
        page._onBandChanged(0, 2)
        page._onBandDragFinished()
        assert page._isSelectionMode is True
        assert len(page._selectedIds) == 3

    def test_band_syncs_live_card_checkboxes(self, env):
        page, svc = env
        _addTasks(svc, 5)
        page._onBandDragStarted(False)
        page._onBandChanged(0, len(page._displayOrder) - 1)
        for card in page._liveCards.values():
            assert card.isChecked()

    def test_band_selector_disabled_on_item_count_change(self, env):
        page, svc = env
        _addTasks(svc, 10)
        page._bandSelector._isDragging = True
        page._bandSelector.setItemCount(5)
        assert page._bandSelector._isDragging is False

    def test_set_enabled_false_clears_drag(self, env):
        page, svc = env
        _addTasks(svc, 10)
        page._bandSelector._isDragging = True
        page._bandSelector.setEnabled(False)
        assert page._bandSelector._isDragging is False


# ─── 卸载推迟（嵌套事件循环安全） ─────────────────────────────

class TestUnmountDeferral:

    def test_unmount_deferred_inside_nested_loop(self, env):
        """嵌套循环（对话框 exec）中卸载的卡片推迟真删，回主循环后回收。"""
        import shiboken6
        from PySide6.QtCore import QEventLoop, QTimer

        page, svc = env
        tasks = _addTasks(svc, 5)
        cardId = tasks[0].taskId
        card = page._liveCards[cardId]

        results = {}
        outer, inner = QEventLoop(), QEventLoop()

        def innerBody():  # loopLevel == 2，模拟对话框 exec 期间
            svc.removeTask(cardId)
            app.processEvents()
            results["alive"] = shiboken6.isValid(card)
            results["hidden"] = not card.isVisible()
            results["pending"] = card in page._pendingUnmounts
            inner.quit()

        def outerBody():  # loopLevel == 1，模拟主循环
            QTimer.singleShot(0, innerBody)
            inner.exec()
            outer.quit()

        QTimer.singleShot(0, outerBody)
        outer.exec()

        assert results == {"alive": True, "hidden": True, "pending": True}

        def reap():  # loopLevel == 1：刷新触发回收
            page._refreshViewport()
            outer.quit()

        QTimer.singleShot(0, reap)
        outer.exec()
        app.processEvents()  # DeferredDelete 需回到更浅层级才执行

        assert not page._pendingUnmounts
        assert not shiboken6.isValid(card)

    def test_unmount_immediate_at_main_loop(self, env):
        """无嵌套循环时卸载走 deleteLater，不积压。"""
        page, svc = env
        tasks = _addTasks(svc, 5)
        svc.removeTask(tasks[0].taskId)
        assert not page._pendingUnmounts


# ─── 拖拽队列投递 ─────────────────────────────────────────────

class TestDragRequestedQueued:

    def test_drag_starts_from_page_frame(self, env, monkeypatch):
        """dragRequested 队列投递：emit 同步阶段不启动拖拽，事件循环后启动。"""
        from app.models.task import TaskStatus

        page, svc = env
        tasks = _addTasks(svc, 3, status=TaskStatus.COMPLETED)
        card = page._liveCards[tasks[0].taskId]

        calls = []
        monkeypatch.setattr("app.platform.desktop.startFileDrag",
                            lambda paths, source: calls.append(paths))

        card.dragRequested.emit(tasks[0].taskId)
        assert not calls  # 直连会立刻执行；队列投递此刻必须为空

        app.processEvents()
        assert calls == [[Path(tasks[0].outputPath)]]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
