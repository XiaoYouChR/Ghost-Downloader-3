from __future__ import annotations

import asyncio
import hashlib
import io
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from app.install import installArchive, matchSha256
from app.models.pack import BinaryRuntime, VersionInfo
from app.models.task import TaskError
from app.services.coroutine_runner import CoroutineRunner
from app.services.runtime_status import RuntimeStatusService


def writeTar(path: Path, members: dict[str, bytes], mode: int = 0o755) -> Path:
    with tarfile.open(path, "w:gz") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = mode
            tf.addfile(info, io.BytesIO(data))
    return path


def writeZip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


async def test_tar_overwrites_old_version_and_keeps_user_files(tmp_path):
    folder = tmp_path / "FFmpeg"
    folder.mkdir()
    (folder / "ffmpeg").write_bytes(b"old")
    (folder / "notes.txt").write_bytes(b"user")
    archive = writeTar(folder / "ffmpeg.tar.gz", {"ffmpeg": b"new", "VERSION": b"8.1"})

    await installArchive(archive, folder)

    assert (folder / "ffmpeg").read_bytes() == b"new"
    assert (folder / "ffmpeg").stat().st_mode & 0o777 == 0o755
    assert (folder / "VERSION").read_bytes() == b"8.1"
    assert (folder / "notes.txt").read_bytes() == b"user"
    assert not archive.exists()


async def test_tar_keeps_only_subtree_under_root(tmp_path):
    archive = writeTar(tmp_path / "yt_dlp.tar.gz", {
        "yt-dlp/yt_dlp/__init__.py": b"init",
        "yt-dlp/README.md": b"readme",
        "other/yt_dlp/x.py": b"x",
    }, mode=0o644)

    await installArchive(archive, tmp_path / "out", root="yt-dlp/", subtree="yt_dlp/")

    assert sorted(p.relative_to(tmp_path / "out").as_posix()
                  for p in (tmp_path / "out").rglob("*") if p.is_file()) == ["yt_dlp/__init__.py"]


async def test_zip_overwrites_and_deletes_archive(tmp_path):
    (tmp_path / "ffmpeg.exe").write_bytes(b"old")
    archive = writeZip(tmp_path / "ffmpeg.zip", {"ffmpeg.exe": b"new"})

    await installArchive(archive, tmp_path)

    assert (tmp_path / "ffmpeg.exe").read_bytes() == b"new"
    assert not archive.exists()


