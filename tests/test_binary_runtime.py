from __future__ import annotations

import io
import os
import tarfile
import zipfile
from pathlib import Path

import pytest

from app.install import deleteInstalled, installArchive, installFile
from app.models.task import TaskError
from tests.conftest import FakeRuntime
from tests.helpers import EXE_SUFFIX, waitUntil


def createTar(path: Path, members: dict[str, bytes], mode: int = 0o755) -> Path:
    with tarfile.open(path, "w:gz") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = mode
            tf.addfile(info, io.BytesIO(data))
    return path


def createZip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


async def test_install_tar_replaces_old_version_and_keeps_user_files(tmp_path):
    folder = tmp_path / "FFmpeg"
    folder.mkdir()
    (folder / "ffmpeg").write_bytes(b"old")
    (folder / "notes.txt").write_bytes(b"user")
    archive = createTar(folder / "ffmpeg.tar.gz", {"ffmpeg": b"new", "VERSION": b"8.1"})

    await installArchive(archive, folder)

    assert (folder / "ffmpeg").read_bytes() == b"new"
    assert os.access(folder / "ffmpeg", os.X_OK)
    assert (folder / "VERSION").read_bytes() == b"8.1"
    assert (folder / "notes.txt").read_bytes() == b"user"
    assert not archive.exists()


async def test_install_tar_only_wanted_folder(tmp_path):
    archive = createTar(tmp_path / "yt_dlp.tar.gz", {
        "yt-dlp/yt_dlp/__init__.py": b"init",
        "yt-dlp/README.md": b"readme",
        "other/yt_dlp/x.py": b"x",
    }, mode=0o644)

    await installArchive(archive, tmp_path / "out", root="yt-dlp/", subtree="yt_dlp/")

    assert sorted(p.relative_to(tmp_path / "out").as_posix()
                  for p in (tmp_path / "out").rglob("*") if p.is_file()) == ["yt_dlp/__init__.py"]


async def test_install_zip_replaces_old_version_and_deletes_archive(tmp_path):
    (tmp_path / "ffmpeg.exe").write_bytes(b"old")
    archive = createZip(tmp_path / "ffmpeg.zip", {"ffmpeg.exe": b"new"})

    await installArchive(archive, tmp_path)

    assert (tmp_path / "ffmpeg.exe").read_bytes() == b"new"
    assert not archive.exists()


async def test_install_rejects_and_deletes_unsafe_archive(tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()
    archive = createTar(folder / "evil.tar.gz", {"../escaped": b"x"})

    with pytest.raises(TaskError):
        await installArchive(archive, folder)

    assert not (tmp_path / "escaped").exists()
    assert not archive.exists()


def test_install_replaces_a_running_program(tmp_path, startProgram):
    target = tmp_path / f"ffmpeg{EXE_SUFFIX}"
    program = startProgram(target)
    (tmp_path / "ffmpeg.download").write_bytes(b"new")

    installFile(tmp_path / "ffmpeg.download", target)

    assert target.read_bytes() == b"new"

    program.kill()
    program.wait()
    (tmp_path / "ffmpeg.download").write_bytes(b"newer")
    installFile(tmp_path / "ffmpeg.download", target)

    assert [p.name for p in tmp_path.iterdir()] == [target.name]
    assert target.read_bytes() == b"newer"


def test_delete_keeps_neighbouring_files(tmp_path):
    (tmp_path / "yt_dlp").mkdir()
    (tmp_path / "yt_dlp" / "__init__.py").write_bytes(b"init")
    (tmp_path / "notes.txt").write_bytes(b"user")

    deleteInstalled(tmp_path / "yt_dlp")

    assert [p.name for p in tmp_path.iterdir()] == ["notes.txt"]


def test_delete_folder_with_running_program(tmp_path, startProgram):
    (tmp_path / "deno").mkdir()
    program = startProgram(tmp_path / "deno" / f"deno{EXE_SUFFIX}")

    deleteInstalled(tmp_path / "deno")

    assert not (tmp_path / "deno").exists()

    program.kill()
    program.wait()
    deleteInstalled(tmp_path / "deno")

    assert list(tmp_path.iterdir()) == []


async def test_install_tar_replaces_running_program_with_executable(tmp_path, startProgram):
    startProgram(tmp_path / f"ffmpeg{EXE_SUFFIX}")
    archive = createTar(tmp_path / "ffmpeg.tar.gz", {f"ffmpeg{EXE_SUFFIX}": b"new"})

    await installArchive(archive, tmp_path)

    assert (tmp_path / f"ffmpeg{EXE_SUFFIX}").read_bytes() == b"new"
    assert os.access(tmp_path / f"ffmpeg{EXE_SUFFIX}", os.X_OK)
    assert sorted(p.name for p in tmp_path.iterdir() if not p.name.endswith(".old")) == [f"ffmpeg{EXE_SUFFIX}"]


def test_delete_removes_only_installed_paths(tmp_path):
    (tmp_path / "fake").write_bytes(b"bin")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "a.so").write_bytes(b"so")
    (tmp_path / "notes.txt").write_bytes(b"user")

    FakeRuntime(tmp_path).delete()

    assert [p.name for p in tmp_path.iterdir()] == ["notes.txt"]


async def runInstall(engine, runtime: FakeRuntime) -> list:
    statuses = []
    engine.runtimeStatusService.statusChanged.connect(statuses.append)
    engine.runtimeStatusService.install(runtime)
    await waitUntil(lambda: statuses and not statuses[-1].isInstalling)
    return statuses


async def test_install_reports_each_whole_percent_once(engine, tmp_path):
    statuses = await runInstall(engine, FakeRuntime(tmp_path, [0.2, 0.9, 1.1, 1.8, 45.5, 100.0]))

    assert [s.progress for s in statuses if s.isInstalling] == [0, 1, 45, 100]


async def test_install_failure_reports_error(engine, tmp_path):
    statuses = await runInstall(engine, FakeRuntime(tmp_path, [50.0], TaskError("安装包校验失败，可能已损坏，请重试")))

    assert not statuses[-1].isInstalling
    assert statuses[-1].error.message == "安装包校验失败，可能已损坏，请重试"


async def test_install_without_the_executable_fails(engine, tmp_path):
    statuses = await runInstall(engine, FakeRuntime(tmp_path, [100.0], isMissingAfterInstall=True))

    assert not statuses[-1].isInstalling
    assert statuses[-1].error.message == "安装后未找到 {name}"


async def test_install_reports_installed_path(engine, tmp_path):
    statuses = await runInstall(engine, FakeRuntime(tmp_path, [100.0]))

    assert statuses[-1].error is None
    assert statuses[-1].path == str(tmp_path / "fake")


async def test_install_wheel_only_the_package(tmp_path):
    archive = createZip(tmp_path / "yt_dlp.whl", {
        "yt_dlp/__init__.py": b"init",
        "yt_dlp-2026.9.27.232945.dev0.dist-info/METADATA": b"meta",
    })

    await installArchive(archive, tmp_path / "out", subtree="yt_dlp/")

    assert [p.relative_to(tmp_path / "out").as_posix()
            for p in (tmp_path / "out").rglob("*") if p.is_file()] == ["yt_dlp/__init__.py"]
    assert not archive.exists()
