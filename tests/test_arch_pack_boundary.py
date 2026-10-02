import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
PACK_NAMES = sorted(p.parent.name for p in (ROOT / "features").glob("*/manifest.toml"))


def findAppFiles() -> list[Path]:
    return [
        *(ROOT / "app").rglob("*.py"),
        ROOT / "Ghost-Downloader-3.py",
        *(ROOT / "android/app/src/main/python").rglob("*.py"),
    ]


def matchPackModule(module: str) -> str | None:
    parts = module.split(".")
    if parts[0] == "features" and len(parts) > 1:
        parts = parts[1:]
    return parts[0] if parts[0] in PACK_NAMES else None


def parseViolations(source: str) -> list[tuple[int, str]]:
    violations = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules = [node.module]
            if node.module == "features":
                modules += [alias.name for alias in node.names]
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            modules = [name for name in PACK_NAMES if re.search(rf"(?<!\w){name}(?!\w)", node.value)]
        else:
            continue
        violations += [(node.lineno, pack) for module in modules if (pack := matchPackModule(module))]
    return violations


@pytest.mark.parametrize("source", [
    "import ed2k_pack",
    "import ed2k_pack.task as t",
    "from ed2k_pack.task import ED2kTask",
    "from ed2k_pack import task",
    "import features.ed2k_pack",
    "from features import ed2k_pack",
    "from features.ed2k_pack.kelpie import Error",
    "importlib.import_module('ed2k_pack.session')",
    "__import__('features.ed2k_pack')",
    "sys.modules['ed2k_pack']",
    "Path('features/ed2k_pack/kelpie')",
])
def test_detector_catches_pack_reference(source):
    assert parseViolations(source) == [(1, "ed2k_pack")]


@pytest.mark.parametrize("source", [
    "import features",
    "from app.models.pack import FeaturePack",
    "pack = featureService.packById('ed2k')",
    "name = 'my_ed2k_pack'",
])
def test_detector_ignores_non_pack_reference(source):
    assert parseViolations(source) == []


def test_app_layer_reaches_packs_only_through_feature_pack():
    violations = [
        f"{path.relative_to(ROOT)}:{line} -> {pack}"
        for path in findAppFiles()
        for line, pack in parseViolations(path.read_text(encoding="utf-8"))
    ]
    assert violations == []
