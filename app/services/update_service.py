from __future__ import annotations

import asyncio
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass, replace
from enum import auto, IntEnum
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal
from loguru import logger

from app.config.constants import VERSION
from app.config.paths import APP_DATA_DIR, executableDir
from app.platform.filesystem import matchChecksum
from app.models.pack import PackManifest
from app.sources import fetchJson, fetchRawFile, fetchReleaseAsset
from app.update import APP_REPO, isNewer

if TYPE_CHECKING:
    from app.services.coroutine_runner import CoroutineRunner

STAGING_DIR = Path(APP_DATA_DIR) / "update_staging"

OS_MAP = {"win32": "Windows", "darwin": "macOS", "linux": "Linux"}
MACHINE_MAP = {"AMD64": "x86_64", "x86_64": "x86_64", "aarch64": "arm64", "arm64": "arm64"}


def buildPlatformKey() -> str:
    return f"{OS_MAP[sys.platform]}-{MACHINE_MAP[platform.machine()]}"


def extractZip(archivePath: Path, targetDir: Path) -> None:
    with zipfile.ZipFile(archivePath) as zf:
        zf.extractall(targetDir)


def extractTarXz(archivePath: Path, targetDir: Path) -> None:
    with tarfile.open(archivePath, "r:xz") as tf:
        tf.extractall(targetDir)


