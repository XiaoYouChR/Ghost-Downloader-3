# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportAny=false, reportImplicitOverride=false, reportInconsistentConstructor=false

from __future__ import annotations

import asyncio
import shutil
import sys
import tarfile
import zipfile
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.feature_pack.api import TaskStatus
from app.feature_pack.api import FeaturePack
from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskInput
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage

_EXTRACT_PACK_ID = "extract_pack"
_EXTRACT_TASK_KIND = "extract_archive"
_EXTRACT_STAGE_KIND = "extract_archive"
_EXTRACT_TASK_VERSION = 1
_EXTRACT_STAGE_VERSION = 1
_DEFAULT_STAGE_NAME = "解压文件"


def _normalizePath(path: Path | str) -> str:
    return str(Path(path)).replace("\\", "/")


def _archiveSuffix(name: str) -> str:
    loweredName = name.lower()
    if loweredName.endswith(".tar.gz"):
        return ".tar.gz"
    return Path(name).suffix.lower()


def _safeJoin(root: Path, relative: str) -> Path:
    resolvedRoot = root.resolve()
    target = (root / relative).resolve()
    if resolvedRoot not in {target, *target.parents}:
        raise RuntimeError(f"压缩包包含非法路径: {relative}")
    return target


def _normalizeState(value: str | TaskStatus | object) -> str:
    if isinstance(value, TaskStatus):
        return value.name.lower()
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"completed", "failed", "paused", "running", "waiting"}:
            return normalized
    return "waiting"


def _legacyStatus(value: str) -> TaskStatus:
    return {
        "waiting": TaskStatus.WAITING,
        "running": TaskStatus.RUNNING,
        "paused": TaskStatus.PAUSED,
        "completed": TaskStatus.COMPLETED,
        "failed": TaskStatus.FAILED,
    }[_normalizeState(value)]


def _copyExecutableMap(
    value: Mapping[str, object] | None,
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, str] = {}
    for key, item in value.items():
        if isinstance(key, str) and isinstance(item, str):
            result[key] = item
    return result


def _supportsArchiveSource(source: str) -> bool:
    normalized = source.strip()
    if not normalized or "://" in normalized:
        return False
    return _archiveSuffix(normalized) in {".zip", ".tar.gz"}


def _notifyAttachedTask(task: object | None) -> None:
    if task is None:
        return

    syncStatus = getattr(task, "syncStatusFromStages", None)
    if callable(syncStatus):
        syncStatus()


def _normalizeExecutableNames(values: object) -> list[str]:
    if isinstance(values, str):
        return [values]
    if not isinstance(values, (list, tuple, set)):
        return []
    return [str(item) for item in values if isinstance(item, str)]


def _taskInputExecutableNames(hints: tuple[dict[str, Any], ...]) -> list[str]:
    names: list[str] = []
    for hint in hints:
        if not isinstance(hint, Mapping):
            continue
        names.extend(_normalizeExecutableNames(hint.get("executableNames")))
        rawName = hint.get("name")
        if isinstance(rawName, str):
            names.append(rawName)
    return names


def _taskInputCleanupArchive(hints: tuple[dict[str, Any], ...]) -> bool:
    for hint in hints:
        if isinstance(hint, Mapping) and isinstance(hint.get("cleanupArchive"), bool):
            return bool(hint.get("cleanupArchive"))
    return True


