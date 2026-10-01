#!/usr/bin/env python3
"""Copy python_ed2k from a Python-eD2k checkout into ed2k_pack, unchanged.

Usage:
    python scripts/sync_python_ed2k.py ~/PycharmProjects/Python-eD2k
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "features" / "ed2k_pack" / "python_ed2k"


def main() -> None:
    source = Path(sys.argv[1]).expanduser() / "python_ed2k"
    if not (source / "client.py").is_file():
        sys.exit(f"Not a Python-eD2k checkout: {source.parent}")
    shutil.rmtree(TARGET)
    shutil.copytree(source, TARGET, ignore=shutil.ignore_patterns("__pycache__"))


if __name__ == "__main__":
    main()
