from __future__ import annotations

import asyncio
import hashlib
import shutil
import tarfile
import zipfile
from pathlib import Path

from app.models.task import TaskError
from app.platform.filesystem import deletePath


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

    def install() -> None:
        lowered = archive.name.lower()
        if lowered.endswith((".zip", ".whl")):
            with zipfile.ZipFile(archive) as zf:
                for info in zf.infolist():
                    if info.is_dir() or (path := toMemberPath(info.filename)) is None:
                        continue
                    with zf.open(info) as source, open(path, "wb") as target:
                        shutil.copyfileobj(source, target)
        elif lowered.endswith(".tar.gz"):
            with tarfile.open(archive, "r:gz") as tf:
                for member in tf.getmembers():
                    if not member.isfile() or (path := toMemberPath(member.name)) is None:
                        continue
                    with tf.extractfile(member) as source, open(path, "wb") as target:
                        shutil.copyfileobj(source, target)
                    path.chmod(member.mode & 0o777)
        else:
            raise TaskError("不支持的压缩格式：{name}", name=archive.name)

    try:
        folder.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(install)
    finally:
        deletePath(archive)


async def matchSha256(file: Path, sha256File: Path) -> bool:
    text = sha256File.read_text(encoding="utf-8", errors="ignore").strip()
    expected = text.split()[0].lower() if text else ""
    with file.open("rb") as source:
        actual = (await asyncio.to_thread(hashlib.file_digest, source, "sha256")).hexdigest()
    return expected == actual