class ExtractStage(TaskStage):
    recordTaskPackId = _EXTRACT_PACK_ID
    recordTaskKind = _EXTRACT_TASK_KIND
    recordTaskVersion = _EXTRACT_TASK_VERSION
    recordKind = _EXTRACT_STAGE_KIND
    recordVersion = _EXTRACT_STAGE_VERSION

    def __init__(
        self,
        *,
        id: str | None = None,
        stageIndex: int = 1,
        archivePath: str,
        installFolder: str,
        executableNames: list[str],
        extractedExecutables: Mapping[str, str] | None = None,
        cleanupArchive: bool = True,
        kind: str = _EXTRACT_STAGE_KIND,
        version: int = _EXTRACT_STAGE_VERSION,
        name: str = _DEFAULT_STAGE_NAME,
        state: str | TaskStatus = "waiting",
        progress: float = 0.0,
        doneBytes: int = 0,
        speed: int = 0,
        error: str = "",
    ) -> None:
        super().__init__(
            id=id or f"extract-stage-{uuid4().hex}",
            kind=kind,
            version=version,
            name=name,
        )
        self.stageIndex = stageIndex
        self.archivePath = str(archivePath)
        self.installFolder = str(installFolder)
        self.executableNames = [str(item) for item in executableNames]
        self.extractedExecutables = dict(extractedExecutables or {})
        self.cleanupArchive = bool(cleanupArchive)
        self.state = _normalizeState(state)
        self.progress = max(0.0, min(float(progress), 100.0))
        self.doneBytes = max(0, int(doneBytes))
        self.speed = max(0, int(speed))
        self.error = str(error)

    @property
    def receivedBytes(self) -> int:
        return self.doneBytes

    @receivedBytes.setter
    def receivedBytes(self, value: int) -> None:
        self.doneBytes = max(0, int(value))

    @property
    def status(self) -> TaskStatus:
        return _legacyStatus(self.state)

    @status.setter
    def status(self, value: TaskStatus | str) -> None:
        self.setStatus(value, emitSignals=False)

    @property
    def stageId(self) -> str:
        return self.id

    def bindTask(self, task: object) -> None:
        self.attach(task)

    def canPause(self) -> bool:
        return False

    async def run(self) -> None:
        await ExtractWorker(self).run()

    def reset(self, notifyTask: bool = True) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.speed = 0
        self.error = ""
        self.extractedExecutables = {}
        if notifyTask:
            _notifyAttachedTask(getattr(self, "_task", None))
        self.stateChanged.emit(self.state)
        self.progressChanged.emit(self.progress)
        self.snapshotChanged.emit(self.snapshot())

    def configure(self, config: TaskConfig) -> None:
        source = str(config.source).strip()
        if source:
            self.archivePath = source
        installFolder = getattr(self, "installFolder", "")
        if not installFolder:
            self.installFolder = str(config.folder)

    def setStatus(
        self,
        status: TaskStatus | str,
        *,
        emitSignals: bool = True,
        notifyTask: bool = True,
    ) -> None:
        normalizedStatus = _normalizeState(status)
        progressChanged = False
        stateChanged = self.state != normalizedStatus

        self.state = normalizedStatus
        if normalizedStatus == "completed":
            if self.progress != 100.0:
                progressChanged = True
            self.progress = 100.0
            self.speed = 0
            self.error = ""
        elif normalizedStatus in {"paused", "waiting"}:
            self.speed = 0
            self.error = ""
        elif normalizedStatus == "failed":
            self.speed = 0

        if notifyTask:
            _notifyAttachedTask(getattr(self, "_task", None))

        if not emitSignals:
            return

        if stateChanged:
            self.stateChanged.emit(self.state)
        if progressChanged:
            self.progressChanged.emit(self.progress)
        self.snapshotChanged.emit(self.snapshot())

    def setError(self, error: Any, notifyTask: bool = True) -> None:
        message = repr(error).strip() if error is not None else ""
        self.error = message
        self.state = "failed"
        self.speed = 0
        if notifyTask:
            _notifyAttachedTask(getattr(self, "_task", None))
        self.stateChanged.emit(self.state)
        self.failed.emit(message)
        self.snapshotChanged.emit(self.snapshot())

    def updateTransfer(
        self,
        *,
        doneBytes: int,
        speed: int,
        progress: float,
        notifyTask: bool = True,
    ) -> None:
        self.doneBytes = max(0, int(doneBytes))
        self.speed = max(0, int(speed))
        self.progress = max(0.0, min(float(progress), 100.0))
        if notifyTask:
            _notifyAttachedTask(getattr(self, "_task", None))
        self.progressChanged.emit(self.progress)
        self.snapshotChanged.emit(self.snapshot())

    def snapshot(self) -> StageSnapshot:
        return StageSnapshot(
            id=self.id,
            kind=self.kind,
            name=self.name,
            state=self.state,
            progress=self.progress,
            doneBytes=self.doneBytes,
            speed=self.speed,
            error=self.error,
        )

    def persistenceState(self) -> dict[str, object]:
        return {
            "stageIndex": self.stageIndex,
            "archivePath": self.archivePath,
            "installFolder": self.installFolder,
            "executableNames": list(self.executableNames),
            "extractedExecutables": dict(self.extractedExecutables),
            "cleanupArchive": self.cleanupArchive,
            "state": self.state,
            "progress": self.progress,
            "doneBytes": self.doneBytes,
            "speed": self.speed,
            "error": self.error,
        }

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        rawStageIndex = state.get("stageIndex")
        rawArchivePath = state.get("archivePath")
        rawInstallFolder = state.get("installFolder")
        rawExecutableNames = state.get("executableNames")
        rawExecutables = state.get("extractedExecutables")
        rawCleanupArchive = state.get("cleanupArchive")
        rawState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawSpeed = state.get("speed")
        rawError = state.get("error")

        if isinstance(rawStageIndex, int) and not isinstance(rawStageIndex, bool):
            self.stageIndex = rawStageIndex
        if isinstance(rawArchivePath, str):
            self.archivePath = rawArchivePath
        if isinstance(rawInstallFolder, str):
            self.installFolder = rawInstallFolder
        if isinstance(rawExecutableNames, list):
            self.executableNames = [
                str(item)
                for item in rawExecutableNames
                if isinstance(item, str)
            ]
        self.extractedExecutables = _copyExecutableMap(
            rawExecutables if isinstance(rawExecutables, Mapping) else None
        )
        if isinstance(rawCleanupArchive, bool):
            self.cleanupArchive = rawCleanupArchive
        if isinstance(rawState, str):
            self.state = _normalizeState(rawState)
        if isinstance(rawProgress, int | float):
            self.progress = max(0.0, min(float(rawProgress), 100.0))
        if isinstance(rawDoneBytes, int) and not isinstance(rawDoneBytes, bool):
            self.doneBytes = max(0, rawDoneBytes)
        if isinstance(rawSpeed, int) and not isinstance(rawSpeed, bool):
            self.speed = max(0, rawSpeed)
        if isinstance(rawError, str):
            self.error = rawError

    @classmethod
    def createPersistentStage(
        cls,
        *,
        id: str,
        kind: str,
        version: int,
        name: str,
        state: Mapping[str, object],
    ) -> "ExtractStage":
        rawStageIndex = state.get("stageIndex")
        rawArchivePath = state.get("archivePath")
        rawInstallFolder = state.get("installFolder")
        rawExecutableNames = state.get("executableNames")
        rawExecutables = state.get("extractedExecutables")
        rawCleanupArchive = state.get("cleanupArchive")
        rawState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawSpeed = state.get("speed")
        rawError = state.get("error")

        return cls(
            id=id,
            stageIndex=rawStageIndex if isinstance(rawStageIndex, int) else 1,
            kind=kind,
            version=version,
            name=name,
            archivePath=rawArchivePath if isinstance(rawArchivePath, str) else "",
            installFolder=rawInstallFolder if isinstance(rawInstallFolder, str) else "",
            executableNames=(
                [str(item) for item in rawExecutableNames if isinstance(item, str)]
                if isinstance(rawExecutableNames, list)
                else []
            ),
            extractedExecutables=_copyExecutableMap(
                rawExecutables if isinstance(rawExecutables, Mapping) else None
            ),
            cleanupArchive=bool(rawCleanupArchive) if isinstance(rawCleanupArchive, bool) else True,
            state=rawState if isinstance(rawState, str) else "waiting",
            progress=float(rawProgress) if isinstance(rawProgress, int | float) else 0.0,
            doneBytes=rawDoneBytes if isinstance(rawDoneBytes, int) else 0,
            speed=rawSpeed if isinstance(rawSpeed, int) else 0,
            error=rawError if isinstance(rawError, str) else "",
        )