async def test_unsafe_member_is_rejected_and_archive_deleted(tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()
    archive = writeTar(folder / "evil.tar.gz", {"../escaped": b"x"})

    with pytest.raises(TaskError):
        await installArchive(archive, folder)

    assert not (tmp_path / "escaped").exists()
    assert not archive.exists()


@pytest.mark.parametrize("digestOf, expected", [(b"payload", True), (b"other", False)])
async def test_match_sha256(tmp_path, digestOf, expected):
    file = tmp_path / "ffmpeg.tar.gz"
    file.write_bytes(b"payload")
    sha256File = tmp_path / "ffmpeg.tar.gz.sha256"
    sha256File.write_text(f"{hashlib.sha256(digestOf).hexdigest().upper()}  ffmpeg.tar.gz\n")

    assert await matchSha256(file, sha256File) is expected


class FakeRuntime(BinaryRuntime):
    name = "fake"

    def __init__(self, folder: Path, progresses: list[float] = (), error: Exception | None = None,
                 isMissingAfterInstall: bool = False):
        self.folder = folder
        self.progresses = progresses
        self.error = error
        self.isMissingAfterInstall = isMissingAfterInstall

    def installFolder(self) -> Path:
        return self.folder

    def path(self) -> str:
        binary = self.folder / "fake"
        return str(binary) if binary.is_file() else ""

    async def probeVersion(self) -> VersionInfo:
        return VersionInfo("")

    def installedPaths(self) -> list[Path]:
        return [self.folder / "fake", self.folder / "lib"]

    async def install(self, version: str, onProgress) -> None:
        for progress in self.progresses:
            onProgress(progress)
            await asyncio.sleep(0)
        if self.error:
            raise self.error
        if not self.isMissingAfterInstall:
            (self.folder / "fake").write_bytes(b"bin")


def test_delete_removes_only_installed_paths(tmp_path):
    (tmp_path / "fake").write_bytes(b"bin")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "a.so").write_bytes(b"so")
    (tmp_path / "notes.txt").write_bytes(b"user")

    FakeRuntime(tmp_path).delete()

    assert [p.name for p in tmp_path.iterdir()] == ["notes.txt"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX 目录权限")
def test_delete_raises_when_a_path_cannot_be_deleted(tmp_path):
    (tmp_path / "fake").write_bytes(b"bin")
    tmp_path.chmod(0o555)
    try:
        with pytest.raises(PermissionError):
            FakeRuntime(tmp_path).delete()
    finally:
        tmp_path.chmod(0o755)


async def runInstall(runtime: FakeRuntime) -> list:
    loop = asyncio.get_running_loop()
    service = RuntimeStatusService(CoroutineRunner(loop.call_soon, loop=loop))
    statuses = []
    service.statusChanged.connect(statuses.append)
    service.install(runtime)
    await asyncio.sleep(0.05)
    return statuses


async def test_install_reports_each_whole_percent_once(tmp_path):
    statuses = await runInstall(FakeRuntime(tmp_path, [0.2, 0.9, 1.1, 1.8, 45.5, 100.0]))

    assert [s.progress for s in statuses if s.isInstalling] == [0, 1, 45, 100]


async def test_install_failure_ends_installing_with_error(tmp_path):
    statuses = await runInstall(FakeRuntime(tmp_path, [50.0], TaskError("安装包校验失败，可能已损坏，请重试")))

    assert not statuses[-1].isInstalling
    assert statuses[-1].error.message == "安装包校验失败，可能已损坏，请重试"


async def test_install_without_the_executable_fails(tmp_path):
    statuses = await runInstall(FakeRuntime(tmp_path, [100.0], isMissingAfterInstall=True))

    assert not statuses[-1].isInstalling
    assert statuses[-1].error.message == "安装后未找到 {name}"


async def test_install_success_reports_installed_path(tmp_path):
    statuses = await runInstall(FakeRuntime(tmp_path, [100.0]))

    assert statuses[-1].error is None
    assert statuses[-1].path == str(tmp_path / "fake")


async def test_wheel_installs_package_only(tmp_path):
    archive = writeZip(tmp_path / "yt_dlp.whl", {
        "yt_dlp/__init__.py": b"init",
        "yt_dlp-2026.9.27.232945.dev0.dist-info/METADATA": b"meta",
    })

    await installArchive(archive, tmp_path / "out", subtree="yt_dlp/")

    assert [p.relative_to(tmp_path / "out").as_posix()
            for p in (tmp_path / "out").rglob("*") if p.is_file()] == ["yt_dlp/__init__.py"]
    assert not archive.exists()


async def test_nightly_wheel_is_latest_dev_in_tag_format(monkeypatch):
    import features.yt_dlp_pack.config as ytDlpConfig

    def wheel(version, yanked=False):
        return {"filename": f"yt_dlp-{version}-py3-none-any.whl", "url": version, "yanked": yanked}

    async def fetchPypiReleases(package):
        return {
            "2026.8.27.3630.dev0": [wheel("2026.8.27.3630.dev0")],
            "2026.8.20.234504.dev0": [wheel("2026.8.20.234504.dev0")],
            "2026.8.28.100.dev0": [wheel("2026.8.28.100.dev0", yanked=True)],
            "2026.8.29.1.dev0": [{"filename": "yt_dlp-2026.8.29.1.dev0.tar.gz", "url": "", "yanked": False}],
            "2026.9.1": [wheel("2026.9.1")],
        }

    monkeypatch.setattr(ytDlpConfig, "fetchPypiReleases", fetchPypiReleases)

    assert await ytDlpConfig.fetchNightlyWheel() == ("2026.08.27.003630", "2026.8.27.3630.dev0")
