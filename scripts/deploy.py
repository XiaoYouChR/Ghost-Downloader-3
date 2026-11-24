import ast
import importlib.util
import os
import plistlib
import shutil
import subprocess
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.config.constants import VERSION, BUILD_VERSION, YEAR, AUTHOR, DESKTOP_ID

MACOS_DOCUMENT_TYPES = [
    {"name": "种子文件", "extensions": ["torrent"], "icon": "torrent"},
    {"name": "M3U8 播放列表", "extensions": ["m3u8", "m3u"], "icon": "m3u8"},
    {"name": "DASH 清单", "extensions": ["mpd"], "icon": "m3u8"},
]

EXCLUDED_PACKS = {"jack_yao"}

PLATFORM_INCLUDE_PACKAGES = {
    "win32": ["winrt"],
}
# 应用不读 PDF 图像，也不需要虚拟键盘。只排除插件时 Nuitka 仍可能带入其依赖库，所以成对排除。
PLATFORM_EXCLUDED_DLLS = {
    "win32": ["PySide6/qt-plugins/imageformats/qpdf.dll", "qt6pdf.dll"],
    "darwin": ["PySide6/qt-plugins/imageformats/libqpdf.dylib", "QtPdf"],
    "linux": [
        "PySide6/qt-plugins/imageformats/libqpdf.so",
        "libQt6Pdf.so.6",
        "PySide6/qt-plugins/platforminputcontexts/libqtvirtualkeyboardplugin.so",
        "libQt6VirtualKeyboard.so.6",
    ],
}
EXTRA_INCLUDE_MODULES = [
    "app.view.dialogs.edit_task",
    "concurrent.futures",
    "email.header",
    "html.entities",
    "html.parser",
    "http.client",
    "http.cookiejar",
    "http.cookies",
    "http.server",
    "urllib.error",
    "urllib.response",
    "xml.etree.ElementTree",
]


def _isTypeCheckingGuard(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _typeCheckingImportIds(tree: ast.Module) -> set[int]:
    ids: set[int] = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.If) and _isTypeCheckingGuard(stmt.test):
            for node in ast.walk(stmt):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    ids.add(id(node))
    return ids


def isModule(dotted: str) -> bool:
    if dotted.split(".")[0] == "app":
        base = REPO / Path(*dotted.split("."))
        return base.with_suffix(".py").is_file() or (base / "__init__.py").is_file()
    try:
        return importlib.util.find_spec(dotted) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def findImports(files: Iterable[Path], ignoredTopLevels: Iterable[str] = ()) -> set[str]:
    ignored = set(ignoredTopLevels)
    modules: set[str] = set()
    for source in files:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        typeCheckingIds = _typeCheckingImportIds(tree)
        for node in ast.walk(tree):
            if id(node) in typeCheckingIds:
                continue
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top and top not in sys.stdlib_module_names and top not in ignored and isModule(alias.name):
                        modules.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                module = node.module
                top = module.split(".")[0]
                if not top or top in sys.stdlib_module_names or top in ignored:
                    continue
                if isModule(module):
                    modules.add(module)
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    dotted = f"{module}.{alias.name}"
                    if isModule(dotted):
                        modules.add(dotted)

    return modules


def findQfwModules(
    files: Iterable[Path],
    packageExports: Mapping[str, Mapping[str, str]],
) -> set[str]:
    modules: set[str] = set()
    for source in files:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        typeCheckingIds = _typeCheckingImportIds(tree)
        for node in ast.walk(tree):
            if id(node) in typeCheckingIds:
                continue
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "qfluentwidgets" or alias.name.startswith("qfluentwidgets."):
                        raise ValueError(
                            f"{source}:{node.lineno}: use 'from qfluentwidgets import ...' instead of 'import {alias.name}'"
                        )
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                module = node.module
                if module != "qfluentwidgets" and not module.startswith("qfluentwidgets."):
                    continue
                exports = packageExports.get(module)
                for alias in node.names:
                    if alias.name == "*":
                        raise ValueError(f"{source}:{node.lineno}: wildcard import from {module} breaks tree-shaking")
                    if exports is not None:
                        target = exports.get(alias.name)
                        if target is not None:
                            modules.add(target)
                            continue
                        candidate = f"{module}.{alias.name}"
                        if candidate in packageExports or importlib.util.find_spec(candidate) is not None:
                            modules.add(candidate)
                            continue
                        raise ValueError(f"{source}:{node.lineno}: unknown qfluentwidgets symbol {module}.{alias.name}")
                    if importlib.util.find_spec(module) is None:
                        raise ValueError(f"{source}:{node.lineno}: unknown qfluentwidgets module {module}")
                    modules.add(module)
    return modules