class ExtractTask(Task):
    recordPackId = _EXTRACT_PACK_ID
    recordKind = _EXTRACT_TASK_KIND
    recordVersion = _EXTRACT_TASK_VERSION

    def __init__(
        self,
        *,
        id: str | None = None,
        config: TaskConfig,
        stage: ExtractStage | None = None,
        stages: list[TaskStage] | None = None,
        state: str = "waiting",
        progress: float = 0.0,
        doneBytes: int = 0,
        totalBytes: int = 0,
        target: str = "",
    ) -> None:
        resolvedStage = stage
        if resolvedStage is None:
            if stages:
                firstStage = stages[0]
                if not isinstance(firstStage, ExtractStage):
                    raise TypeError(
                        f"ExtractTask requires ExtractStage, got {type(firstStage).__name__}"
                    )
                resolvedStage = firstStage
            else:
                resolvedStage = ExtractStage(
                    archivePath=str(config.source),
                    installFolder=str(config.folder),
                    executableNames=[],
                )

        self.state = _normalizeState(state)
        self.progress = max(0.0, min(float(progress), 100.0))
        self.doneBytes = max(0, int(doneBytes))
        self.archiveSize = max(0, int(totalBytes))
        self.totalBytes = max(0, int(totalBytes))
        self.target = str(target)
        super().__init__(
            id=id or f"extract-task-{uuid4().hex}",
            packId=_EXTRACT_PACK_ID,
            kind=_EXTRACT_TASK_KIND,
            version=_EXTRACT_TASK_VERSION,
            config=config,
            stages=[resolvedStage],
        )
        self.syncOutput()

    @property
    def archivePath(self) -> Path:
        return Path(self.config.source)

    @property
    def installFolder(self) -> Path:
        return self.config.folder

    @property
    def title(self) -> str:
        if self.config.name:
            return self.config.name
        archiveName = self.archivePath.name
        suffix = _archiveSuffix(archiveName)
        if suffix and archiveName.lower().endswith(suffix):
            return archiveName[: -len(suffix)] or archiveName
        return archiveName or "extract"

    @property
    def extractedExecutables(self) -> dict[str, str]:
        stage = self.extractStage()
        return dict(stage.extractedExecutables)

    @property
    def cleanupArchive(self) -> bool:
        return self.extractStage().cleanupArchive

    def extractStage(self) -> ExtractStage:
        stage = self.stages[0]
        if not isinstance(stage, ExtractStage):
            raise TypeError(f"Unexpected extract stage type: {type(stage).__name__}")
        return stage

    def syncOutput(self) -> None:
        self.target = str(self.installFolder)
        stage = self.extractStage()
        stage.archivePath = str(self.archivePath)
        stage.installFolder = self.target

    def syncStatusFromStages(self) -> TaskStatus:
        stage = self.extractStage()
        snapshot = stage.snapshot()
        self.state = snapshot.state
        self.progress = snapshot.progress
        self.doneBytes = snapshot.doneBytes
        self.totalBytes = max(self.totalBytes, snapshot.doneBytes)
        return _legacyStatus(self.state)

    async def run(self) -> None:
        try:
            await super().run()
            self.syncStatusFromStages()
        except Exception:
            self.syncStatusFromStages()
            raise

    def reset(self) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.currentStageIndex = 0
        for stage in self.stages:
            stage.reset()
        self.syncStatusFromStages()

    def snapshot(self) -> TaskSnapshot:
        stageSnapshots = self.stageSnapshots()
        totalBytes = self.totalBytes
        if totalBytes <= 0 and stageSnapshots:
            totalBytes = max(stageSnapshots[0].doneBytes, self.doneBytes)

        return TaskSnapshot(
            id=self.id,
            packId=self.packId,
            kind=self.kind,
            name=self.title,
            state=self.state,
            progress=self.progress,
            doneBytes=self.doneBytes,
            totalBytes=totalBytes,
            canPause=self.canPause(),
            target=self.target,
            stages=stageSnapshots,
        )

    def persistenceState(self) -> dict[str, object]:
        state = super().persistenceState()
        state.update(
            {
                "state": self.state,
                "progress": self.progress,
                "doneBytes": self.doneBytes,
                "archiveSize": self.archiveSize,
                "totalBytes": self.totalBytes,
                "target": self.target,
            }
        )
        return state

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        super().restorePersistentState(state)
        rawState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawArchiveSize = state.get("archiveSize")
        rawTotalBytes = state.get("totalBytes")
        rawTarget = state.get("target")

        if isinstance(rawState, str):
            self.state = _normalizeState(rawState)
        if isinstance(rawProgress, int | float):
            self.progress = max(0.0, min(float(rawProgress), 100.0))
        if isinstance(rawDoneBytes, int) and not isinstance(rawDoneBytes, bool):
            self.doneBytes = max(0, rawDoneBytes)
        if isinstance(rawArchiveSize, int) and not isinstance(rawArchiveSize, bool):
            self.archiveSize = max(0, rawArchiveSize)
        if isinstance(rawTotalBytes, int) and not isinstance(rawTotalBytes, bool):
            self.totalBytes = max(0, rawTotalBytes)
        if isinstance(rawTarget, str) and rawTarget:
            self.target = rawTarget
        self.syncOutput()

    @classmethod
    def createPersistentTask(
        cls,
        *,
        id: str,
        packId: str,
        kind: str,
        version: int,
        config: TaskConfig,
        stages: list[TaskStage],
        state: Mapping[str, object],
    ) -> "ExtractTask":
        _ = packId
        _ = kind
        _ = version
        if len(stages) != 1 or not isinstance(stages[0], ExtractStage):
            raise TypeError("ExtractTask restore requires exactly one ExtractStage")

        rawState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawArchiveSize = state.get("archiveSize")
        rawTotalBytes = state.get("totalBytes")
        rawTarget = state.get("target")
        return cls(
            id=id,
            config=config,
            stage=stages[0],
            state=rawState if isinstance(rawState, str) else "waiting",
            progress=float(rawProgress) if isinstance(rawProgress, int | float) else 0.0,
            doneBytes=rawDoneBytes if isinstance(rawDoneBytes, int) else 0,
            totalBytes=(
                rawArchiveSize
                if isinstance(rawArchiveSize, int)
                else rawTotalBytes
                if isinstance(rawTotalBytes, int)
                else 0
            ),
            target=rawTarget if isinstance(rawTarget, str) else "",
        )


