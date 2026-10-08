import importlib
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

BLOCKED = ("PySide6", "qfluentwidgets", "qframelesswindow", "shiboken6")


class BlockQt:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ImportError(f"{name} 不在 Android 运行时里")


tree, packs = Path(sys.argv[1]), sys.argv[2:]
sys.meta_path.insert(0, BlockQt())
sys.modules["java"] = MagicMock()
sys.path.insert(0, str(tree))
sys.path.insert(0, str(tree / "features"))

failures = {}
for pack in packs:
    for module in ("pack", "android"):
        if not (tree / "features" / pack / f"{module}.py").exists():
            continue
        try:
            importlib.import_module(f"{pack}.{module}")
        except Exception as e:
            failures[f"{pack}.{module}"] = f"{type(e).__name__}: {e}"
print(json.dumps(failures))
