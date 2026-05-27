import asyncio
import shutil
import sys
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter

from app.bases.interfaces import Worker
from app.bases.models import TaskStage, TaskStatus
from app.supports.utils import toPosixPath


_CHUNK_SIZE = 1 << 20


@dataclass(kw_only=True)
class ExtractStage(TaskStage):
    workerType: type = field(init=False, repr=False)
    canPause: bool = field(init=False, default=False)

    archivePath: str
    outputFolder: str
    archiveSize: int = 0


async def _extractZip(archive: Path, outputFolder: Path, stage: ExtractStage):
    with zipfile.ZipFile(archive) as zf:
        files = [info for info in zf.infolist() if not info.is_dir()]
        totalSize = sum(info.file_size for info in files)
        stage.task.fileSize = max(stage.archiveSize + totalSize, stage.archiveSize)

        safeRoot = outputFolder.resolve()
        extractedBytes = speedBytes = 0
        speedTime = perf_counter()
        for info in files:
            # 防 zip-slip：archive 里若含 "../" 路径会让文件落到 outputFolder 之外
            memberPath = (outputFolder / info.filename).resolve()
            if safeRoot not in {memberPath, *memberPath.parents}:
                raise RuntimeError(f"压缩包包含非法路径: {info.filename}")
            memberPath.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as source, open(memberPath, "wb") as target:
                while chunk := source.read(_CHUNK_SIZE):
                    target.write(chunk)
                    extractedBytes += len(chunk)
                    stage.receivedBytes = extractedBytes
                    if totalSize > 0:
                        stage.progress = min(99.5, extractedBytes / totalSize * 100)
                    now = perf_counter()
                    if now - speedTime >= 0.5:
                        stage.speed = int((extractedBytes - speedBytes) / (now - speedTime))
                        speedBytes, speedTime = extractedBytes, now
                        await asyncio.sleep(0)


async def _extractTar(archive: Path, outputFolder: Path, stage: ExtractStage):
    with tarfile.open(archive, "r:*") as tf:
        files = [m for m in tf.getmembers() if m.isfile()]
        totalSize = sum(m.size for m in files)
        stage.task.fileSize = max(stage.archiveSize + totalSize, stage.archiveSize)

        safeRoot = outputFolder.resolve()
        extractedBytes = speedBytes = 0
        speedTime = perf_counter()
        for member in files:
            # 防 tar-slip：archive 里若含 "../" 路径会让文件落到 outputFolder 之外
            memberPath = (outputFolder / member.name).resolve()
            if safeRoot not in {memberPath, *memberPath.parents}:
                raise RuntimeError(f"压缩包包含非法路径: {member.name}")
            memberPath.parent.mkdir(parents=True, exist_ok=True)
            source = tf.extractfile(member)
            if source is None:
                continue
            with source, open(memberPath, "wb") as target:
                while chunk := source.read(_CHUNK_SIZE):
                    target.write(chunk)
                    extractedBytes += len(chunk)
                    stage.receivedBytes = extractedBytes
                    if totalSize > 0:
                        stage.progress = min(99.5, extractedBytes / totalSize * 100)
                    now = perf_counter()
                    if now - speedTime >= 0.5:
                        stage.speed = int((extractedBytes - speedBytes) / (now - speedTime))
                        speedBytes, speedTime = extractedBytes, now
                        await asyncio.sleep(0)


class ExtractWorker(Worker):
    def __init__(self, stage: ExtractStage):
        super().__init__(stage)
        self.stage = stage

    async def run(self):
        archive = Path(self.stage.archivePath)
        if not archive.is_file():
            raise FileNotFoundError(f"未找到安装包: {archive}")

        outputFolder = Path(self.stage.outputFolder)

        try:
            self.stage.progress = 0
            self.stage.speed = 0
            self.stage.receivedBytes = 0

            outputFolder.mkdir(parents=True, exist_ok=True)

            lowered = archive.name.lower()
            if lowered.endswith(".tar.gz"):
                await _extractTar(archive, outputFolder, self.stage)
            elif lowered.endswith(".zip"):
                await _extractZip(archive, outputFolder, self.stage)
            else:
                raise RuntimeError(f"不支持的压缩包格式: {archive.name}")

            self.stage.setStatus(TaskStatus.COMPLETED)
        except asyncio.CancelledError:
            self.stage.setStatus(TaskStatus.PAUSED)
            raise
        except Exception as e:
            self.stage.setError(e)
            raise


ExtractStage.workerType = ExtractWorker


@dataclass(kw_only=True)
class InstallStage(TaskStage):
    workerType: type = field(init=False, repr=False)
    canPause: bool = field(init=False, default=False)

    sourceDir: str
    installFolder: str
    archivePath: str = ""
    cleanup: bool = True
    executableNames: list[str] = field(default_factory=list)
    extractedExecutables: dict[str, str] = field(default_factory=dict)


def _executablePath(root: Path, name: str) -> Path:
    for candidate in (root / "bin" / name, root / name):
        if candidate.is_file():
            return candidate
    found = next((c for c in root.rglob(name) if c.is_file()), None)
    if found is None:
        raise RuntimeError(f"安装包解压完成，但未找到可执行文件: {name}")
    return found


class InstallWorker(Worker):
    def __init__(self, stage: InstallStage):
        super().__init__(stage)
        self.stage = stage

    async def run(self):
        sourceDir = Path(self.stage.sourceDir)
        installDir = Path(self.stage.installFolder)
        archive = Path(self.stage.archivePath) if self.stage.archivePath else None

        try:
            # archive 和 sourceDir 都可能位于 installDir 内，清空时必须保留
            preserve = {sourceDir.name}
            if archive is not None and archive.parent == installDir:
                preserve.add(archive.name)
            for child in installDir.iterdir():
                if child.name in preserve:
                    continue
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)

            # archive 常把内容包在一个顶层版本目录里（如 ffmpeg-7.0/），跳过它直接移内层
            children = list(sourceDir.iterdir())
            contentRoot = children[0] if len(children) == 1 and children[0].is_dir() else sourceDir

            for child in list(contentRoot.iterdir()):
                shutil.move(str(child), str(installDir / child.name))

            executables: dict[str, Path] = {
                name: _executablePath(installDir, name)
                for name in self.stage.executableNames
            }
            if sys.platform != "win32":
                for path in executables.values():
                    path.chmod(path.stat().st_mode | 0o755)

            self.stage.extractedExecutables = {name: toPosixPath(p) for name, p in executables.items()}
            self.stage.task.metadata["extractedExecutables"] = self.stage.extractedExecutables

            if self.stage.cleanup and archive is not None and archive.exists():
                archive.unlink()

            self.stage.setStatus(TaskStatus.COMPLETED)
        except asyncio.CancelledError:
            self.stage.setStatus(TaskStatus.PAUSED)
            raise
        except Exception as e:
            self.stage.setError(e)
            raise
        finally:
            if self.stage.cleanup and sourceDir.exists():
                shutil.rmtree(sourceDir, ignore_errors=True)


InstallStage.workerType = InstallWorker
