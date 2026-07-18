from __future__ import annotations

import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

from loguru import logger

# Supported archive extensions (lower-cased)
_ARCHIVE_SUFFIXES = {".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar"}


def canAutoExtract(path: str) -> bool:
    """Return True if *path* is a recognised archive that we can auto-extract."""
    p = Path(path)
    suffixes = "".join(p.suffixes).lower()
    return (
        p.suffix.lower() in _ARCHIVE_SUFFIXES
        or suffixes.endswith(".tar.gz")
        or suffixes.endswith(".tar.bz2")
        or suffixes.endswith(".tar.xz")
    )


def autoExtract(archivePath: str, outputFolder: str, deleteAfter: bool = False) -> None:
    """
    Extract *archivePath* into a subfolder inside *outputFolder* named after
    the archive stem (without extension).  If *deleteAfter* is True the
    archive is removed on success.

    Raises exceptions on failure so the caller can surface them.
    """
    src = Path(archivePath)
    if not src.is_file():
        raise FileNotFoundError(f"Archive not found: {archivePath}")

    # Determine a clean stem for the output subfolder
    name = src.name
    for ext in (".tar.gz", ".tar.bz2", ".tar.xz"):
        if name.lower().endswith(ext):
            stem = name[: -len(ext)]
            break
    else:
        stem = src.stem  # strips last suffix only

    destFolder = Path(outputFolder) / stem
    destFolder.mkdir(parents=True, exist_ok=True)

    suffix = "".join(src.suffixes).lower()
    logger.info("Auto-extracting {} → {}", archivePath, destFolder)

    if src.suffix.lower() == ".zip":
        _extractZip(src, destFolder)
    elif (
        src.suffix.lower() in (".tar", ".gz", ".bz2", ".xz")
        or suffix.endswith(".tar.gz")
        or suffix.endswith(".tar.bz2")
        or suffix.endswith(".tar.xz")
    ):
        _extractTar(src, destFolder)
    elif src.suffix.lower() == ".7z":
        _extractSevenZip(src, destFolder)
    elif src.suffix.lower() == ".rar":
        _extractRar(src, destFolder)
    else:
        raise ValueError(f"Unsupported archive type: {src.suffix}")

    if deleteAfter:
        try:
            src.unlink()
            logger.info("Deleted archive after extraction: {}", archivePath)
        except OSError as e:
            logger.warning("Could not delete archive {}: {}", archivePath, e)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _extractZip(src: Path, dest: Path) -> None:
    with zipfile.ZipFile(src, "r") as zf:
        zf.extractall(dest)


def _extractTar(src: Path, dest: Path) -> None:
    with tarfile.open(src, "r:*") as tf:
        tf.extractall(dest)


def _extractSevenZip(src: Path, dest: Path) -> None:
    """Try 7z / 7za / 7zz CLI tools found on PATH."""
    exe = shutil.which("7z") or shutil.which("7za") or shutil.which("7zz")
    if exe:
        result = subprocess.run(
            [exe, "x", str(src), f"-o{dest}", "-y"],
            capture_output=True,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="ignore").strip()
            raise RuntimeError(f"7z extraction failed: {stderr}")
        return

    # Fallback: try py7zr if installed
    try:
        import py7zr  # type: ignore[import]
        with py7zr.SevenZipFile(str(src), mode="r") as zf:
            zf.extractall(path=str(dest))
    except ImportError:
        raise RuntimeError(
            "7z/7za not found on PATH and py7zr is not installed. "
            "Install 7-Zip to auto-extract .7z files."
        )


def _extractRar(src: Path, dest: Path) -> None:
    """Try unrar / rar CLI tools found on PATH."""
    exe = shutil.which("unrar") or shutil.which("rar")
    if exe:
        result = subprocess.run(
            [exe, "x", "-y", str(src), str(dest) + "/"],
            capture_output=True,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="ignore").strip()
            raise RuntimeError(f"unrar extraction failed: {stderr}")
        return

    # Fallback: try rarfile if installed
    try:
        import rarfile  # type: ignore[import]
        with rarfile.RarFile(str(src)) as rf:
            rf.extractall(str(dest))
    except ImportError:
        raise RuntimeError(
            "unrar not found on PATH and rarfile is not installed. "
            "Install WinRAR or unrar to auto-extract .rar files."
        )
