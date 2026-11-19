from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

FCITX5_QT_REPO = "https://github.com/fcitx/fcitx5-qt.git"
PLUGIN_FILENAME = "libfcitx5platforminputcontextplugin.so"

AQT_TARGETS: dict[str, tuple[str, str]] = {
    "x86_64": ("linux", "linux_gcc_64"),
    "aarch64": ("linux_arm64", "linux_gcc_arm64"),
    "arm64": ("linux_arm64", "linux_gcc_arm64"),
}


def fetchLatestTag(repoUrl: str = FCITX5_QT_REPO) -> str:
    result = subprocess.run(
        ["git", "ls-remote", "--tags", repoUrl],
        check=True,
        capture_output=True,
        text=True,
    )
    tags = re.findall(r"\trefs/tags/(\d+\.\d+\.\d+)$", result.stdout, re.MULTILINE)
    if not tags:
        raise RuntimeError(f"No stable semver tag found in {repoUrl}")
    return max(tags, key=lambda tag: tuple(int(part) for part in tag.split(".")))


def compilePlugin(qtVersion: str, arch: str, tag: str, outputFolder: Path) -> Path:
    targetInfo = AQT_TARGETS.get(arch.lower())
    if targetInfo is None:
        raise ValueError(f"Unsupported Linux architecture: {arch}")
    host, target = targetInfo

    with tempfile.TemporaryDirectory(prefix="fcitx5-qt-build-") as tempPath:
        workFolder = Path(tempPath)
        qtFolder = workFolder / "qt"
        sourceFolder = workFolder / "fcitx5-qt"
        buildFolder = workFolder / "build"

        # Qt6 官方 Linux 构建链接自带的 icu，缺它时 qmake/moc 无法启动
        subprocess.run(
            [
                "uvx", "--from", "aqtinstall", "aqt", "install-qt",
                host, "desktop", qtVersion, target,
                "--archives", "qtbase", "qtwayland", "icu",
                "-O", str(qtFolder),
            ],
            check=True,
        )

        versionFolder = qtFolder / qtVersion
        qtPrefix = next(
            (folder for folder in sorted(versionFolder.iterdir()) if (folder / "lib" / "cmake" / "Qt6").is_dir()),
            None,
        )
        if qtPrefix is None:
            raise FileNotFoundError(f"Qt6 CMake config folder not found under: {versionFolder}")

        subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", tag, FCITX5_QT_REPO, str(sourceFolder)],
            check=True,
        )
        subprocess.run(
            [
                "cmake", "-S", str(sourceFolder), "-B", str(buildFolder), "-G", "Ninja",
                "-DCMAKE_BUILD_TYPE=Release",
                f"-DCMAKE_PREFIX_PATH={qtPrefix}",
                "-DBUILD_ONLY_PLUGIN=ON",
                "-DENABLE_QT4=OFF",
                "-DENABLE_QT5=OFF",
                "-DENABLE_QT6=ON",
                "-DENABLE_X11=ON",
                "-DWITH_FCITX_PLUGIN_NAME=ON",
                "-DENABLE_QT6_WAYLAND_WORKAROUND=ON",
            ],
            check=True,
        )
        subprocess.run(
            [
                "cmake", "--build", str(buildFolder),
                "--target", "fcitx5platforminputcontextplugin-qt6",
                f"-j{os.cpu_count() or 2}",
            ],
            check=True,
        )

        builtPlugin = buildFolder / "qt6" / "platforminputcontext" / PLUGIN_FILENAME
        outputFolder.mkdir(parents=True, exist_ok=True)
        targetPlugin = outputFolder / PLUGIN_FILENAME
        shutil.copy2(builtPlugin, targetPlugin)

    # 与 PySide6 自带 platforminputcontexts 插件保持一致，避免 Nuitka 追踪到临时 Qt 目录
    subprocess.run(["patchelf", "--set-rpath", "$ORIGIN/../../lib", str(targetPlugin)], check=True)
    return targetPlugin


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile fcitx5-qt Qt6 input context plugin matching PySide6.")
    parser.add_argument("--print-tag", action="store_true", help="Print the latest stable fcitx5-qt tag and exit.")
    parser.add_argument("--qt-version", default=None, help="Target Qt6 version (defaults to installed PySide6 version).")
    parser.add_argument("--arch", default=platform.machine(), help="Target Linux architecture (x86_64 or arm64).")
    parser.add_argument("--tag", default=None, help="fcitx5-qt git tag (defaults to latest stable tag).")
    parser.add_argument("--output-dir", type=Path, default=None, help="Folder to write the compiled .so file.")
    args = parser.parse_args()

    if args.print_tag:
        print(fetchLatestTag())
        return 0

    if args.output_dir is None:
        parser.error("--output-dir is required unless --print-tag is specified")

    qtVersion = args.qt_version
    if qtVersion is None:
        import PySide6
        qtVersion = PySide6.__version__

    plugin = compilePlugin(qtVersion, args.arch, args.tag or fetchLatestTag(), args.output_dir)
    print(f"Compiled {plugin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
