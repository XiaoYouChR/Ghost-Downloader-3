from __future__ import annotations

import asyncio
import hashlib
import shutil
import sys
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from time import perf_counter
from urllib.parse import urlparse

from app.models.task import Task, TaskError, TaskStep, TaskStatus
from app.platform.filesystem import deletePath, toPosixPath

CHUNK_SIZE = 1 << 20
ARCHIVE_SUFFIXES = (".zip", ".tar.gz")


def isArchive(name: str) -> bool:
    lower = name.lower()
    return any(lower.endswith(suffix) for suffix in ARCHIVE_SUFFIXES)


@dataclass(kw_only=True, eq=False)
class InstallTask(Task):
    hasOutputFile = False
    installFolder: str = ""

    @property
    def canPause(self) -> bool:
        return False

    def deleteFiles(self):
        if self.installFolder:
            deletePath(Path(self.installFolder))
            return
        super().deleteFiles()


@dataclass(kw_only=True)
class ExtractStep(TaskStep):
    canPause = False

    archivePath: str
    outputFolder: str
    archiveSize: int = 0
    root: str = ""
    subtree: str = ""

    async def _extractZip(self, archive: Path, outputFolder: Path):
        with zipfile.ZipFile(archive) as zf:
            members = []
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = info.filename
                if self.root:
                    if not name.startswith(self.root):
                        continue
                    name = name[len(self.root):]
                if self.subtree and not name.startswith(self.subtree):
                    continue
                members.append((info, name))

            totalSize = sum(info.file_size for info, _ in members)
            self.task.fileSize = max(self.archiveSize + totalSize, self.archiveSize)

            safeRoot = outputFolder.resolve()
            extractedBytes = speedBytes = 0
            speedTime = perf_counter()
            for info, name in members:
                memberPath = (outputFolder / name).resolve()
                if safeRoot not in {memberPath, *memberPath.parents}:
                    raise TaskError("压缩包包含不安全路径：{path}", path=info.filename)
                memberPath.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as source, open(memberPath, "wb") as target:
                    while chunk := source.read(CHUNK_SIZE):
                        target.write(chunk)
                        extractedBytes += len(chunk)
                        self.receivedBytes = extractedBytes
                        if totalSize > 0:
                            self.progress = min(99.5, extractedBytes / totalSize * 100)
                        now = perf_counter()
                        if now - speedTime >= 0.5:
                            self.speed = int((extractedBytes - speedBytes) / (now - speedTime))
                            speedBytes, speedTime = extractedBytes, now
                            await asyncio.sleep(0)

    async def _extractTar(self, archive: Path, outputFolder: Path):
        with tarfile.open(archive, "r:*") as tf:
            members = []
            for m in tf.getmembers():
                if not m.isfile():
                    continue
                name = m.name
                if self.root:
                    if not name.startswith(self.root):
                        continue
                    name = name[len(self.root):]
                if self.subtree and not name.startswith(self.subtree):
                    continue
                members.append((m, name))

            totalSize = sum(m.size for m, _ in members)
            self.task.fileSize = max(self.archiveSize + totalSize, self.archiveSize)

            safeRoot = outputFolder.resolve()
            extractedBytes = speedBytes = 0
            speedTime = perf_counter()
            for member, name in members:
                memberPath = (outputFolder / name).resolve()
                if safeRoot not in {memberPath, *memberPath.parents}:
                    raise TaskError("压缩包包含不安全路径：{path}", path=member.name)
                memberPath.parent.mkdir(parents=True, exist_ok=True)
                source = tf.extractfile(member)
                if source is None:
                    continue
                with source, open(memberPath, "wb") as target:
                    while chunk := source.read(CHUNK_SIZE):
                        target.write(chunk)
                        extractedBytes += len(chunk)
                        self.receivedBytes = extractedBytes
                        if totalSize > 0:
                            self.progress = min(99.5, extractedBytes / totalSize * 100)
                        now = perf_counter()
                        if now - speedTime >= 0.5:
                            self.speed = int((extractedBytes - speedBytes) / (now - speedTime))
                            speedBytes, speedTime = extractedBytes, now
                            await asyncio.sleep(0)

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        archive = Path(self.archivePath)
        if not archive.is_file():
            raise TaskError("压缩包未找到：{path}", path=str(archive))

        outputFolder = Path(self.outputFolder)
        self.progress = 0
        self.speed = 0
        self.receivedBytes = 0
        outputFolder.mkdir(parents=True, exist_ok=True)

        lowered = archive.name.lower()
        if lowered.endswith(".tar.gz"):
            await self._extractTar(archive, outputFolder)
        elif lowered.endswith(".zip"):
            await self._extractZip(archive, outputFolder)
        else:
            raise TaskError("不支持的压缩格式：{name}", name=archive.name)

        self.setStatus(TaskStatus.COMPLETED)