class ExtractWorker:
    chunkSize = 1048576

    def __init__(self, stage: ExtractStage):
        self.stage = stage

    def _removePath(self, path: Path) -> None:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        else:
            with suppress(FileNotFoundError):
                path.unlink()

    def _updateTaskFileSize(self, extractedSize: int) -> None:
        task = getattr(self.stage, "_task", None)
        if task is None:
            return

        archiveSize = int(getattr(task, "archiveSize", 0) or 0)
        totalBytes = max(archiveSize + extractedSize, extractedSize, archiveSize)
        if isinstance(task, ExtractTask):
            task.totalBytes = totalBytes
        if hasattr(task, "fileSize"):
            setattr(task, "fileSize", totalBytes)

    def _resolveExtractedRoot(self, tempDir: Path) -> Path:
        children = list(tempDir.iterdir())
        if len(children) == 1 and children[0].is_dir():
            return children[0]
        return tempDir

    def _findExecutable(self, root: Path, name: str) -> Path | None:
        for candidate in (root / "bin" / name, root / name):
            if candidate.is_file():
                return candidate

        for candidate in root.rglob(name):
            if candidate.is_file():
                return candidate

        return None

    async def _writeExtractedFile(
        self,
        source: Any,
        targetPath: Path,
        extractedBytes: int,
        speedBytes: int,
        speedTime: float,
        totalSize: int,
    ) -> tuple[int, int, float]:
        with open(targetPath, "wb") as target:
            while True:
                chunk = source.read(self.chunkSize)
                if not chunk:
                    return extractedBytes, speedBytes, speedTime

                target.write(chunk)
                extractedBytes += len(chunk)
                progress = 0.0
                if totalSize > 0:
                    progress = min(99.5, max(0.0, extractedBytes / totalSize * 100))
                now = perf_counter()
                speed = self.stage.speed
                if now - speedTime >= 0.5:
                    speed = int((extractedBytes - speedBytes) / (now - speedTime))
                    speedBytes = extractedBytes
                    speedTime = now
                    await asyncio.sleep(0)
                self.stage.updateTransfer(
                    doneBytes=extractedBytes,
                    speed=speed,
                    progress=progress,
                )

    async def _extractZip(self, archivePath: Path, tempDir: Path, totalSize: int) -> None:
        extractedBytes = 0
        speedBytes = 0
        speedTime = perf_counter()

        with zipfile.ZipFile(archivePath) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            for info in infos:
                targetPath = _safeJoin(tempDir, info.filename)
                targetPath.parent.mkdir(parents=True, exist_ok=True)

                with archive.open(info, "r") as source:
                    extractedBytes, speedBytes, speedTime = await self._writeExtractedFile(
                        source,
                        targetPath,
                        extractedBytes,
                        speedBytes,
                        speedTime,
                        totalSize,
                    )

    async def _extractTar(self, archivePath: Path, tempDir: Path, totalSize: int) -> None:
        extractedBytes = 0
        speedBytes = 0
        speedTime = perf_counter()

        with tarfile.open(archivePath, "r:*") as archive:
            members = [member for member in archive.getmembers() if member.isfile()]
            for member in members:
                targetPath = _safeJoin(tempDir, member.name)
                targetPath.parent.mkdir(parents=True, exist_ok=True)

                source = archive.extractfile(member)
                if source is None:
                    continue

                with source:
                    extractedBytes, speedBytes, speedTime = await self._writeExtractedFile(
                        source,
                        targetPath,
                        extractedBytes,
                        speedBytes,
                        speedTime,
                        totalSize,
                    )

    async def _extractArchive(self, archivePath: Path, tempDir: Path, totalSize: int) -> None:
        suffix = _archiveSuffix(archivePath.name)
        if suffix == ".zip":
            await self._extractZip(archivePath, tempDir, totalSize)
            return

        if suffix == ".tar.gz":
            await self._extractTar(archivePath, tempDir, totalSize)
            return

        raise RuntimeError(f"不支持的压缩包格式: {archivePath.name}")

    def _archiveExtractSize(self, archivePath: Path) -> int:
        suffix = _archiveSuffix(archivePath.name)
        if suffix == ".zip":
            with zipfile.ZipFile(archivePath) as archive:
                return sum(info.file_size for info in archive.infolist() if not info.is_dir())

        if suffix == ".tar.gz":
            with tarfile.open(archivePath, "r:*") as archive:
                return sum(member.size for member in archive.getmembers() if member.isfile())

        raise RuntimeError(f"不支持的压缩包格式: {archivePath.name}")

    def _installExtractedFiles(
        self,
        extractedRoot: Path,
        installDir: Path,
        archiveName: str,
        tempDirName: str,
    ) -> dict[str, str]:
        for child in installDir.iterdir():
            if child.name in {archiveName, tempDirName}:
                continue
            self._removePath(child)

        for child in list(extractedRoot.iterdir()):
            target = installDir / child.name
            if target.exists():
                self._removePath(target)
            shutil.move(str(child), str(target))

        executables: dict[str, str] = {}
        for name in self.stage.executableNames:
            executablePath = self._findExecutable(installDir, name)
            if executablePath is None:
                raise RuntimeError(f"安装包解压完成，但未找到可执行文件: {name}")

            if sys.platform != "win32":
                executablePath.chmod(executablePath.stat().st_mode | 0o755)

            executables[name] = _normalizePath(executablePath)

        return executables

    async def run(self) -> None:
        archivePath = Path(self.stage.archivePath)
        if not archivePath.is_file():
            self.stage.setStatus("failed")
            raise FileNotFoundError(f"未找到安装包: {archivePath}")

        installDir = Path(self.stage.installFolder)
        tempDir = installDir / ".extracting"

        try:
            self.stage.updateTransfer(doneBytes=0, speed=0, progress=0.0)
            self.stage.setStatus("running")

            installDir.mkdir(parents=True, exist_ok=True)
            if tempDir.exists():
                shutil.rmtree(tempDir, ignore_errors=True)
            tempDir.mkdir(parents=True, exist_ok=True)

            extractSize = self._archiveExtractSize(archivePath)
            self._updateTaskFileSize(extractSize)
            await self._extractArchive(archivePath, tempDir, extractSize)

            extractedRoot = self._resolveExtractedRoot(tempDir)
            self.stage.extractedExecutables = self._installExtractedFiles(
                extractedRoot,
                installDir,
                archivePath.name,
                tempDir.name,
            )

            if self.stage.cleanupArchive and archivePath.exists():
                archivePath.unlink()

            self.stage.setStatus("completed")
        except asyncio.CancelledError:
            self.stage.setStatus("paused")
            raise
        except Exception as error:
            self.stage.setError(error)
            raise
        finally:
            if tempDir.exists():
                shutil.rmtree(tempDir, ignore_errors=True)
            _notifyAttachedTask(getattr(self.stage, "_task", None))


class ExtractPack(FeaturePack):
    def accepts(self, source: str) -> bool:
        return _supportsArchiveSource(source)

    async def createTask(self, data: TaskInput) -> Task | None:
        archivePath = str(data.config.source).strip()
        if not archivePath or not self.accepts(archivePath):
            return None

        stage = ExtractStage(
            stageIndex=1,
            archivePath=archivePath,
            installFolder=str(data.config.folder),
            executableNames=_taskInputExecutableNames(data.hints),
            cleanupArchive=_taskInputCleanupArchive(data.hints),
        )
        task = ExtractTask(config=data.config, stage=stage)
        if isinstance(data.size, int) and data.size > 0:
            task.archiveSize = data.size
            task.totalBytes = data.size
        return task

    def owns(self, task: Task) -> bool:
        return isinstance(task, ExtractTask) and task.packId == self.manifest.id


__all__ = [
    "ExtractPack",
    "ExtractStage",
    "ExtractTask",
    "ExtractWorker",
]
