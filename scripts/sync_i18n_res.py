import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LANGUAGES = ["zh_CN", "en_US", "ja_JP", "zh_TW", "zh_HK", "ru_RU", "pt_BR"]
ASSETS_DIR = REPO / "app" / "assets"
I18N_DIR = ASSETS_DIR / "i18n"
QRC_PATH = ASSETS_DIR / "resources.qrc"
RESOURCES_PY = ASSETS_DIR / "resources.py"


def findTool(name: str) -> str:
    path = shutil.which(name)
    if path:
        return path
    candidate = Path(sys.executable).resolve().with_name(
        f"{name}{'.exe' if os.name == 'nt' else ''}")
    if candidate.exists():
        return str(candidate)
    raise FileNotFoundError(f"Required tool not found in PATH: {name}")


def findSources() -> list[str]:
    sources = []
    for root in ("app", "features"):
        for path in sorted((REPO / root).rglob("*.py")):
            if path == RESOURCES_PY:
                continue
            sources.append(path.relative_to(REPO).as_posix())
    return sources


def updateTsFiles(sources: list[str]) -> None:
    lupdate = findTool("pyside6-lupdate")
    for locale in LANGUAGES:
        subprocess.run([
            lupdate, "-no-ui-lines",
            "-source-language", "zh_CN",
            "-target-language", locale,
            *sources,
            "-ts", (I18N_DIR / f"gd3.{locale}.ts").as_posix(),
        ], cwd=REPO, check=True)


def buildQmFiles() -> None:
    lrelease = findTool("pyside6-lrelease")
    for locale in LANGUAGES:
        ts = I18N_DIR / f"gd3.{locale}.ts"
        qm = I18N_DIR / f"gd3.{locale}.qm"
        subprocess.run([lrelease, ts.as_posix(), "-qm", qm.as_posix()],
                       cwd=REPO, check=True)


def updateQrcI18n() -> None:
    text = QRC_PATH.read_text(encoding="utf-8")
    text = re.sub(
        r'\s*<qresource prefix="i18n">.*?</qresource>',
        '', text, flags=re.DOTALL,
    )
    entries = "\n".join(
        f'    <file alias="gd3.{l}.qm">i18n/gd3.{l}.qm</file>'
        for l in LANGUAGES
    )
    section = f'\n  <qresource prefix="i18n">\n{entries}\n  </qresource>'
    text = text.replace("</RCC>", f"{section}\n</RCC>")
    QRC_PATH.write_text(text, encoding="utf-8")


def buildResources() -> None:
    rcc = findTool("pyside6-rcc")
    subprocess.run([
        rcc, "-g", "python",
        "-o", RESOURCES_PY.as_posix(),
        QRC_PATH.as_posix(),
    ], cwd=REPO, check=True)


def main() -> int:
    I18N_DIR.mkdir(parents=True, exist_ok=True)

    sources = findSources()
    updateTsFiles(sources)
    buildQmFiles()
    updateQrcI18n()
    buildResources()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
