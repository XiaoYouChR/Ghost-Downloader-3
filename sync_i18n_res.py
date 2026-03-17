import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
I18N_DIR = ROOT_DIR / "app" / "assets" / "i18n"
RESOURCES_QRC = ROOT_DIR / "app" / "assets" / "resources.qrc"
RESOURCES_PY = ROOT_DIR / "app" / "assets" / "resources.py"
SOURCE_LANGUAGE = "zh_CN"
RUNTIME_LANGUAGES = ["en_US", "ja_JP", "zh_TW", "zh_HK", "ru_RU"]
SYNC_LANGUAGES = [SOURCE_LANGUAGE, *RUNTIME_LANGUAGES]
EXCLUDED_FILES = {
    Path("app/assets/resources.py"),
}


def resolve_tool(tool_name: str) -> str:
    executable = shutil.which(tool_name)
    if executable:
        return executable

    suffix = ".exe" if os.name == "nt" else ""
    candidate = Path(sys.executable).resolve().with_name(f"{tool_name}{suffix}")
    if candidate.exists():
        return str(candidate)

    raise FileNotFoundError(f"Required tool was not found in PATH: {tool_name}")


def get_py_files(root_dir: str) -> list[str]:
    py_files: list[str] = []
    base_dir = ROOT_DIR / root_dir

    for root, _, files in os.walk(base_dir):
        for file_name in files:
            if not file_name.endswith(".py"):
                continue

            full_path = Path(root, file_name).resolve()
            rel_path = full_path.relative_to(ROOT_DIR)
            if rel_path in EXCLUDED_FILES:
                continue

            py_files.append(rel_path.as_posix())

    return sorted(py_files)


def run_command(command: list[str]) -> None:
    result = subprocess.run(command, cwd=ROOT_DIR, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def update_ts_files(py_files: list[str]) -> None:
    lupdate = resolve_tool("pyside6-lupdate")
    I18N_DIR.mkdir(parents=True, exist_ok=True)

    for language in SYNC_LANGUAGES:
        ts_path = I18N_DIR / f"gd3.{language}.ts"
        run_command([
            lupdate,
            "-no-ui-lines",
            "-source-language",
            SOURCE_LANGUAGE,
            "-target-language",
            language,
            *py_files,
            "-ts",
            ts_path.as_posix(),
        ])


def build_qm_files() -> None:
    lrelease = resolve_tool("pyside6-lrelease")

    for language in RUNTIME_LANGUAGES:
        ts_path = I18N_DIR / f"gd3.{language}.ts"
        qm_path = I18N_DIR / f"gd3.{language}.qm"
        run_command([
            lrelease,
            ts_path.as_posix(),
            "-qm",
            qm_path.as_posix(),
        ])


def rebuild_resources() -> None:
    rcc = resolve_tool("pyside6-rcc")
    run_command([
        rcc,
        "-g",
        "python",
        "-o",
        RESOURCES_PY.as_posix(),
        RESOURCES_QRC.as_posix(),
    ])


def main() -> int:
    py_files = get_py_files("app")
    py_files.extend(get_py_files("features"))

    update_ts_files(py_files)
    build_qm_files()
    rebuild_resources()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
