from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from app.models.pack import PackManifest

if TYPE_CHECKING:
    from app.models.pack import FeaturePack


def seedPacks(seedDir: Path, targetDir: Path) -> None:
    from PySide6.QtCore import QVersionNumber

    if not seedDir.exists():
        return
    targetDir.mkdir(parents=True, exist_ok=True)

    for packDir in sorted(seedDir.iterdir()):
        if not packDir.is_dir() or packDir.name.startswith("."):
            continue
        seedManifest = PackManifest.fromDir(packDir)
        if seedManifest is None or not seedManifest.version:
            continue

        target = targetDir / packDir.name
        userManifest = PackManifest.fromDir(target) if target.exists() else None

        if userManifest is not None and userManifest.version:
            seedVersion = QVersionNumber.fromString(seedManifest.version)
            userVersion = QVersionNumber.fromString(userManifest.version)
            if userVersion >= seedVersion:
                continue

        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(packDir, target)
        logger.info("种子 Pack 已同步: {} {}", packDir.name, seedManifest.version)


def loadPacks(featuresDir: Path, services=None) -> list[FeaturePack]:
    from PySide6.QtCore import QVersionNumber
    from app.config.constants import VERSION

    if not featuresDir.exists():
        logger.warning("features 目录不存在: {}", featuresDir)
        return []

    appVersion = QVersionNumber.fromString(VERSION)

    manifests = []
    for p in sorted(featuresDir.iterdir()):
        if not p.is_dir() or p.name.startswith("."):
            continue
        m = PackManifest.fromDir(p)
        if m is None:
            continue
        if m.gdMinVersion:
            required = QVersionNumber.fromString(m.gdMinVersion)
            if appVersion < required:
                logger.warning("跳过 FeaturePack {}：需要 GD ≥ {}，当前 {}", m.name, m.gdMinVersion, VERSION)
                continue
        manifests.append(m)

    ordered = orderedByDependency(manifests)
    return [pack for m in ordered if (pack := loadManifest(m, services)) is not None]


def orderedByDependency(manifests: list[PackManifest]) -> list[PackManifest]:
    byName: dict[str, PackManifest] = {m.name: m for m in manifests}
    visiting: list[str] = []
    visited: set[str] = set()
    ordered: list[PackManifest] = []
    skipped: set[str] = set()

    def visit(name: str):
        if name in visited:
            return
        if name in skipped:
            raise ValueError(f"{name} 依赖的 FeaturePack 已被跳过")
        if name in visiting:
            cycle = visiting[visiting.index(name):] + [name]
            raise ValueError(f"循环依赖: {' -> '.join(cycle)}")

        visiting.append(name)
        for dep in byName[name].dependencies:
            if dep not in byName:
                raise ValueError(f"{name} 依赖未找到的 FeaturePack: {dep}")
            visit(dep)
        visiting.pop()
        visited.add(name)
        ordered.append(byName[name])

    for m in manifests:
        try:
            visit(m.name)
        except Exception as e:
            skipped.add(m.name)
            visiting.clear()
            logger.opt(exception=e).error("跳过 FeaturePack {}", m.name)

    return [m for m in ordered if m.name not in skipped]


def loadManifest(manifest: PackManifest, services=None) -> FeaturePack | None:
    moduleName = manifest.name
    try:
        spec = importlib.util.spec_from_file_location(
            moduleName,
            manifest.entryPath,
            submodule_search_locations=[str(manifest.folder)],
        )
        if spec is None or spec.loader is None:
            logger.error("无法创建模块规格: {}", moduleName)
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[moduleName] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(moduleName, None)
            raise

        PackClass = getattr(module, manifest.className, None)
        if PackClass is None:
            logger.warning("未找到类 {}: {}", manifest.className, moduleName)
            return None

        pack = PackClass(services)
        pack.manifest = manifest
        logger.success("加载 FeaturePack: {}", moduleName)
        return pack

    except Exception as e:
        sys.modules.pop(moduleName, None)
        logger.opt(exception=e).error("加载 FeaturePack 失败: {}", moduleName)
        return None
