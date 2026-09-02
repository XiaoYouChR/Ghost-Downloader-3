from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

DEFAULT_BACKUP_DIR = ".convert_to_pyqt6_backup"

DIRECTORY_EXCLUDES = {
    ".git", ".hg", ".idea", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".venv", "__pycache__", "build", "dist", "node_modules",
}


def convertToPyQt(content: str, relativePath: Path) -> str:
    qtcoreImportRe = re.compile(
        r"^(\s*from\s+PyQt6\.QtCore\s+import\s+)(.+?)(\s*(?:#.*)?\r?\n?)$",
        re.MULTILINE,
    )
    signalRe = re.compile(r"(?<!pyqt)\bSignal(?=\s*\()")
    slotRe = re.compile(r"(?<!pyqt)\bSlot(?=\s*\()")
    propertyRe = re.compile(r"(?<!pyqt)\bProperty(?=\s*\()")

    def rewriteImport(match: re.Match[str]) -> str:
        prefix, imports, suffix = match.groups()
        imports = re.sub(r"(?<!pyqt)\bSignal\b", "pyqtSignal", imports)
        imports = re.sub(r"(?<!pyqt)\bSlot\b", "pyqtSlot", imports)
        imports = re.sub(r"(?<!pyqt)\bProperty\b", "pyqtProperty", imports)
        return f"{prefix}{imports}{suffix}"

    converted = content.replace("PySide6", "PyQt6")
    converted = qtcoreImportRe.sub(rewriteImport, converted)
    converted = signalRe.sub("pyqtSignal", converted)
    converted = slotRe.sub("pyqtSlot", converted)
    converted = propertyRe.sub("pyqtProperty", converted)
    converted = converted.replace("plugin-enable=pyside6", "plugin-enable=pyqt6")

    if relativePath.name == "sync_i18n_res.py":
        syncFindToolRe = re.compile(
            r"def findTool\(name: str\) -> str:\r?\n.*?(?=\r?\ndef findSources)",
            re.DOTALL,
        )
        syncFindToolNew = (
            "def findTool(*names: str) -> str:\n"
            "    for name in names:\n"
            "        executable = shutil.which(name)\n"
            "        if executable:\n"
            "            return executable\n"
            "\n"
            "        suffix = \".exe\" if os.name == \"nt\" else \"\"\n"
            "        candidate = Path(sys.executable).resolve().with_name(f\"{name}{suffix}\")\n"
            "        if candidate.exists():\n"
            "            return str(candidate)\n"
            "\n"
            "    raise FileNotFoundError(f\"Required tool was not found in PATH: {', '.join(names)}\")\n"
        )
        newline = "\r\n" if "\r\n" in converted else "\n"
        converted = syncFindToolRe.sub(
            syncFindToolNew.replace("\n", newline) + newline,
            converted,
            count=1,
        )
        converted = converted.replace(
            'findTool("pyside6-lupdate")',
            'findTool("pylupdate6", "lupdate", "pyside6-lupdate")',
        )
        converted = converted.replace(
            'findTool("pyside6-lrelease")',
            'findTool("lrelease", "pyside6-lrelease")',
        )
        converted = converted.replace(
            'findTool("pyside6-rcc")',
            'findTool("rcc", "pyside6-rcc")',
        )

    return converted


def isExcluded(relativePath: Path) -> bool:
    if any(part in DIRECTORY_EXCLUDES for part in relativePath.parts[:-1]):
        return True
    if relativePath.name in {"convert_to_pyqt5.py", Path(__file__).name, "uv.lock"}:
        return True
    if relativePath.parts and relativePath.parts[0] == DEFAULT_BACKUP_DIR:
        return True
    return False


def findFiles(root: Path, includeMarkdown: bool) -> list[Path]:
    textExtensions = {".md", ".py", ".toml", ".txt"}
    files: list[Path] = []

    for currentRoot, dirNames, fileNames in os.walk(root):
        currentPath = Path(currentRoot)

        dirNames[:] = [
            name for name in dirNames
            if name not in DIRECTORY_EXCLUDES
            and name != DEFAULT_BACKUP_DIR
        ]

        for fileName in sorted(fileNames):
            candidate = currentPath / fileName
            relativePath = candidate.relative_to(root)

            if isExcluded(relativePath):
                continue

            suffix = candidate.suffix.lower()
            if suffix not in textExtensions:
                continue
            if suffix == ".md" and not includeMarkdown:
                continue

            files.append(candidate)

    return files