async def extractDmg(dmgPath: Path, targetDir: Path) -> None:
    mountPoint = dmgPath.parent / "_dmg_mount"
    mountPoint.mkdir(exist_ok=True)
    try:
        proc = await asyncio.create_subprocess_exec(
            "hdiutil", "attach", str(dmgPath), "-mountpoint", str(mountPoint),
            "-nobrowse", "-quiet",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"hdiutil attach failed ({proc.returncode})")

        apps = [p for p in mountPoint.iterdir() if p.suffix == ".app"]
        if not apps:
            raise RuntimeError("DMG 中未找到 .app")

        await asyncio.to_thread(shutil.copytree, apps[0], targetDir)
    finally:
        await asyncio.create_subprocess_exec(
            "hdiutil", "detach", str(mountPoint), "-quiet",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        if mountPoint.exists():
            mountPoint.rmdir()


def installPendingPacks(featuresDir: Path) -> None:
    if not featuresDir.exists():
        return
    for pending in featuresDir.glob("*_pending"):
        packId = pending.name.removesuffix("_pending")
        target = featuresDir / packId
        if target.exists():
            shutil.rmtree(target)
        pending.rename(target)
        logger.info("已应用 Pack 更新: {}", packId)


class UpdateState(IntEnum):
    IDLE = auto()
    CHECKING = auto()
    AVAILABLE = auto()
    DOWNLOADING = auto()
    READY = auto()
    FAILED = auto()


@dataclass(frozen=True)
class UpdateInfo:
    targetId: str
    label: str
    currentVersion: str
    latestVersion: str
    state: UpdateState = UpdateState.IDLE
    progress: float = 0
    error: str = ""


class UpdateService(QObject):
    changed = Signal(object)

    def __init__(self, coroutineRunner: CoroutineRunner, parent=None):
        super().__init__(parent)
        self._coroutineRunner = coroutineRunner
        self._infos: dict[str, UpdateInfo] = {}
        self._versionsData: dict = {}

    def check(self) -> None:
        self._coroutineRunner.submit(self._check())

    def download(self, targetId: str) -> None:
        self._coroutineRunner.submit(self._download(targetId))

    def apply(self) -> None:
        for info in self._infos.values():
            if info.state == UpdateState.READY and info.targetId != "app":
                self._applyPack(info.targetId)
        appInfo = self._infos.get("app")
        if appInfo is not None and appInfo.state == UpdateState.READY:
            self._startUpdater()

    # ── Private ──

    async def _check(self) -> None:
        self._emit("app", UpdateState.CHECKING, label=f"Ghost Downloader {VERSION}")

        data = await self._fetchVersions()
        if data is None:
            self._emit("app", UpdateState.FAILED, error="无法获取版本信息")
            return
        self._versionsData = data

        appData = data.get("app", {})
        latestVersion = appData.get("version", "")
        if latestVersion and isNewer(VERSION, latestVersion):
            self._emit("app", UpdateState.AVAILABLE,
                        label=f"Ghost Downloader {latestVersion}",
                        latestVersion=latestVersion)
        else:
            self._emit("app", UpdateState.IDLE)

        packsData = data.get("packs", {})
        featuresDir = executableDir / "features"
        for packDir in sorted(featuresDir.iterdir()) if featuresDir.exists() else []:
            if not packDir.is_dir() or packDir.name.startswith("."):
                continue
            manifest = PackManifest.fromDir(packDir)
            if manifest is None or not manifest.version:
                continue
            remoteInfo = packsData.get(manifest.name)
            if remoteInfo is None:
                continue
            remoteVersion = remoteInfo.get("version", "")
            if remoteVersion and isNewer(manifest.version, remoteVersion):
                remoteGdMin = remoteInfo.get("gdMinVersion", "")
                if remoteGdMin and not isNewer(remoteGdMin, VERSION) and remoteGdMin != VERSION:
                    logger.debug("跳过 Pack 更新 {}：需要 GD ≥ {}", manifest.name, remoteGdMin)
                    continue
                self._emit(manifest.name, UpdateState.AVAILABLE,
                            label=f"{manifest.className} {remoteVersion}",
                            currentVersion=manifest.version,
                            latestVersion=remoteVersion)

    async def _fetchVersions(self) -> dict | None:
        try:
            data, _ = await fetchJson(APP_REPO, "main", "versions.json")
            return data
        except RuntimeError:
            return None

    async def _download(self, targetId: str) -> None:
        info = self._infos.get(targetId)
        if info is None or info.state != UpdateState.AVAILABLE:
            return

        self._emit(targetId, UpdateState.DOWNLOADING)
        STAGING_DIR.mkdir(parents=True, exist_ok=True)

        try:
            if targetId == "app":
                await self._downloadApp(info)
            else:
                await self._downloadPack(targetId, info)
        except Exception as e:
            logger.opt(exception=e).error("下载更新失败: {}", targetId)
            self._emit(targetId, UpdateState.FAILED, error=str(e))

    async def _downloadApp(self, info: UpdateInfo) -> None:
        appData = self._versionsData.get("app", {})
        version = appData.get("version", "")
        tag = f"v{version}"
        platformKey = buildPlatformKey()

        patches = appData.get("patches", {})
        patch = patches.get(platformKey)

        if patch and patch.get("from") == VERSION:
            sha = patch.get("sha256", "")
            outputPath = STAGING_DIR / "patch.hdiff"

            await fetchReleaseAsset(APP_REPO, tag, patch["file"], outputPath,
                                    onProgress=lambda p: self._emit("app", UpdateState.DOWNLOADING, progress=p))

            if sha and not matchChecksum(outputPath, sha):
                outputPath.unlink(missing_ok=True)
                self._emit("app", UpdateState.FAILED, error="校验失败")
                return

            self._emit("app", UpdateState.READY)
            return

        full = appData.get("full", {}).get(platformKey)
        if not full:
            self._emit("app", UpdateState.FAILED, error="当前平台无可用更新")
            return

        archivePath = STAGING_DIR / full["file"]
        sha = full.get("sha256", "")

        await fetchReleaseAsset(APP_REPO, tag, full["file"], archivePath,
                                onProgress=lambda p: self._emit("app", UpdateState.DOWNLOADING, progress=p))

        if sha and not matchChecksum(archivePath, sha):
            archivePath.unlink(missing_ok=True)
            self._emit("app", UpdateState.FAILED, error="校验失败")
            return

        appDir = executableDir.parent.parent if sys.platform == "darwin" else executableDir
        newDir = appDir.parent / f"{appDir.name}_new"
        if newDir.exists():
            await asyncio.to_thread(shutil.rmtree, newDir)

        if sys.platform == "darwin":
            await extractDmg(archivePath, newDir)
        elif archivePath.suffix == ".xz":
            await asyncio.to_thread(extractTarXz, archivePath, newDir)
        else:
            await asyncio.to_thread(extractZip, archivePath, newDir)

        archivePath.unlink(missing_ok=True)
        self._emit("app", UpdateState.READY)

    async def _downloadPack(self, packId: str, info: UpdateInfo) -> None:
        packData = self._versionsData.get("packs", {}).get(packId, {})
        filename = packData.get("file", f"{packId}.zip")
        outputPath = STAGING_DIR / f"{packId}.zip"

        await fetchRawFile(APP_REPO, "main", f"dist/packs/{filename}", outputPath,
                           onProgress=lambda p: self._emit(packId, UpdateState.DOWNLOADING, progress=p))

        expectedSha = packData.get("sha256", "")
        if expectedSha and not matchChecksum(outputPath, expectedSha):
            outputPath.unlink(missing_ok=True)
            self._emit(packId, UpdateState.FAILED, error="校验失败")
            return

        self._emit(packId, UpdateState.READY)

    def _applyPack(self, packId: str) -> None:
        zipPath = STAGING_DIR / f"{packId}.zip"
        if not zipPath.is_file():
            return
        pendingDir = executableDir / "features" / f"{packId}_pending"
        pendingDir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zipPath) as zf:
            zf.extractall(pendingDir)
        zipPath.unlink()
        logger.info("Pack 更新已暂存: {}", packId)

    def _startUpdater(self) -> None:
        updaterName = "updater.exe" if sys.platform == "win32" else "updater"
        updaterPath = executableDir / updaterName
        if not updaterPath.is_file():
            logger.error("updater not found: {}", updaterPath)
            return

        appDir = executableDir.parent.parent if sys.platform == "darwin" else executableDir
        patchPath = STAGING_DIR / "patch.hdiff"
        newDir = appDir.parent / f"{appDir.name}_new"

        args = [str(updaterPath), str(os.getpid()), str(appDir), sys.executable]
        if patchPath.is_file():
            args.append(str(patchPath))
        elif not newDir.is_dir():
            logger.error("no patch or newDir found for update")
            return

        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True

        subprocess.Popen(args, **kwargs)
        logger.info("updater started")

    def _emit(self, targetId: str, state: UpdateState, **kwargs) -> None:
        current = self._infos.get(targetId)
        if current is None:
            info = UpdateInfo(
                targetId=targetId,
                label=kwargs.get("label", targetId),
                currentVersion=kwargs.get("currentVersion", VERSION if targetId == "app" else ""),
                latestVersion=kwargs.get("latestVersion", ""),
                state=state,
                progress=kwargs.get("progress", 0),
                error=kwargs.get("error", ""),
            )
        else:
            info = replace(current, state=state, **{
                k: v for k, v in kwargs.items()
                if k in ("label", "currentVersion", "latestVersion", "progress", "error")
            })
        self._infos[targetId] = info
        self.changed.emit(info)
