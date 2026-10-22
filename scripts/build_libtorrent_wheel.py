#!/usr/bin/env python3
"""Build the libtorrent win_arm64 wheel from the upstream tag.

PyPI has no win_arm64 wheel. Boost and OpenSSL versions follow the upstream
tag's own cibuildwheel config, so the wheel matches the x64 one on PyPI.

Usage:
    python scripts/build_libtorrent_wheel.py <libtorrent version> <python version> <output folder>
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

UPSTREAM = "https://github.com/arvidn/libtorrent.git"
OPENSSL_FOLDER = Path(r"C:\Program Files\OpenSSL")


def run(*args: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, cwd=cwd, env=env, check=True)


def main() -> None:
    version, pythonVersion, outputFolder = sys.argv[1:]
    source = Path(os.environ["RUNNER_TEMP"]) / "libtorrent"

    run("git", "clone", "--depth=1", f"--branch=v{version}",
        "--recurse-submodules", "--shallow-submodules", UPSTREAM, str(source))
    run("git", "apply", "../patch-libdatachannel-32bit-builds.patch", cwd=source / "deps" / "libdatachannel")

    run("vcpkg", "install", "--triplet=arm64-windows-static", cwd=source / "tools")
    # 上游 pyproject 的 B2_EXTRA_ARGS 固定从这里找 OpenSSL
    shutil.rmtree(OPENSSL_FOLDER, ignore_errors=True)
    run("cmd", "/c", "mklink", "/J", str(OPENSSL_FOLDER),
        str(source / "tools" / "vcpkg_installed" / "arm64-windows-static"))

    env = os.environ | {
        "CIBW_BUILD": f"cp{pythonVersion.replace('.', '')}-win_arm64",
        "CIBW_ARCHS_WINDOWS": "ARM64",
        # 上游只给 win32、win_amd64 配了装 Boost 的 before-all
        "CIBW_BEFORE_ALL_WINDOWS": "bash -c './tools/cibuildwheel/setup_boost.sh $BOOST_VERSION $BOOST_ROOT'",
        "CIBW_TEST_SKIP": "*",
    }
    run("uvx", "cibuildwheel", "--output-dir", str(Path(outputFolder).resolve()), str(source), env=env)


if __name__ == "__main__":
    main()
