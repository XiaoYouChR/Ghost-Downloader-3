# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportAny=false, reportImplicitOverride=false

from __future__ import annotations

import asyncio
import shutil
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import cast
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api import DefaultFeatureService
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskInput
from app.feature_pack.api import TaskStage
from app.feature_pack.internal.recorder import TaskRecorder


class _FakeWindow:
    def __init__(self) -> None:
        self.installed: list[str] = []


class ExtractPackV1Tests(unittest.TestCase):
    _temporaryDirectory: tempfile.TemporaryDirectory[str] | None = None
    workspace: Path = ROOT

    def setUp(self) -> None:
        temporaryDirectory = tempfile.TemporaryDirectory()
        self._temporaryDirectory = temporaryDirectory
        self.addCleanup(temporaryDirectory.cleanup)
        self.workspace = Path(temporaryDirectory.name)
        shutil.copytree(ROOT / "features" / "extract_pack", self.workspace / "extract_pack")
        self.resetExtractPackRegistries()

    def resetExtractPackRegistries(self) -> None:
        Task.__recordRegistry__.pop(("extract_pack", "extract_archive", 1), None)
        TaskStage.__recordRegistry__.pop(
            ("extract_pack", "extract_archive", 1, "extract_archive", 1),
            None,
        )
        for moduleName in list(sys.modules):
            if moduleName.startswith("_ghost_feature_pack_extract_pack"):
                del sys.modules[moduleName]
            if moduleName.startswith("features.extract_pack"):
                del sys.modules[moduleName]
            if moduleName.startswith("extract_pack"):
                del sys.modules[moduleName]

    def createService(self) -> DefaultFeatureService:
        service = DefaultFeatureService(featuresPath=self.workspace)
        service.loadPacks(_FakeWindow())
        return service

    def createZipArchive(
        self,
        *,
        archiveName: str,
        entries: dict[str, bytes],
    ) -> Path:
        archivePath = self.workspace / archiveName
        with zipfile.ZipFile(archivePath, "w") as archive:
            for relativePath, content in entries.items():
                archive.writestr(relativePath, content)
        return archivePath

    def createTarArchive(
        self,
        *,
        archiveName: str,
        entries: dict[str, bytes],
    ) -> Path:
        archivePath = self.workspace / archiveName
        with tarfile.open(archivePath, "w:gz") as archive:
            for relativePath, content in entries.items():
                payload = tempfile.NamedTemporaryFile(delete=False)
                try:
                    payload.write(content)
                    payload.flush()
                    payload.close()
                    archive.add(
                        payload.name,
                        arcname=relativePath,
                    )
                finally:
                    Path(payload.name).unlink(missing_ok=True)
        return archivePath

    def buildTaskInput(
        self,
        *,
        archivePath: Path,
        installFolder: Path,
        name: str = "",
        executableNames: tuple[str, ...] = (),
        cleanupArchive: bool = True,
    ) -> TaskInput:
        return TaskInput(
            config=TaskConfig(
                source=str(archivePath),
                folder=installFolder,
                name=name,
                chunks=1,
            ),
            size=archivePath.stat().st_size,
            hints=(
                {
                    "executableNames": list(executableNames),
                    "cleanupArchive": cleanupArchive,
                },
            ),
        )

    def testExtractPackLoadsAndCreatesTaskFromTaskInput(self) -> None:
        archivePath = self.createZipArchive(
            archiveName="runtime.zip",
            entries={"runtime/bin/tool.exe": b"tool"},
        )
        service = self.createService()
        pack = service.pack("extract_pack")

        self.assertIsNotNone(pack)
        if pack is None:
            raise AssertionError("extract_pack 未加载")

        self.assertTrue(pack.accepts(str(archivePath)))
        self.assertFalse(pack.accepts("https://example.com/runtime.zip"))

        task = asyncio.run(
            pack.createTask(
                self.buildTaskInput(
                    archivePath=archivePath,
                    installFolder=self.workspace / "Runtime",
                    name="Runtime 安装",
                    executableNames=("tool.exe",),
                    cleanupArchive=False,
                )
            )
        )

        self.assertIsNotNone(task)
        if task is None:
            raise AssertionError("extract_pack 未创建任务")

        self.assertEqual(type(task).__name__, "ExtractTask")
        self.assertEqual(task.packId, "extract_pack")
        self.assertEqual(task.kind, "extract_archive")
        self.assertEqual(task.snapshot().name, "Runtime 安装")
        self.assertEqual(task.snapshot().target, str(self.workspace / "Runtime"))
        self.assertEqual(task.snapshot().totalBytes, archivePath.stat().st_size)
        self.assertEqual(service.packForTask(task), pack)

        stage = task.stages[0]
        self.assertEqual(type(stage).__name__, "ExtractStage")
        self.assertEqual(getattr(stage, "stageIndex"), 1)
        self.assertEqual(getattr(stage, "archivePath"), str(archivePath))
        self.assertEqual(getattr(stage, "installFolder"), str(self.workspace / "Runtime"))
        self.assertEqual(getattr(stage, "executableNames"), ["tool.exe"])
        self.assertFalse(cast(bool, getattr(stage, "cleanupArchive")))

    def testExtractTaskRunExtractsZipArchiveAndRecorderRestoresTask(self) -> None:
        archivePath = self.createZipArchive(
            archiveName="runtime.zip",
            entries={"runtime/bin/tool.exe": b"tool"},
        )
        service = self.createService()
        pack = service.pack("extract_pack")
        self.assertIsNotNone(pack)
        if pack is None:
            raise AssertionError("extract_pack 未加载")

        task = asyncio.run(
            pack.createTask(
                self.buildTaskInput(
                    archivePath=archivePath,
                    installFolder=self.workspace / "Runtime",
                    name="Runtime 安装",
                    executableNames=("tool.exe",),
                    cleanupArchive=True,
                )
            )
        )
        self.assertIsNotNone(task)
        if task is None:
            raise AssertionError("extract_pack 未创建任务")

        asyncio.run(task.run())

        executablePath = self.workspace / "Runtime" / "bin" / "tool.exe"
        self.assertTrue(executablePath.is_file())
        self.assertFalse(archivePath.exists())
        self.assertEqual(
            getattr(task.stages[0], "extractedExecutables"),
            {"tool.exe": str(executablePath).replace("\\", "/")},
        )
        self.assertEqual(task.snapshot().state, "completed")
        self.assertEqual(task.snapshot().progress, 100.0)
        self.assertGreater(task.snapshot().totalBytes, 0)

        with patch(
            "app.feature_pack.internal.recorder.QStandardPaths.writableLocation",
            return_value=str(self.workspace),
        ):
            recorder = TaskRecorder()

        recorder.load()
        recorder.add(task, flush=True)
        restored = recorder.read()[task.id]

        self.assertEqual(type(restored).__name__, "ExtractTask")
        self.assertEqual(restored.snapshot().state, "completed")
        self.assertEqual(restored.snapshot().target, str(self.workspace / "Runtime"))
        restoredStage = restored.stages[0]
        self.assertEqual(type(restoredStage).__name__, "ExtractStage")
        self.assertEqual(
            getattr(restoredStage, "extractedExecutables"),
            {"tool.exe": str(executablePath).replace("\\", "/")},
        )

    def testExtractTaskRunSupportsTarGzWithoutDeletingArchive(self) -> None:
        archivePath = self.createTarArchive(
            archiveName="runtime.tar.gz",
            entries={"runtime/bin/tool.exe": b"tool"},
        )
        service = self.createService()
        pack = service.pack("extract_pack")
        self.assertIsNotNone(pack)
        if pack is None:
            raise AssertionError("extract_pack 未加载")

        task = asyncio.run(
            pack.createTask(
                self.buildTaskInput(
                    archivePath=archivePath,
                    installFolder=self.workspace / "Runtime",
                    executableNames=("tool.exe",),
                    cleanupArchive=False,
                )
            )
        )
        self.assertIsNotNone(task)
        if task is None:
            raise AssertionError("extract_pack 未创建任务")

        asyncio.run(task.run())

        executablePath = self.workspace / "Runtime" / "bin" / "tool.exe"
        self.assertTrue(archivePath.exists())
        self.assertTrue(executablePath.is_file())
        self.assertEqual(task.snapshot().state, "completed")

    def testExtractTaskRejectsUnsafeArchiveEntries(self) -> None:
        archivePath = self.createZipArchive(
            archiveName="unsafe.zip",
            entries={"../escape.txt": b"escape"},
        )
        service = self.createService()
        pack = service.pack("extract_pack")
        self.assertIsNotNone(pack)
        if pack is None:
            raise AssertionError("extract_pack 未加载")

        task = asyncio.run(
            pack.createTask(
                self.buildTaskInput(
                    archivePath=archivePath,
                    installFolder=self.workspace / "Unsafe",
                    cleanupArchive=False,
                )
            )
        )
        self.assertIsNotNone(task)
        if task is None:
            raise AssertionError("extract_pack 未创建任务")

        with self.assertRaises(RuntimeError) as context:
            asyncio.run(task.run())

        self.assertIn("非法路径", str(context.exception))
        self.assertEqual(task.stages[0].snapshot().state, "failed")
        self.assertFalse((self.workspace / "escape.txt").exists())
        self.assertFalse((self.workspace / "Unsafe" / ".extracting").exists())


if __name__ == "__main__":
    _ = unittest.main()
