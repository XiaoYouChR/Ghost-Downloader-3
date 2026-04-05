from __future__ import annotations

import argparse
import os
import re
import shutil
from pathlib import Path


SCRIPT_NAME = Path(__file__).name
DEFAULT_BACKUP_DIR = ".convert_to_pyqt6_backup"
DIRECTORY_EXCLUDES = {
    ".git",
    ".hg",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
FILE_EXCLUDES = {
    "convert_to_pyqt5.py",
    SCRIPT_NAME,
    "uv.lock",
}
TEXT_FILE_EXTENSIONS = {".md", ".py", ".toml", ".txt"}

QTCORE_IMPORT_RE = re.compile(
    r"^(\s*from\s+PyQt6\.QtCore\s+import\s+)(.+?)(\s*(?:#.*)?\r?\n?)$",
    re.MULTILINE,
)
SIGNAL_CALL_RE = re.compile(r"(?<!pyqt)\bSignal(?=\s*\()")
SLOT_CALL_RE = re.compile(r"(?<!pyqt)\bSlot(?=\s*\()")
PROPERTY_CALL_RE = re.compile(r"(?<!pyqt)\bProperty(?=\s*\()")

SYNC_RESOLVE_TOOL_OLD = "def resolve_tool(tool_name: str) -> str:"
SYNC_RESOLVE_TOOL_RE = re.compile(
    r"def resolve_tool\(tool_name: str\) -> str:\r?\n.*?(?=\r?\ndef get_py_files)",
    re.DOTALL,
)
SYNC_RESOLVE_TOOL_NEW = """def resolve_tool(*tool_names: str) -> str:
    for tool_name in tool_names:
        executable = shutil.which(tool_name)
        if executable:
            return executable

        suffix = ".exe" if os.name == "nt" else ""
        candidate = Path(sys.executable).resolve().with_name(f"{tool_name}{suffix}")
        if candidate.exists():
            return str(candidate)

    formatted_names = ", ".join(tool_names)
    raise FileNotFoundError(f"Required tool was not found in PATH: {formatted_names}")
"""


def replace_qtcore_imports(line_match: re.Match[str]) -> str:
    prefix, imports, suffix = line_match.groups()
    imports = re.sub(r"(?<!pyqt)\bSignal\b", "pyqtSignal", imports)
    imports = re.sub(r"(?<!pyqt)\bSlot\b", "pyqtSlot", imports)
    imports = re.sub(r"(?<!pyqt)\bProperty\b", "pyqtProperty", imports)
    return f"{prefix}{imports}{suffix}"


def convert_python_content(content: str, relative_path: Path) -> str:
    converted = content.replace("PySide6", "PyQt6")
    converted = QTCORE_IMPORT_RE.sub(replace_qtcore_imports, converted)
    converted = SIGNAL_CALL_RE.sub("pyqtSignal", converted)
    converted = SLOT_CALL_RE.sub("pyqtSlot", converted)
    converted = PROPERTY_CALL_RE.sub("pyqtProperty", converted)
    converted = converted.replace("plugin-enable=pyside6", "plugin-enable=pyqt6")

    if relative_path.as_posix() == "sync_i18n_res.py":
        converted = convert_sync_i18n_res(converted)

    return converted


def convert_sync_i18n_res(content: str) -> str:
    newline = "\r\n" if "\r\n" in content else "\n"

    if SYNC_RESOLVE_TOOL_OLD in content:
        resolve_tool_block = SYNC_RESOLVE_TOOL_NEW.replace("\n", newline)
        content = SYNC_RESOLVE_TOOL_RE.sub(
            f"{resolve_tool_block}{newline}",
            content,
            count=1,
        )

    content = content.replace(
        'resolve_tool("pyside6-lupdate")',
        'resolve_tool("pylupdate6", "lupdate", "pyside6-lupdate")',
    )
    content = content.replace(
        'resolve_tool("pyside6-lrelease")',
        'resolve_tool("lrelease", "pyside6-lrelease")',
    )
    content = content.replace(
        'resolve_tool("pyside6-rcc")',
        'resolve_tool("rcc", "pyside6-rcc")',
    )
    return content


def convert_text_content(content: str) -> str:
    converted = content.replace("pyside6-fluent-widgets", "pyqt6-fluent-widgets")
    converted = converted.replace("pyside6", "pyqt6")
    converted = converted.replace("PySide6", "PyQt6")
    return converted


def is_skipped(relative_path: Path) -> bool:
    if any(part in DIRECTORY_EXCLUDES for part in relative_path.parts[:-1]):
        return True

    if relative_path.name in FILE_EXCLUDES:
        return True

    if relative_path.parts and relative_path.parts[0] == DEFAULT_BACKUP_DIR:
        return True

    return False


def is_text_file(path: Path, include_markdown: bool) -> bool:
    suffix = path.suffix.lower()
    if suffix not in TEXT_FILE_EXTENSIONS:
        return False

    if suffix == ".md" and not include_markdown:
        return False

    return True


def iter_project_files(root_dir: Path, include_markdown: bool) -> list[Path]:
    files: list[Path] = []

    for current_root, dir_names, file_names in os.walk(root_dir):
        current_path = Path(current_root)
        relative_root = current_path.relative_to(root_dir)

        dir_names[:] = [
            name
            for name in dir_names
            if name not in DIRECTORY_EXCLUDES
            and name != DEFAULT_BACKUP_DIR
        ]

        for file_name in sorted(file_names):
            candidate = current_path / file_name
            relative_path = candidate.relative_to(root_dir)

            if is_skipped(relative_path):
                continue

            if is_text_file(candidate, include_markdown):
                files.append(candidate)

    return files


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as file:
        return file.read()


def write_text(path: Path, content: str) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8", newline="") as file:
        file.write(content)


def create_backup(source_root: Path, backup_root: Path, file_path: Path) -> None:
    relative_path = file_path.relative_to(source_root)
    backup_path = backup_root / relative_path

    if backup_path.exists():
        return

    ensure_parent(backup_path)
    shutil.copy2(file_path, backup_path)


def convert_file_content(content: str, relative_path: Path) -> str:
    if relative_path.suffix.lower() == ".py":
        return convert_python_content(content, relative_path)

    return convert_text_content(content)


def copy_project_tree(source_dir: Path, output_dir: Path) -> None:
    for current_root, dir_names, file_names in os.walk(source_dir):
        current_path = Path(current_root)
        relative_root = current_path.relative_to(source_dir)

        dir_names[:] = [
            name
            for name in dir_names
            if name not in DIRECTORY_EXCLUDES
            and name != DEFAULT_BACKUP_DIR
        ]

        destination_root = output_dir / relative_root
        destination_root.mkdir(parents=True, exist_ok=True)

        for file_name in file_names:
            source_path = current_path / file_name
            relative_path = source_path.relative_to(source_dir)
            if is_skipped(relative_path):
                continue

            destination_path = output_dir / relative_path
            ensure_parent(destination_path)
            shutil.copy2(source_path, destination_path)


def process_directory(
    source_dir: Path,
    output_dir: Path | None,
    *,
    in_place: bool,
    dry_run: bool,
    backup_dir_name: str,
    include_markdown: bool,
) -> int:
    changed_files = 0
    inspected_files = 0
    backup_root = source_dir / backup_dir_name

    if output_dir is not None and not in_place and not dry_run:
        copy_project_tree(source_dir, output_dir)

    for file_path in iter_project_files(source_dir, include_markdown=include_markdown):
        relative_path = file_path.relative_to(source_dir)
        inspected_files += 1

        try:
            original_content = read_text(file_path)
        except UnicodeDecodeError:
            print(f"[skip] {relative_path} is not UTF-8 text")
            continue

        converted_content = convert_file_content(original_content, relative_path)
        if converted_content == original_content:
            continue

        changed_files += 1
        destination = file_path if in_place else output_dir / relative_path
        print(f"[change] {relative_path}")

        if dry_run:
            continue

        if in_place and backup_dir_name:
            create_backup(source_dir, backup_root, file_path)

        write_text(destination, converted_content)

    print(
        f"Done. inspected={inspected_files}, changed={changed_files}, "
        f"mode={'in-place' if in_place else 'copy'}"
    )

    if in_place and changed_files and not dry_run and backup_dir_name:
        print(f"Backups saved to: {backup_root}")

    if output_dir is not None and not in_place:
        print(f"Converted project saved to: {output_dir}")

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a PySide6 project to PyQt6 with minimal code changes.",
    )
    parser.add_argument(
        "source_dir",
        nargs="?",
        default=".",
        help="Project root to convert. Defaults to the current directory.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        help="Write the converted project to this directory. Ignored with --in-place.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Rewrite the project in place instead of writing a copy.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the files that would change without writing them.",
    )
    parser.add_argument(
        "--backup-dir",
        default=DEFAULT_BACKUP_DIR,
        help=(
            "Backup directory used with --in-place. "
            "Use an empty string to disable backups."
        ),
    )
    parser.add_argument(
        "--include-markdown",
        action="store_true",
        help="Also rewrite Markdown documentation files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_dir = Path(args.source_dir).resolve()

    if not source_dir.is_dir():
        raise SystemExit(f"Source directory does not exist: {source_dir}")

    if args.in_place and args.output_dir:
        raise SystemExit("--output-dir cannot be used together with --in-place")

    if args.in_place:
        output_dir = None
    elif args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    else:
        output_dir = source_dir.parent / f"{source_dir.name}_pyqt6"

    if output_dir is not None and output_dir == source_dir:
        raise SystemExit("Output directory must be different from the source directory")

    if output_dir is not None:
        try:
            output_dir.relative_to(source_dir)
        except ValueError:
            pass
        else:
            raise SystemExit("Output directory must not be inside the source directory")

    return process_directory(
        source_dir=source_dir,
        output_dir=output_dir,
        in_place=args.in_place,
        dry_run=args.dry_run,
        backup_dir_name=args.backup_dir,
        include_markdown=args.include_markdown,
    )


if __name__ == "__main__":
    raise SystemExit(main())
