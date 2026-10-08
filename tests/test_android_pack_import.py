from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).parents[1]
GRADLE = (ROOT / "android/app/build.gradle.kts").read_text(encoding="utf-8")
SCRIPT = ROOT / "tests/fixtures/import_android_packs.py"


def gradleBlock(name: str) -> str:
    start = GRADLE.index(f'register<Sync>("{name}")')
    return GRADLE[start:GRADLE.index("\n}\n", start)]


def excludesOf(block: str) -> list[str]:
    return re.findall(r'exclude\("([^"]+)"\)', block)


def copyPy(source: Path, target: Path, excludes: list[str], includes: tuple[str, ...]) -> None:
    for path in source.rglob("*"):
        relative = path.relative_to(source).as_posix()
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if not any(fnmatch(relative, pattern) for pattern in includes):
            continue
        if any(fnmatch(relative, pattern) for pattern in excludes):
            continue
        (target / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, target / relative)


def buildAndroidTree(tree: Path) -> list[str]:
    engine = gradleBlock("syncEngineSource")
    copyPy(ROOT / "app", tree / "app", excludesOf(engine), ("*.py",))
    shutil.copytree(ROOT / "android/app/src/main/python/app", tree / "app", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))

    packs = re.search(r"androidPacks = listOf\((.*?)\)", GRADLE, re.S).group(1)
    packs = re.findall(r'"([^"]+)"', packs)
    featureExcludes = excludesOf(gradleBlock("syncFeatureSource"))
    for pack in packs:
        copyPy(ROOT / "features" / pack, tree / "features" / pack, featureExcludes,
               ("*.py", "manifest.toml", "lists/*"))
    (tree / "features/__init__.py").write_text("")
    return packs


def test_every_android_pack_imports_in_the_android_runtime(tmp_path):
    packs = buildAndroidTree(tmp_path / "tree")

    result = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), str(tmp_path / "tree"), *packs],
        capture_output=True, text=True, cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == {}
