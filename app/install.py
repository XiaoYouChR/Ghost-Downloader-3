from __future__ import annotations

import asyncio
import glob
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from app.models.task import TaskError
from app.platform.filesystem import deletePath


def deleteInstalled(path: Path) -> None:
    if path.exists() or path.is_symlink():
        path.rename(path.with_name(f"{path.name}.{uuid4().hex[:8]}.old"))
    for old in path.parent.glob(f"{glob.escape(path.name)}.*.old"):
        deletePath(old)


def installFile(source: Path, target: Path) -> None:
    deleteInstalled(target)
    source.replace(target)


async def installArchive(archive: Path, folder: Path, root: str = "", subtree: str = "") -> None:
    safeRoot = folder.resolve()

    def toMemberPath(name: str) -> Path | None:
        relativeName = name
        if root:
            if not relativeName.startswith(root):
                return None
            relativeName = relativeName[len(root):]
        if subtree and not relativeName.startswith(subtree):
            return None
        path = (folder / relativeName).resolve()
        if safeRoot not in path.parents:
            raise TaskError("压缩包包含不安全路径：{path}", path=name)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def installStream(source: BinaryIO, target: Path, mode: int | None = None) -> None:
        downloadPath = target.with_name(f"{target.name}.download")
        try:
            with open(downloadPath, "wb") as file:
                shutil.copyfileobj(source, file)
            if mode is not None:
                downloadPath.chmod(mode)
            installFile(downloadPath, target)
        finally:
            downloadPath.unlink(missing_ok=True)

    def install() -> None:
        lowered = archive.name.lower()
        if lowered.endswith((".zip", ".whl")):
            with zipfile.ZipFile(archive) as zf:
                for info in zf.infolist():
                    if info.is_dir() or (path := toMemberPath(info.filename)) is None:
                        continue
                    with zf.open(info) as source:
                        installStream(source, path)
        elif lowered.endswith(".tar.gz"):
            with tarfile.open(archive, "r:gz") as tf:
                for member in tf.getmembers():
                    if not member.isfile() or (path := toMemberPath(member.name)) is None:
                        continue
                    with tf.extractfile(member) as source:
                        installStream(source, path, member.mode & 0o777)
        else:
            raise TaskError("不支持的压缩格式：{name}", name=archive.name)

    try:
        folder.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(install)
    finally:
        deletePath(archive)
