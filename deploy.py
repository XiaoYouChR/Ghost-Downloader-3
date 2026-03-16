import shutil
import subprocess
import sys
from pathlib import Path

from app.supports.config import VERSION, YEAR, AUTHOR

FEATURES_ROOT = Path("features")
FEATURE_PACK_BLACKLIST = {"jack_yao"}
COMMON_INCLUDE_PACKAGES = [
    "urllib3",
    "qrcode",
    "libtorrent"
]
PLATFORM_INCLUDE_PACKAGES = {
    "win32": [
        "winrt",
    ],
}
INCLUDE_MODULES = [
    "app.supports.sysio",
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
            '--windows-console-mode=disable',
            '--plugin-enable=pyside6',
            *build_include_args(),
            '--assume-yes-for-downloads',
            '--msvc=latest',              # Use MSVC
            # '--mingw64',  # Use MinGW
            # '--show-memory' ,
            # '--show-progress' ,
            '--windows-icon-from-ico=app/assets/logo.ico',
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
            "--assume-yes-for-download",
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


def main() -> int:
    args = build_args()
    command = ' '.join(args)

    print(command)
    result = subprocess.run(command, shell=True)
    if result.returncode != 0:
        return result.returncode

    copy_feature_packs()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