def findIncludes() -> tuple[list[str], list[str]]:
    from qfluentwidgets._symbols import PACKAGE_EXPORTS

    featureFiles = [path for pack in findPacks() for path in pack.rglob("*.py")]
    appFiles = [REPO / "Ghost-Downloader-3.py", *(REPO / "app").rglob("*.py")]

    featuresDir = REPO / "features"
    internalPackages = {featuresDir.name} | {item.name for item in featuresDir.iterdir() if item.is_dir()}
    ignoredTopLevels = internalPackages | {"qfluentwidgets"}

    # FeaturePack 第三方依赖按导入模块走 --include-module，由 Nuitka 做传递闭包，避免整包带入 tests 等子包
    featureModules = findImports(featureFiles, ignoredTopLevels)
    appModules = findImports(appFiles, ignoredTopLevels)
    qfwModules = findQfwModules([*appFiles, *featureFiles], PACKAGE_EXPORTS)

    packages = sorted(PLATFORM_INCLUDE_PACKAGES.get(sys.platform, []))
    modules = sorted((featureModules - appModules) | set(EXTRA_INCLUDE_MODULES) | qfwModules)
    return packages, modules


def buildArgs() -> list[str]:
    includePackages, includeModules = findIncludes()
    from qfluentwidgets._rc import RCC_PATH as QFW_RCC_PATH

    includeArgs = [
        *[f"--include-package={package}" for package in includePackages],
        *[f"--include-module={module}" for module in includeModules],
        "--report=dist/compilation-report.xml",
    ]

    nuitka = f'"{sys.executable}" -m nuitka'

    dataArgs = [
        '--include-data-files=app/assets/resources.rcc=app/assets/resources.rcc',
        f'--include-data-files="{QFW_RCC_PATH}=qfluentwidgets/_rc/resource.rcc"',
    ]
    excludeArgs = [f"--noinclude-dlls={path}" for path in PLATFORM_EXCLUDED_DLLS[sys.platform]]

    if sys.platform == "win32":
        return [
            nuitka,
            '--standalone',
            '--windows-console-mode=attach',
            '--plugin-enable=pyside6',
            *includeArgs,
            *dataArgs,
            *excludeArgs,
            '--assume-yes-for-downloads',
            '--msvc=latest',
            '--windows-icon-from-ico=app/assets/logo.ico',
            '--include-data-dir=app/assets/file_icons=app/assets/file_icons',
            '--company-name=XiaoYouChR',
            '--product-name="Ghost Downloader"',
            f'--file-version={BUILD_VERSION}',
            f'--product-version={BUILD_VERSION}',
            '--file-description="Ghost Downloader"',
            f'--copyright="Copyright(C) {YEAR} {AUTHOR}"',
            '--output-dir=dist',
            'Ghost-Downloader-3.py',
        ]

    if sys.platform == "darwin":
        return [
            nuitka,
            '--standalone',
            '--plugin-enable=pyside6',
            *includeArgs,
            *dataArgs,
            *excludeArgs,
            '--static-libpython=no',
            "--macos-create-app-bundle",
            "--assume-yes-for-downloads",
            "--macos-app-mode=gui",
            f"--macos-app-version={BUILD_VERSION}",
            "--macos-app-macos-min-version=13.0",
            "--macos-app-icon=app/assets/logo.icns",
            f'--copyright="Copyright(C) {YEAR} {AUTHOR}"',
            '--output-dir=dist',
            'Ghost-Downloader-3.py',
        ]

    return [
        nuitka,
        '--standalone',
        '--plugin-enable=pyside6',
        *includeArgs,
        *dataArgs,
        *excludeArgs,
        '--include-qt-plugins=platforms,platforminputcontexts',
        '--include-module=PySide6.QtDBus',
        '--assume-yes-for-downloads',
        '--linux-icon=app/assets/logo.png',
        '--output-dir=dist',
        'Ghost-Downloader-3.py',
    ]


