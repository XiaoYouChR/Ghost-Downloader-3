from __future__ import annotations

import importlib.util
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from app.models.pack import FeaturePack


@dataclass(frozen=True)
class PackManifest:
    name: str
    entryPath: Path
    folder: Path
    dependencies: tuple[str, ...]

    @classmethod
    def fromDir(cls, packDir: Path) -> PackManifest | None:
        manifestPath = packDir / "manifest.toml"
        if not manifestPath.exists():
            logger.warning("FeaturePack 缺少 manifest.toml: {}", packDir)
            return None

        try:
            raw = tomllib.loads(manifestPath.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("无法读取 manifest {}: {}", manifestPath, repr(e))
            return None

        packSection = raw.get("pack")
        if not isinstance(packSection, dict):
            logger.warning("manifest 缺少 [pack] 节: {}", manifestPath)
            return None

        entry = packSection.get("entry", "pack.py")
        if not isinstance(entry, str) or not entry.strip():
            logger.warning("manifest entry 无效: {}", manifestPath)
            return None

        entryPath = packDir / entry
        if not entryPath.exists() and entry.endswith(".py"):
            entryPath = packDir / (entry[:-3] + ".pyc")
        if not entryPath.exists():
            logger.warning("入口文件不存在: {}", packDir / entry)
            return None

        deps = packSection.get("dependencies", [])
        if not isinstance(deps, list) or any(
            not isinstance(d, str) or not d for d in deps
        ):
            logger.warning("manifest dependencies 无效: {}", manifestPath)
            return None

        return cls(
            name=packDir.name,
            entryPath=entryPath,
            folder=packDir,
            dependencies=tuple(deps),
        )


def loadPacks(featuresDir: Path) -> list[FeaturePack]:
    if not featuresDir.exists():
        logger.warning("features 目录不存在: {}", featuresDir)
        return []

    manifests = [
        m for p in sorted(featuresDir.iterdir())
        if p.is_dir() and not p.name.startswith(".")
        if (m := PackManifest.fromDir(p)) is not None
    ]
    ordered = orderedByDependency(manifests)
    return [pack for m in ordered if (pack := loadManifest(m)) is not None]


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


def loadManifest(manifest: PackManifest) -> FeaturePack | None:
    from app.models.pack import FeaturePack

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

        for attrName in dir(module):
            attr = getattr(module, attrName)
            if (
                isinstance(attr, type)
                and issubclass(attr, FeaturePack)
                and attr is not FeaturePack
                and attr.__module__ == moduleName
            ):
                pack = attr()
                logger.success("加载 FeaturePack: {}", moduleName)
                return pack

        logger.warning("未找到 FeaturePack 子类: {}", moduleName)
        return None

    except Exception as e:
        sys.modules.pop(moduleName, None)
        logger.opt(exception=e).error("加载 FeaturePack 失败: {}", moduleName)
        return None
