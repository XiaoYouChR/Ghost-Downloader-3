import ast
import re
from pathlib import Path


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


def test_find_no_pack_import_in_app():
    violations = [
        f"{path.relative_to(ROOT)}:{line} -> {pack}"
        for path in findAppFiles()
        for line, pack in parseViolations(path.read_text(encoding="utf-8"))
    ]
    assert violations == []
