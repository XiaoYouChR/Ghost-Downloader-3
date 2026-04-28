# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportAny=false, reportExplicitAny=false, reportImplicitOverride=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportUnusedCallResult=false, reportUnnecessaryCast=false, reportUnannotatedClassAttribute=false, reportUnusedParameter=false

from __future__ import annotations

import asyncio
import importlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any
from typing import cast
from unittest.mock import patch

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

import libtorrent as lt
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QDialog
from PySide6.QtWidgets import QWidget

from app.feature_pack.api import DefaultFeatureService
from app.feature_pack.api import DefaultResultCard
from app.feature_pack.api import DefaultTaskCard
from app.feature_pack.api import MultiFileTask
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskInput
from app.feature_pack.api import TaskStage
from app.feature_pack.internal import buildBrowserTaskSummary
from app.feature_pack.internal.recorder import TaskRecorder


class _FakeWindow:
    def __init__(self) -> None:
        self.installed: list[str] = []


def ensureApplication() -> QApplication:
    application = QApplication.instance()
    if application is not None:
        return cast(QApplication, application)

    return QApplication([])


async def noAdditionalTrackers() -> list[str]:
    return []


class BitTorrentPackV1Tests(unittest.TestCase):
    application: QApplication | None = None
    _temporaryDirectory: tempfile.TemporaryDirectory[str] | None = None
    workspace: Path = ROOT
    torrentPath: Path = ROOT / "sample.torrent"

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = ensureApplication()

    def setUp(self) -> None:
        temporaryDirectory = tempfile.TemporaryDirectory()
        self._temporaryDirectory = temporaryDirectory
        self.addCleanup(temporaryDirectory.cleanup)
        self.workspace = Path(temporaryDirectory.name)
        shutil.copytree(ROOT / "features" / "bittorrent_pack", self.workspace / "bittorrent_pack")
        self.torrentPath = self.createSampleTorrent()
        self.resetBitTorrentPackRegistries()

    def resetBitTorrentPackRegistries(self) -> None:
        Task.__recordRegistry__.pop(("bittorrent_pack", "bittorrent_download", 1), None)
        TaskStage.__recordRegistry__.pop(
            (
                "bittorrent_pack",
                "bittorrent_download",
                1,
                "bittorrent_download",
                1,
            ),
            None,
        )
        for moduleName in list(sys.modules):
            if moduleName.startswith("_ghost_feature_pack_bittorrent_pack"):
                del sys.modules[moduleName]
            if moduleName.startswith("features.bittorrent_pack"):
                del sys.modules[moduleName]
            if moduleName.startswith("bittorrent_pack"):
                del sys.modules[moduleName]

    def createService(self) -> DefaultFeatureService:
        service = DefaultFeatureService(featuresPath=self.workspace)
        service.loadPacks(_FakeWindow())
        return service

    def taskModule(self) -> ModuleType:
        return cast(ModuleType, importlib.import_module("_ghost_feature_pack_bittorrent_pack.task"))

    def buildTaskInput(
        self,
        *,
        source: str | None = None,
        name: str = "",
    ) -> TaskInput:
        return TaskInput(
            config=TaskConfig(
                source=source or str(self.torrentPath),
                folder=self.workspace / "downloads",
                name=name,
                proxies={"http": "http://127.0.0.1:7890"},
            ),
        )

    def createSampleTorrent(self) -> Path:
        sourceRoot = self.workspace / "torrent-source"
        seasonRoot = sourceRoot / "Season 1"
        seasonRoot.mkdir(parents=True)
        _ = (seasonRoot / "episode-1.txt").write_bytes(b"abc")
        _ = (seasonRoot / "episode-2.txt").write_bytes(b"defg")

        fileStorage = lt.file_storage()
        lt.add_files(fileStorage, str(seasonRoot))
        torrent = lt.create_torrent(fileStorage)
        torrent.add_tracker("udp://tracker.example:80/announce")
        lt.set_piece_hashes(torrent, str(sourceRoot))

        torrentPath = self.workspace / "season.torrent"
        _ = torrentPath.write_bytes(lt.bencode(torrent.generate()))
        return torrentPath

    def createTorrentTask(self) -> Task:
        service = self.createService()
        taskModule = self.taskModule()
        with patch.object(taskModule, "_resolveAdditionalTrackers", noAdditionalTrackers):
            return asyncio.run(service.createTask(self.buildTaskInput()))

    def showWidget(self, widget: QWidget) -> None:
        widget.show()
        application = self.application
        assert application is not None
        application.processEvents()
        self.addCleanup(widget.close)
        self.addCleanup(widget.deleteLater)

    def createParent(self) -> QWidget:
        parent = QWidget()
        parent.resize(960, 720)
        self.showWidget(parent)
        return parent

    def testBitTorrentPackCreatesMultiFileTaskFromTorrentInput(self) -> None:
        service = self.createService()
        taskModule = self.taskModule()

        with patch.object(taskModule, "_resolveAdditionalTrackers", noAdditionalTrackers):
            routedPack = service.packForSource(str(self.torrentPath))
            magnetPack = service.packForSource("magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567")
            task = asyncio.run(service.createTask(self.buildTaskInput()))

        self.assertIsNotNone(routedPack)
        self.assertIsNotNone(magnetPack)
        if routedPack is None or magnetPack is None:
            raise AssertionError("bittorrent_pack should route torrent and magnet sources")
        self.assertEqual(routedPack.manifest.id, "bittorrent_pack")
        self.assertEqual(magnetPack.manifest.id, "bittorrent_pack")

        self.assertIsInstance(task, MultiFileTask)
        self.assertEqual(type(task).__name__, "BitTorrentTask")
        self.assertEqual(task.packId, "bittorrent_pack")
        self.assertEqual(task.kind, "bittorrent_download")
        self.assertEqual(task.config.name, "Season 1")
        self.assertEqual(task.fileCount, 2)
        self.assertEqual(task.selectedCount, 2)
        self.assertEqual(task.selectedIds, {"file-0", "file-2"})
        self.assertEqual(task.snapshot().target, str(self.workspace / "downloads" / "Season 1"))
        self.assertEqual(task.snapshot().totalBytes, 7)

        self.assertEqual(
            [(file.id, file.path, file.size, file.selected) for file in task.files],
            [
                ("file-0", "Season 1/episode-1.txt", 3, True),
                ("file-2", "Season 1/episode-2.txt", 4, True),
            ],
        )
        self.assertEqual(cast(Any, task).filePriorities(), [4, 0, 4])
        self.assertEqual(type(task.stages[0]).__name__, "BitTorrentTaskStage")
        self.assertEqual(cast(str, getattr(task.stages[0], "resolvePath")), str(self.workspace / "downloads" / "Season 1"))

        packForTask = service.packForTask(task)
        self.assertIsNotNone(packForTask)
        if packForTask is None:
            raise AssertionError("BitTorrent task should route back to BitTorrent Pack")
        self.assertEqual(packForTask.manifest.id, "bittorrent_pack")

    def testBitTorrentTaskUsesDefaultCardsAndDefaultEditFlowForSelectionAndConfig(self) -> None:
        service = self.createService()
        taskModule = self.taskModule()
        with patch.object(taskModule, "_resolveAdditionalTrackers", noAdditionalTrackers):
            task = asyncio.run(service.createTask(self.buildTaskInput()))

        taskCard = cast(DefaultTaskCard, service.createTaskCard(task, self.createParent()))
        resultCard = service.createResultCard(task, self.createParent())
        self.showWidget(taskCard)
        self.showWidget(cast(QWidget, resultCard))

        self.assertIsInstance(taskCard, DefaultTaskCard)
        self.assertIsInstance(resultCard, DefaultResultCard)
        self.assertEqual(taskCard.nameLabel.text(), "Season 1")

        updatedConfig = TaskConfig(
            source=task.config.source,
            folder=self.workspace / "archive",
            name="Renamed Season",
            headers=task.config.headers,
            proxies={"https": "socks5://127.0.0.1:1080"},
        )

        with patch("app.feature_pack.api.service.TaskConfigDialog") as dialogMock:
            dialog = dialogMock.return_value
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            dialog.selectedIds.return_value = {"file-2"}
            dialog.config.return_value = updatedConfig

            QTest.mouseClick(taskCard.editButton, Qt.MouseButton.LeftButton)

        self.assertEqual(task.selectedIds, {"file-2"})
        self.assertEqual(task.selectedCount, 1)
        self.assertEqual(cast(Any, task).filePriorities(), [0, 0, 4])
        self.assertEqual(task.config, updatedConfig)
        self.assertEqual(task.snapshot().totalBytes, 4)
        self.assertEqual(task.snapshot().target, str(self.workspace / "archive" / "Renamed Season"))
        self.assertEqual(cast(str, getattr(task.stages[0], "resolvePath")), str(self.workspace / "archive" / "Renamed Season"))

    def testBitTorrentTaskRecorderRestoresSelectionAndBrowserProjection(self) -> None:
        service = self.createService()
        taskModule = self.taskModule()
        with patch.object(taskModule, "_resolveAdditionalTrackers", noAdditionalTrackers):
            task = asyncio.run(service.createTask(self.buildTaskInput()))

        task = cast(Any, task)
        task.select({"file-0"})
        task.resumeData = "cmVzdW1l"
        stage = task.stages[0]
        getattr(stage, "setStatus")("running", emitSignals=False, notifyTask=False)
        getattr(stage, "updateTransfer")(
            doneBytes=2,
            speed=11,
            progress=66.0,
            notifyTask=False,
        )
        task.files[0].doneBytes = 2
        task.syncStatusFromStages()

        recorder = TaskRecorder(recordFile=self.workspace / "FeaturePackMemory.log")
        recorder.load()
        recorder.add(task, flush=True)
        record = recorder.serializeTask(cast(Task, task))
        restored = recorder.read()[task.id]

        self.assertEqual(record["packId"], "bittorrent_pack")
        self.assertEqual(record["kind"], "bittorrent_download")
        self.assertEqual(record["version"], 1)
        self.assertNotIn("type", record)
        self.assertEqual(type(restored).__name__, "BitTorrentTask")
        self.assertIsInstance(restored, MultiFileTask)
        self.assertEqual(restored.selectedIds, {"file-0"})
        self.assertEqual(restored.selectedCount, 1)
        self.assertEqual(restored.fileCount, 2)
        self.assertEqual(restored.snapshot().state, "running")
        self.assertEqual(restored.snapshot().doneBytes, 2)
        self.assertEqual(restored.snapshot().totalBytes, 3)
        self.assertEqual(
            [(file.id, file.path, file.selected, file.doneBytes) for file in restored.files],
            [
                ("file-0", "Season 1/episode-1.txt", True, 2),
                ("file-2", "Season 1/episode-2.txt", False, 0),
            ],
        )

        summary = buildBrowserTaskSummary(restored)
        self.assertEqual(summary.id, restored.id)
        self.assertEqual(summary.packId, "bittorrent_pack")
        self.assertEqual(summary.kind, "bittorrent_download")
        self.assertEqual(summary.name, "Season 1")
        self.assertEqual(summary.state, "running")
        self.assertEqual(summary.target, str(self.workspace / "downloads" / "Season 1"))
        self.assertEqual(summary.folder, str(self.workspace / "downloads"))
        self.assertEqual(summary.totalBytes, 3)
        self.assertEqual(summary.speed, 11)


if __name__ == "__main__":
    _ = unittest.main()
