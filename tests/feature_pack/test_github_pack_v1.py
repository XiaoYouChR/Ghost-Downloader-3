# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportAny=false, reportExplicitAny=false, reportImplicitOverride=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportUnusedCallResult=false, reportUnnecessaryCast=false

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
from unittest.mock import AsyncMock
from unittest.mock import patch

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QDialog
from PySide6.QtWidgets import QWidget

from app.feature_pack.api import DefaultFeatureService
from app.feature_pack.api import DefaultResultCard
from app.feature_pack.api import DefaultTaskCard
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskInput
from app.feature_pack.api import TaskStage


class _FakeWindow:
    def __init__(self) -> None:
        self.installed: list[str] = []


def ensureApplication() -> QApplication:
    application = QApplication.instance()
    if application is not None:
        return cast(QApplication, application)

    return QApplication([])


class GitHubPackV1Tests(unittest.TestCase):
    application: QApplication | None = None
    _temporaryDirectory: tempfile.TemporaryDirectory[str] | None = None
    workspace: Path = ROOT

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = ensureApplication()

    def setUp(self) -> None:
        temporaryDirectory = tempfile.TemporaryDirectory()
        self._temporaryDirectory = temporaryDirectory
        self.addCleanup(temporaryDirectory.cleanup)
        self.workspace = Path(temporaryDirectory.name)
        for packName in ("http_pack", "github_pack"):
            shutil.copytree(ROOT / "features" / packName, self.workspace / packName)
        self.resetPackRegistries()

    def resetPackRegistries(self) -> None:
        Task.__recordRegistry__.pop(("http_pack", "http_download", 1), None)
        Task.__recordRegistry__.pop(("github_pack", "github_download", 1), None)
        TaskStage.__recordRegistry__.pop(("http_pack", "http_download", 1, "http_download", 1), None)
        TaskStage.__recordRegistry__.pop(("github_pack", "github_download", 1, "http_download", 1), None)
        for moduleName in list(sys.modules):
            if moduleName.startswith("_ghost_feature_pack_http_pack"):
                del sys.modules[moduleName]
            if moduleName.startswith("_ghost_feature_pack_github_pack"):
                del sys.modules[moduleName]

    def createService(self) -> DefaultFeatureService:
        service = DefaultFeatureService(featuresPath=self.workspace)
        service.loadPacks(_FakeWindow())
        return service

    def module(self, moduleName: str) -> ModuleType:
        return cast(ModuleType, importlib.import_module(moduleName))

    def enableGitHub(self, githubModule: ModuleType) -> None:
        githubConfig = cast(Any, getattr(githubModule, "githubConfig"))
        githubConfig.enabled.value = True

    def buildTaskInput(
        self,
        *,
        source: str = "https://github.com/owner/project/releases/download/v1.0/release.zip",
        name: str = "",
    ) -> TaskInput:
        return TaskInput(
            config=TaskConfig(
                source=source,
                folder=self.workspace / "downloads",
                name=name,
                headers={"User-Agent": "Ghost Downloader"},
                proxies={"https": "http://127.0.0.1:7890"},
                chunks=6,
            ),
        )

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

    def testGitHubPackRoutesBeforeGenericHttpAndCreatesProxiedHttpTask(self) -> None:
        service = self.createService()
        githubModule = self.module("_ghost_feature_pack_github_pack")
        githubTaskModule = self.module("_ghost_feature_pack_github_pack.task")
        self.enableGitHub(githubModule)

        probe = AsyncMock(
            return_value=(
                4096,
                True,
                "https://gh.example/https://github.com/owner/project/releases/download/v1.0/release.zip",
                {
                    "content-disposition": 'attachment; filename="release.zip"',
                },
            )
        )
        originalSource = "https://github.com/owner/project/releases/download/v1.0/release.zip"

        with patch.object(
            githubModule,
            "getSelectedProxySite",
            return_value="https://gh.example",
        ), patch.object(
            githubTaskModule,
            "getSelectedProxySite",
            return_value="https://gh.example",
        ), patch(
            "_ghost_feature_pack_http_pack.pack._probeDownloadInfo",
            new=probe,
        ):
            routedPack = service.packForSource(originalSource)
            task = asyncio.run(service.createTask(self.buildTaskInput(source=originalSource)))

        self.assertIsNotNone(routedPack)
        if routedPack is None:
            raise AssertionError("GitHub Pack should route before generic HTTP Pack")
        self.assertEqual(routedPack.manifest.id, "github_pack")

        self.assertEqual(type(task).__name__, "GitHubDownloadTask")
        self.assertEqual(task.packId, "github_pack")
        self.assertEqual(task.kind, "github_download")
        self.assertEqual(task.config.source, originalSource)
        self.assertEqual(task.config.name, "release.zip")
        self.assertEqual(task.snapshot().target, str(self.workspace / "downloads" / "release.zip"))
        self.assertEqual(task.snapshot().totalBytes, 4096)

        stage = task.stages[0]
        self.assertEqual(type(stage).__name__, "GitHubHttpTaskStage")
        self.assertEqual(cast(str, getattr(stage, "url")), f"https://gh.example/{originalSource}")
        self.assertEqual(cast(str, getattr(stage, "resolvePath")), str(self.workspace / "downloads" / "release.zip"))
        self.assertEqual(cast(int, getattr(stage, "blockNum")), 6)

        packForTask = service.packForTask(task)
        self.assertIsNotNone(packForTask)
        if packForTask is None:
            raise AssertionError("GitHub task should route back to GitHub Pack")
        self.assertEqual(packForTask.manifest.id, "github_pack")

        probe.assert_awaited_once()
        self.assertEqual(cast(Any, probe).await_args.args[0], f"https://gh.example/{originalSource}")

    def testGitHubPackAcceptsOnlySupportedEnabledGithubFileUrls(self) -> None:
        service = self.createService()
        githubModule = self.module("_ghost_feature_pack_github_pack")
        githubTaskModule = self.module("_ghost_feature_pack_github_pack.task")
        self.enableGitHub(githubModule)
        pack = service.pack("github_pack")
        self.assertIsNotNone(pack)
        if pack is None:
            raise AssertionError("github_pack 未加载")

        with patch.object(
            githubModule,
            "getSelectedProxySite",
            return_value="https://gh.example",
        ), patch.object(
            githubTaskModule,
            "getSelectedProxySite",
            return_value="https://gh.example",
        ):
            self.assertTrue(pack.accepts("https://github.com/owner/project/archive/refs/heads/main.zip"))
            self.assertTrue(pack.accepts("https://raw.githubusercontent.com/owner/project/main/file.txt"))
            self.assertTrue(pack.accepts("https://github.com/owner/project/releases/latest/download/app.exe"))
            self.assertFalse(pack.accepts("https://github.com/owner/project/issues/1"))
            self.assertFalse(pack.accepts("https://example.com/owner/project/releases/download/app.exe"))

        githubConfig = cast(Any, getattr(githubModule, "githubConfig"))
        githubConfig.enabled.value = False
        with patch.object(githubModule, "getSelectedProxySite", return_value="https://gh.example"):
            self.assertFalse(pack.accepts("https://github.com/owner/project/releases/download/v1/app.exe"))

    def testGitHubPackUsesDefaultCardsAndKeepsOriginalSourceWhenEditing(self) -> None:
        service = self.createService()
        githubModule = self.module("_ghost_feature_pack_github_pack")
        githubTaskModule = self.module("_ghost_feature_pack_github_pack.task")
        self.enableGitHub(githubModule)

        originalSource = "https://github.com/owner/project/releases/download/v1.0/release.zip"
        with patch.object(
            githubModule,
            "getSelectedProxySite",
            return_value="https://gh.example",
        ), patch.object(
            githubTaskModule,
            "getSelectedProxySite",
            return_value="https://gh.example",
        ), patch(
            "_ghost_feature_pack_http_pack.pack._probeDownloadInfo",
            new=AsyncMock(
                return_value=(
                    1024,
                    True,
                    f"https://gh.example/{originalSource}",
                    {
                        "content-disposition": 'attachment; filename="release.zip"',
                    },
                )
            ),
        ):
            task = asyncio.run(service.createTask(self.buildTaskInput(source=originalSource, name="release.zip")))

        taskCard = cast(DefaultTaskCard, service.createTaskCard(task, self.createParent()))
        resultCard = service.createResultCard(task, self.createParent())
        self.showWidget(taskCard)
        self.showWidget(cast(QWidget, resultCard))

        self.assertIsInstance(taskCard, DefaultTaskCard)
        self.assertIsInstance(resultCard, DefaultResultCard)
        self.assertEqual(taskCard.nameLabel.text(), "release.zip")

        updatedSource = "https://raw.githubusercontent.com/owner/project/main/app.zip"
        updatedConfig = TaskConfig(
            source=updatedSource,
            folder=self.workspace / "archive",
            name="renamed.zip",
            headers={"Accept": "application/octet-stream"},
            proxies=None,
            chunks=3,
        )

        with patch.object(
            githubTaskModule,
            "getSelectedProxySite",
            return_value="https://mirror.example",
        ), patch("app.feature_pack.api.service.TaskConfigDialog") as dialogMock:
            dialog = dialogMock.return_value
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            dialog.selectedIds.return_value = set()
            dialog.config.return_value = updatedConfig

            QTest.mouseClick(taskCard.editButton, Qt.MouseButton.LeftButton)

        self.assertEqual(task.config.source, updatedSource)
        self.assertEqual(task.snapshot().target, str(self.workspace / "archive" / "renamed.zip"))
        self.assertEqual(cast(str, getattr(task, "url")), updatedSource)
        self.assertEqual(cast(str, getattr(task, "proxySource")), f"https://mirror.example/{updatedSource}")
        self.assertEqual(cast(str, getattr(task.stages[0], "url")), f"https://mirror.example/{updatedSource}")
        self.assertEqual(cast(str, getattr(task.stages[0], "resolvePath")), str(self.workspace / "archive" / "renamed.zip"))


if __name__ == "__main__":
    _ = unittest.main()