@dataclass(kw_only=True)
class InstallStep(TaskStep):
    canPause = False

    sourceFolder: str
    installFolder: str
    archivePath: str = ""
    shouldDeleteSource: bool = True
    executableNames: list[str] = field(default_factory=list)

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        sourceFolder = Path(self.sourceFolder)
        installFolder = Path(self.installFolder)
        archive = Path(self.archivePath) if self.archivePath else None

        try:
            preserve = {sourceFolder.name}
            if archive is not None and archive.parent == installFolder:
                preserve.add(archive.name)
            for child in installFolder.iterdir():
                if child.name in preserve:
                    continue
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)

            children = list(sourceFolder.iterdir())
            contentRoot = children[0] if len(children) == 1 and children[0].is_dir() else sourceFolder

            for child in list(contentRoot.iterdir()):
                shutil.move(str(child), str(installFolder / child.name))

            for name in self.executableNames:
                executable = None
                for candidate in (installFolder / "bin" / name, installFolder / name):
                    if candidate.is_file():
                        executable = candidate
                        break
                if executable is None:
                    executable = next((c for c in installFolder.rglob(name) if c.is_file()), None)
                if executable is None:
                    raise TaskError("解压后未找到可执行文件：{name}", name=name)
                if sys.platform != "win32":
                    executable.chmod(executable.stat().st_mode | 0o755)

            if self.shouldDeleteSource and archive is not None and archive.exists():
                archive.unlink()

            self.setStatus(TaskStatus.COMPLETED)
        finally:
            if self.shouldDeleteSource and sourceFolder.exists():
                shutil.rmtree(sourceFolder, ignore_errors=True)


@dataclass(kw_only=True)
class ChecksumStep(TaskStep):
    canPause = False

    targetFile: str
    sha256File: str

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        text = Path(self.sha256File).read_text(encoding="utf-8", errors="ignore").strip()
        expected = text.split()[0].lower() if text else ""
        if not expected:
            raise TaskError("无法读取校验文件：{path}", path=self.sha256File)
        actual = await asyncio.to_thread(self._sha256, Path(self.targetFile))
        if expected != actual:
            raise TaskError("SHA256 校验失败：期望 {expected}，实际 {actual}", expected=expected, actual=actual)
        deletePath(Path(self.sha256File))
        self.setStatus(TaskStatus.COMPLETED)

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(CHUNK_SIZE), b""):
                digest.update(chunk)
        return digest.hexdigest().lower()


@dataclass(kw_only=True)
class BinaryInstallStep(TaskStep):
    canPause = False

    binaryPath: str

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        path = Path(self.binaryPath)
        if not path.is_file():
            raise TaskError("下载的文件未找到：{path}", path=str(path))
        if sys.platform != "win32":
            path.chmod(path.stat().st_mode | 0o755)
        self.setStatus(TaskStatus.COMPLETED)


@dataclass(kw_only=True)
class FetchStep(TaskStep):
    canPause = False
    url: str
    outputFile: str = ""

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        from app.client import fetchFile

        def onProgress(p):
            self.progress = p
            reportSpeed()

        await fetchFile(self.url, Path(self.outputFile), onProgress=onProgress)
        self.setStatus(TaskStatus.COMPLETED)


def createInstallTask(
    url: str,
    outputFolder: Path,
    name: str = "",
    executableNames: tuple[str, ...] = (),
    sha256Url: str = "",
) -> InstallTask:
    assetName = PurePosixPath(urlparse(url).path).name

    archive = isArchive(assetName)
    if archive:
        targetPath = toPosixPath(outputFolder / assetName)
    else:
        binaryName = executableNames[0] if executableNames else assetName
        targetPath = toPosixPath(outputFolder / binaryName)

    task = InstallTask(
        name=name or assetName,
        url=url,
        packId="install",
        fileSize=0,
        outputFolder=outputFolder,
        installFolder=str(outputFolder),
    )
    stepIndex = 1
    task.addStep(FetchStep(stepIndex=stepIndex, url=url, outputFile=targetPath))
    stepIndex += 1

    if sha256Url:
        sha256Path = toPosixPath(outputFolder / PurePosixPath(urlparse(sha256Url).path).name)
        task.addStep(FetchStep(stepIndex=stepIndex, url=sha256Url, outputFile=sha256Path))
        stepIndex += 1
        task.addStep(ChecksumStep(
            stepIndex=stepIndex, targetFile=targetPath, sha256File=sha256Path,
        ))
        stepIndex += 1

    if archive:
        extractFolder = toPosixPath(outputFolder / ".extracting")
        task.addStep(ExtractStep(
            stepIndex=stepIndex,
            archivePath=targetPath,
            outputFolder=extractFolder,
        ))
        stepIndex += 1
        task.addStep(InstallStep(
            stepIndex=stepIndex,
            sourceFolder=extractFolder,
            installFolder=toPosixPath(outputFolder),
            archivePath=targetPath,
            executableNames=list(executableNames),
        ))
    else:
        task.addStep(BinaryInstallStep(stepIndex=stepIndex, binaryPath=targetPath))

    return task
