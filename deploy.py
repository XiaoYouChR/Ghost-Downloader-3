import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from app.supports.config import VERSION, YEAR, AUTHOR, DESKTOP_ID

FEATURES_ROOT = Path("features")
FILE_ICONS_DIR = Path("app/assets/file_icons")
# macOS 文件关联只能构建时烘进 Info.plist; 这份清单镜像各 pack 的 fileTypes(), 改 pack 时同步
MACOS_DOCUMENT_TYPES = [
    {"name": "种子文件", "extensions": ["torrent"], "icon": "torrent"},
    {"name": "M3U8 播放列表", "extensions": ["m3u8", "m3u"], "icon": "m3u8"},
    {"name": "DASH 清单", "extensions": ["mpd"], "icon": "m3u8"},
]
FEATURE_PACK_BLACKLIST = {"jack_yao"}
COMMON_INCLUDE_PACKAGES = [
    "urllib3",
    "qrcode",
    "libtorrent",
    "aioftp"
]
PLATFORM_INCLUDE_PACKAGES = {
    "win32": [
        "winrt",
    ],
}
INCLUDE_MODULES = [
    "app.supports.sysio",
    "app.view.components.edit_task_cards",
    "app.view.components.edit_task_dialog",
    "app.supports.file_association",
    "app.supports.file_open"
]


def build_include_args() -> list[str]:
    include_packages = COMMON_INCLUDE_PACKAGES + PLATFORM_INCLUDE_PACKAGES.get(sys.platform, [])
    return [
        *[f"--include-package={package}" for package in include_packages],
        *[f"--include-module={module}" for module in INCLUDE_MODULES],
    ]


def build_args() -> list[str]:
    nuitka_command = f'"{sys.executable}" -m nuitka'

    if sys.platform == "win32":
        return [
            nuitka_command,
            '--standalone',  # Following all imports is the default for standalone mode and need not be specified.
            '--windows-console-mode=attach',
            '--plugin-enable=pyside6',
            *build_include_args(),
            '--assume-yes-for-downloads',
            '--msvc=latest',              # Use MSVC
            # '--mingw64',  # Use MinGW
            # '--show-memory' ,
            # '--show-progress' ,
            '--windows-icon-from-ico=app/assets/logo.ico',
            # 注册表 DefaultIcon 指向磁盘上的 .ico, 所以图标必须作为实体文件随包发出 (不能只进 qrc)
            '--include-data-dir=app/assets/file_icons=app/assets/file_icons',
            '--company-name=XiaoYouChR',
            '--product-name="Ghost Downloader"',
            f'--file-version={VERSION}',
            f'--product-version={VERSION}',
            '--file-description="Ghost Downloader"',
            f'--copyright="Copyright(C) {YEAR} {AUTHOR}"',
            '--output-dir=dist',
            'Ghost-Downloader-3.py',
        ]

    if sys.platform == "darwin":
        return [
            nuitka_command,
            '--standalone',
            '--plugin-enable=pyside6',
            *build_include_args(),
            # '--show-memory',
            # '--show-progress',
            '--static-libpython=no',
            "--macos-create-app-bundle",
            "--assume-yes-for-downloads",
            "--macos-app-mode=gui",
            f"--macos-app-version={VERSION}",
            "--macos-app-icon=app/assets/logo.icns",
            f'--copyright="Copyright(C) {YEAR} {AUTHOR}"',
            '--output-dir=dist',
            'Ghost-Downloader-3.py',
        ]

    return [
        nuitka_command,
        '--standalone',
        '--plugin-enable=pyside6',
        *build_include_args(),
        '--include-qt-plugins=platforms',
        # 文件关联的 D-Bus 激活接收器懒加载 QtDBus, 显式带上确保进包
        '--include-module=PySide6.QtDBus',
        '--assume-yes-for-downloads',
        # '--show-memory',
        # '--show-progress',
        '--linux-icon=app/assets/logo.png',
        '--output-dir=dist',
        'Ghost-Downloader-3.py',
    ]


def get_feature_pack_sources() -> list[Path]:
    if not FEATURES_ROOT.is_dir():
        raise FileNotFoundError(f"FeaturePacks source directory not found: {FEATURES_ROOT}")

    return sorted(
        (
            item
            for item in FEATURES_ROOT.iterdir()
            if item.is_dir()
            and item.name not in FEATURE_PACK_BLACKLIST
            and (item / "manifest.toml").is_file()
        ),
        key=lambda item: item.name,
    )


def get_feature_pack_target_root() -> Path:
    if sys.platform == "darwin":
        return Path("dist") / "Ghost-Downloader-3.app" / "Contents" / "MacOS" / "features"
    return Path("dist") / "Ghost-Downloader-3.dist" / "features"


def copy_feature_packs() -> None:
    feature_pack_sources = get_feature_pack_sources()
    if not feature_pack_sources:
        raise RuntimeError("No feature packs were found to copy.")

    target_root = get_feature_pack_target_root()
    if not target_root.parent.exists():
        raise FileNotFoundError(f"FeaturePacks target directory does not exist: {target_root.parent}")

    if target_root.exists():
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True, exist_ok=True)

    for source in feature_pack_sources:
        shutil.copytree(source, target_root / source.name)

    print(f"Copied FeaturePacks to {target_root}: {[source.name for source in feature_pack_sources]}")


def patch_macos_app() -> None:
    appBundle = Path("dist") / "Ghost-Downloader-3.app"
    plistPath = appBundle / "Contents" / "Info.plist"
    resourcesDir = appBundle / "Contents" / "Resources"
    resourcesDir.mkdir(parents=True, exist_ok=True)

    documentTypes = []
    for entry in MACOS_DOCUMENT_TYPES:
        shutil.copy(FILE_ICONS_DIR / f"{entry['icon']}.icns", resourcesDir / f"{entry['icon']}.icns")
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
    # LaunchServices 按 bundle id 注册文档类型, 固定成反向域名 id
    plist["CFBundleIdentifier"] = DESKTOP_ID
    with open(plistPath, "wb") as f:
        plistlib.dump(plist, f)

    print(f"Patched Info.plist with {len(documentTypes)} document types")


def main() -> int:
    args = build_args()
    command = ' '.join(args)

    print(command)
    result = subprocess.run(command, shell=True)
    if result.returncode != 0:
        return result.returncode

    copy_feature_packs()

    if sys.platform == "darwin":
        patch_macos_app()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
