#!/usr/bin/env python3
"""Build the libtorrent win_arm64 wheel from the upstream tag.

PyPI has no win_arm64 wheel. OpenSSL follows the upstream tag's own
cibuildwheel config, so the wheel matches the x64 one on PyPI. Boost uses the
latest release instead of the upstream one, because the windows-11-arm runner
only has Visual Studio 2026, and b2 knows it since Boost 1.91.

Usage:
    python scripts/build_libtorrent_wheel.py <libtorrent version> <python version> <output folder>
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

UPSTREAM = "https://github.com/arvidn/libtorrent.git"
BOOST = "https://github.com/boostorg/boost.git"
OPENSSL_FOLDER = Path(r"C:\Program Files\OpenSSL")


def run(*args: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, cwd=cwd, env=env, check=True)


def fetchLatestBoostVersion() -> str:
    tags = subprocess.run(("git", "ls-remote", "--tags", "--refs", BOOST, "boost-*"),
                          capture_output=True, text=True, check=True).stdout
    versions = re.findall(r"refs/tags/boost-(\d+\.\d+\.\d+)$", tags, re.MULTILINE)
    return max(versions, key=lambda v: tuple(map(int, v.split("."))))


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
        "CIBW_BEFORE_ALL_WINDOWS": f"bash -c './tools/cibuildwheel/setup_boost.sh {fetchLatestBoostVersion()} $BOOST_ROOT'",
        "CIBW_TEST_SKIP": "*",
    }
    run("uvx", "cibuildwheel", "--output-dir", str(Path(outputFolder).resolve()), cwd=source, env=env)


if __name__ == "__main__":
    main()
