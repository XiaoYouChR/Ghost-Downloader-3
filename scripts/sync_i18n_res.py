import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

LANGUAGES = ["zh_CN", "en_US", "ja_JP", "zh_TW", "zh_HK", "ru_RU", "pt_BR"]


def findTool(name: str) -> str:
    executable = shutil.which(name)
    if executable:
        return executable

    suffix = ".exe" if os.name == "nt" else ""
    candidate = Path(sys.executable).resolve().with_name(f"{name}{suffix}")
    if candidate.exists():
        return str(candidate)

    raise FileNotFoundError(f"Required tool was not found in PATH: {name}")


def findSources(root: str) -> list[str]:
    sources: list[str] = []
    baseDir = REPO / root

    for dirPath, _, fileNames in os.walk(baseDir):
        for fileName in fileNames:
            if not fileName.endswith(".py"):
                continue

            fullPath = Path(dirPath, fileName).resolve()
            relPath = fullPath.relative_to(REPO)

            if relPath == Path("app/assets/resources.py"):
                continue

            sources.append(relPath.as_posix())

    return sorted(sources)


def main() -> int:
    os.chdir(REPO)

    sources = findSources("app")
    sources.extend(findSources("features"))

    i18nDir = REPO / "app" / "assets" / "i18n"
    i18nDir.mkdir(parents=True, exist_ok=True)

    lupdate = findTool("pyside6-lupdate")
    for locale in LANGUAGES:
        tsPath = i18nDir / f"gd3.{locale}.ts"
        subprocess.run([
            lupdate, "-no-ui-lines",
            "-source-language", "zh_CN",
            "-target-language", locale,
            *sources,
            "-ts", tsPath.as_posix(),
        ], cwd=REPO, check=True)

    lrelease = findTool("pyside6-lrelease")
    for locale in LANGUAGES:
        tsPath = i18nDir / f"gd3.{locale}.ts"
        qmPath = i18nDir / f"gd3.{locale}.qm"
        subprocess.run([
            lrelease, tsPath.as_posix(),
            "-qm", qmPath.as_posix(),
        ], cwd=REPO, check=True)

    rcc = findTool("pyside6-rcc")
    resourcesQrc = REPO / "app" / "assets" / "resources.qrc"
    resourcesPy = REPO / "app" / "assets" / "resources.py"
    subprocess.run([
        rcc, "-g", "python",
        "-o", resourcesPy.as_posix(),
        resourcesQrc.as_posix(),
    ], cwd=REPO, check=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