def copyTree(source: Path, output: Path) -> None:
    for currentRoot, dirNames, fileNames in os.walk(source):
        currentPath = Path(currentRoot)
        relativeRoot = currentPath.relative_to(source)

        dirNames[:] = [
            name for name in dirNames
            if name not in DIRECTORY_EXCLUDES
            and name != DEFAULT_BACKUP_DIR
        ]

        destRoot = output / relativeRoot
        destRoot.mkdir(parents=True, exist_ok=True)

        for fileName in fileNames:
            sourcePath = currentPath / fileName
            relativePath = sourcePath.relative_to(source)
            if isExcluded(relativePath):
                continue
            destPath = output / relativePath
            destPath.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sourcePath, destPath)


def parseArgs() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a PySide6 project to PyQt6 with minimal code changes.",
    )
    parser.add_argument(
        "source_dir", nargs="?", default=".",
        help="Project root to convert. Defaults to the current directory.",
    )
    parser.add_argument(
        "-o", "--output-dir",
        help="Write the converted project to this directory. Ignored with --in-place.",
    )
    parser.add_argument(
        "--in-place", action="store_true",
        help="Rewrite the project in place instead of writing a copy.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report the files that would change without writing them.",
    )
    parser.add_argument(
        "--backup-dir", default=DEFAULT_BACKUP_DIR,
        help="Backup directory used with --in-place. Use an empty string to disable backups.",
    )
    parser.add_argument(
        "--include-markdown", action="store_true",
        help="Also rewrite Markdown documentation files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parseArgs()
    sourceDir = Path(args.source_dir).resolve()

    if not sourceDir.is_dir():
        raise SystemExit(f"Source directory does not exist: {sourceDir}")

    if args.in_place and args.output_dir:
        raise SystemExit("--output-dir cannot be used together with --in-place")

    if args.in_place:
        outputDir = None
    elif args.output_dir:
        outputDir = Path(args.output_dir).resolve()
    else:
        outputDir = sourceDir.parent / f"{sourceDir.name}_pyqt6"

    if outputDir is not None and outputDir == sourceDir:
        raise SystemExit("Output directory must be different from the source directory")

    if outputDir is not None:
        try:
            outputDir.relative_to(sourceDir)
        except ValueError:
            pass
        else:
            raise SystemExit("Output directory must not be inside the source directory")

    if outputDir is not None and not args.in_place and not args.dry_run:
        copyTree(sourceDir, outputDir)

    changedFiles = 0
    inspectedFiles = 0
    backupRoot = sourceDir / args.backup_dir

    for filePath in findFiles(sourceDir, includeMarkdown=args.include_markdown):
        relativePath = filePath.relative_to(sourceDir)
        inspectedFiles += 1

        try:
            with filePath.open("r", encoding="utf-8", newline="") as f:
                original = f.read()
        except UnicodeDecodeError:
            print(f"[skip] {relativePath} is not UTF-8 text")
            continue

        if relativePath.suffix.lower() == ".py":
            converted = convertToPyQt(original, relativePath)
        else:
            converted = original.replace("pyside6-fluent-widgets", "pyqt6-fluent-widgets")
            converted = converted.replace("pyside6", "pyqt6")
            converted = converted.replace("PySide6", "PyQt6")

        if converted == original:
            continue

        changedFiles += 1
        dest = filePath if args.in_place else outputDir / relativePath
        print(f"[change] {relativePath}")

        if args.dry_run:
            continue

        if args.in_place and args.backup_dir:
            backupPath = backupRoot / relativePath
            if not backupPath.exists():
                backupPath.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(filePath, backupPath)

        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("w", encoding="utf-8", newline="") as f:
            f.write(converted)

    print(
        f"Done. inspected={inspectedFiles}, changed={changedFiles}, "
        f"mode={'in-place' if args.in_place else 'copy'}"
    )

    if args.in_place and changedFiles and not args.dry_run and args.backup_dir:
        print(f"Backups saved to: {backupRoot}")

    if outputDir is not None and not args.in_place:
        print(f"Converted project saved to: {outputDir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
