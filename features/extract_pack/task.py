import asyncio
import shutil
import sys
import tarfile
import zipfile
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter

from app.bases.interfaces import Worker
from app.bases.models import TaskStage, TaskStatus


def _normalizePath(path: Path | str) -> str:
    return str(Path(path)).replace("\\", "/")


def _archiveSuffix(name: str) -> str:
    loweredName = name.lower()
    if loweredName.endswith(".tar.gz"):
        return ".tar.gz"
    return Path(name).suffix.lower()


def _safeJoin(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if root.resolve() not in {target, *target.parents}:
        raise RuntimeError(f"压缩包包含非法路径: {relative}")
    return target


@dataclass
class ExtractStage(TaskStage):
    archivePath: str
    installFolder: str
    executableNames: list[str]
    extractedExecutables: dict[str, str] = field(default_factory=dict)
    cleanupArchive: bool = field(default=True)


class ExtractWorker(Worker):
    chunkSize = 1048576

    def __init__(self, stage: ExtractStage):
        super().__init__(stage)
        self.stage = stage

    def _removePath(self, path: Path):
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        else:
            with suppress(FileNotFoundError):
                path.unlink()

    def _updateTaskFileSize(self, extractedSize: int):
        task = getattr(self.stage, "_task", None)
        if task is None:
            return

        archiveSize = int(getattr(task, "archiveSize", 0) or 0)
        task.fileSize = max(archiveSize + extractedSize, archiveSize)

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
        source,
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
                self.stage.receivedBytes = extractedBytes
                if totalSize > 0:
                    self.stage.progress = min(99.5, max(0.0, extractedBytes / totalSize * 100))

                now = perf_counter()
                if now - speedTime >= 0.5:
                    self.stage.speed = int((extractedBytes - speedBytes) / (now - speedTime))
                    speedBytes = extractedBytes
                    speedTime = now
                    await asyncio.sleep(0)

    async def _extractZip(self, archivePath: Path, tempDir: Path, totalSize: int):
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

    async def _extractTar(self, archivePath: Path, tempDir: Path, totalSize: int):
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

    async def _extractArchive(self, archivePath: Path, tempDir: Path, totalSize: int):
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

    def _installExtractedFiles(self, extractedRoot: Path, installDir: Path, archiveName: str, tempDirName: str) -> dict[str, str]:
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

    async def run(self):
        archivePath = Path(self.stage.archivePath)
        if not archivePath.is_file():
            self.stage.setStatus(TaskStatus.FAILED)
            raise FileNotFoundError(f"未找到安装包: {archivePath}")

        installDir = Path(self.stage.installFolder)
        tempDir = installDir / ".extracting"

        try:
            self.stage.progress = 0
            self.stage.speed = 0
            self.stage.receivedBytes = 0

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

            self.stage.setStatus(TaskStatus.COMPLETED)
        except asyncio.CancelledError:
            self.stage.setStatus(TaskStatus.PAUSED)
            raise
        except Exception as e:
            self.stage.setError(e)
            raise
        finally:
            if tempDir.exists():
                shutil.rmtree(tempDir, ignore_errors=True)