def findPacks() -> list[Path]:
    featuresDir = REPO / "features"
    if not featuresDir.is_dir():
        raise FileNotFoundError(f"features directory not found: {featuresDir}")

    return sorted(
        (
            item
            for item in featuresDir.iterdir()
            if item.is_dir()
            and item.name not in EXCLUDED_PACKS
            and (item / "manifest.toml").is_file()
        ),
        key=lambda item: item.name,
    )


def copyPacks() -> None:
    packs = findPacks()
    if not packs:
        raise RuntimeError("No feature packs were found to copy.")

    if sys.platform == "darwin":
        targetRoot = Path("dist") / "Ghost-Downloader-3.app" / "Contents" / "MacOS" / "features"
    else:
        targetRoot = Path("dist") / "Ghost-Downloader-3.dist" / "features"

    if not targetRoot.parent.exists():
        raise FileNotFoundError(f"dist directory does not exist: {targetRoot.parent}")

    if targetRoot.exists():
        shutil.rmtree(targetRoot)
    targetRoot.mkdir(parents=True, exist_ok=True)

    ignorePatterns = shutil.ignore_patterns("*.svg", "*.qrc")
    for source in packs:
        shutil.copytree(source, targetRoot / source.name, ignore=ignorePatterns)

    print(f"Copied feature packs to {targetRoot}: {[p.name for p in packs]}")


def patchInfoPlist() -> None:
    appBundle = Path("dist") / "Ghost-Downloader-3.app"
    plistPath = appBundle / "Contents" / "Info.plist"
    resourcesDir = appBundle / "Contents" / "Resources"
    resourcesDir.mkdir(parents=True, exist_ok=True)

    fileIconsDir = REPO / "app" / "assets" / "file_icons"
    documentTypes = []
    for entry in MACOS_DOCUMENT_TYPES:
        shutil.copy(fileIconsDir / f"{entry['icon']}.icns", resourcesDir / f"{entry['icon']}.icns")
        documentTypes.append(
            {
                "CFBundleTypeName": entry["name"],
                "CFBundleTypeRole": "Viewer",
                "CFBundleTypeExtensions": entry["extensions"],
                "CFBundleTypeIconFile": f"{entry['icon']}.icns",
                "LSHandlerRank": "Alternate",
            }
        )

    with open(plistPath, "rb") as f:
        plist = plistlib.load(f)
    plist["CFBundleDocumentTypes"] = documentTypes
    plist["CFBundleIdentifier"] = DESKTOP_ID
    plist["NSDownloadsFolderUsageDescription"] = "Ghost Downloader 需要访问下载文件夹以管理和删除下载的文件。"
    plist["CFBundleURLTypes"] = [{
        "CFBundleURLName": DESKTOP_ID,
        "CFBundleURLSchemes": ["ghostdownloader", "magnet", "ed2k", "ftp", "ftps", "thunder", "flashget", "qqdl"],
    }]
    with open(plistPath, "wb") as f:
        plistlib.dump(plist, f)

    print(f"Patched Info.plist with {len(documentTypes)} document types + URL scheme")


def main() -> int:
    os.chdir(REPO)

    args = buildArgs()
    command = ' '.join(args)

    print(command)
    result = subprocess.run(command, shell=True)
    if result.returncode != 0:
        return result.returncode

    copyPacks()

    if sys.platform == "darwin":
        patchInfoPlist()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
