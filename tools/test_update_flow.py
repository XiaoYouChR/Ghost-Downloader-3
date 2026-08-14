"""End-to-end test for the update flow with a local HTTP server.

Exercises: _fetchVersions (raw URL) → _check → _downloadPack (raw URL) →
_applyPack → installPendingPacks. Also verifies buildAssetUrl.

Usage:
    .venv/bin/python3 tools/test_update_flow.py
"""
import asyncio
import hashlib
import json
import shutil
import sys
import threading
import zipfile
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WORK_DIR = Path(__file__).resolve().parent / "_test_update"
SERVE_DIR = WORK_DIR / "serve"
FAKE_EXEC_DIR = WORK_DIR / "exec"
FAKE_STAGING = WORK_DIR / "staging"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def setup_server_content() -> str:
    SERVE_DIR.mkdir(parents=True, exist_ok=True)

    pack_dir = SERVE_DIR / "dist" / "packs"
    pack_dir.mkdir(parents=True, exist_ok=True)
    pack_zip = pack_dir / "test_pack.zip"
    with zipfile.ZipFile(pack_zip, "w") as zf:
        zf.writestr("manifest.toml", '[pack]\nentry = "pack.py"\nclass = "TestPack"\nversion = "2.0.0"\ngdMinVersion = "4.2.0"\n')
        zf.writestr("pack.py", "class TestPack: pass\n")

    pack_sha = sha256(pack_zip)
    versions = {
        "app": {
            "version": "99.0.0",
            "patches": {},
            "full": {},
        },
        "packs": {
            "test_pack": {
                "version": "2.0.0",
                "file": "test_pack.zip",
                "sha256": pack_sha,
                "gdMinVersion": "4.2.0",
            }
        },
    }
    (SERVE_DIR / "versions.json").write_text(json.dumps(versions, indent=2))
    return pack_sha


def setup_local_pack():
    features = FAKE_EXEC_DIR / "features"
    pack_dir = features / "test_pack"
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "manifest.toml").write_text(
        '[pack]\nentry = "pack.py"\nclass = "TestPack"\nversion = "1.0.0"\ngdMinVersion = "4.2.0"\n'
    )
    (pack_dir / "pack.py").write_text("class TestPack: pass\n")


def start_server() -> tuple[HTTPServer, int]:
    import os
    os.chdir(SERVE_DIR)

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), QuietHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def cleanup():
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)


def main():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    cleanup()
    expected_sha = setup_server_content()
    setup_local_pack()
    server, port = start_server()
    base = f"http://127.0.0.1:{port}"
    print(f"Local server: {base}")

    import app.services.update_service as us

    original_sources = us.SOURCES.copy()
    original_staging = us.STAGING_DIR
    original_exec_dir = us.executableDir

    us.SOURCES["github"] = {
        "versions": f"{base}/versions.json",
        "raw": base,
        "release": f"{base}/releases",
    }
    us.STAGING_DIR = FAKE_STAGING
    us.executableDir = FAKE_EXEC_DIR

    original_fetchFile = us.fetchFile
    async def mock_fetchFile(url, outputPath, onProgress=None):
        import urllib.request
        urllib.request.urlretrieve(url, str(outputPath))
        if onProgress:
            onProgress(100)
    us.fetchFile = mock_fetchFile

    passed = 0
    failed = 0

    def check(name, condition):
        nonlocal passed, failed
        if condition:
            print(f"  ✓ {name}")
            passed += 1
        else:
            print(f"  ✗ {name}")
            failed += 1

    signals: list = []

    from app.services.update_service import UpdateService, UpdateState, installPendingPacks, buildAssetUrl

    class FakeCoroutineRunner:
        def submit(self, coro, **kwargs):
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(coro)
            finally:
                loop.close()

    try:
        svc = UpdateService(FakeCoroutineRunner())
        svc.changed.connect(lambda info: signals.append(info))

        # ── Test 1: _fetchVersions ──
        print("\n[Test 1] _fetchVersions via raw URL")
        loop = asyncio.new_event_loop()
        data = loop.run_until_complete(svc._fetchVersions())
        loop.close()
        check("returns dict", isinstance(data, dict))
        check("app.version = 99.0.0", data.get("app", {}).get("version") == "99.0.0")
        check("packs.test_pack exists", "test_pack" in data.get("packs", {}))
        check("source set to github", svc._source == "github")

        # ── Test 2: _check ──
        print("\n[Test 2] _check detects app + pack updates")
        signals.clear()
        svc._source = ""
        loop = asyncio.new_event_loop()
        loop.run_until_complete(svc._check())
        loop.close()

        states = [(s.targetId, s.state) for s in signals]
        check("app CHECKING emitted", ("app", UpdateState.CHECKING) in states)
        check("app AVAILABLE emitted", ("app", UpdateState.AVAILABLE) in states)
        check("test_pack AVAILABLE emitted", ("test_pack", UpdateState.AVAILABLE) in states)

        app_info = next((s for s in signals if s.targetId == "app" and s.state == UpdateState.AVAILABLE), None)
        check("app latestVersion=99.0.0", app_info and app_info.latestVersion == "99.0.0")

        pack_info = next((s for s in signals if s.targetId == "test_pack" and s.state == UpdateState.AVAILABLE), None)
        check("pack latestVersion=2.0.0", pack_info and pack_info.latestVersion == "2.0.0")
        check("pack currentVersion=1.0.0", pack_info and pack_info.currentVersion == "1.0.0")

        # ── Test 3: _downloadPack ──
        print("\n[Test 3] _downloadPack via raw URL")
        signals.clear()
        loop = asyncio.new_event_loop()
        loop.run_until_complete(svc._download("test_pack"))
        loop.close()

        dl_states = [(s.targetId, s.state) for s in signals]
        check("DOWNLOADING emitted", ("test_pack", UpdateState.DOWNLOADING) in dl_states)
        check("READY emitted", ("test_pack", UpdateState.READY) in dl_states)
        check("FAILED not emitted", ("test_pack", UpdateState.FAILED) not in dl_states)

        zip_path = FAKE_STAGING / "test_pack.zip"
        check("zip downloaded", zip_path.is_file())
        if zip_path.is_file():
            check("sha256 matches", sha256(zip_path) == expected_sha)

        # ── Test 4: _applyPack ──
        print("\n[Test 4] _applyPack stages to _pending")
        svc._applyPack("test_pack")
        pending = FAKE_EXEC_DIR / "features" / "test_pack_pending"
        check("pending dir created", pending.is_dir())
        check("manifest.toml in pending", (pending / "manifest.toml").is_file())
        check("zip removed after apply", not zip_path.is_file())

        # ── Test 5: installPendingPacks ──
        print("\n[Test 5] installPendingPacks swaps pending → final")
        features_dir = FAKE_EXEC_DIR / "features"
        installPendingPacks(features_dir)
        check("pending dir gone", not pending.exists())
        check("test_pack dir exists", (features_dir / "test_pack").is_dir())

        import tomllib
        with open(features_dir / "test_pack" / "manifest.toml", "rb") as f:
            manifest = tomllib.load(f)
        check("version updated to 2.0.0", manifest.get("pack", {}).get("version") == "2.0.0")

        # ── Test 6: buildAssetUrl ──
        print("\n[Test 6] buildAssetUrl uses SOURCES table")
        url = buildAssetUrl("github", "4.3.0", "Ghost-Downloader-v4.3.0-Windows-x86_64.zip")
        check("URL correct", url == f"{base}/releases/v4.3.0/Ghost-Downloader-v4.3.0-Windows-x86_64.zip")

        # ── Summary ──
        print(f"\n{'='*40}")
        print(f"Passed: {passed}  Failed: {failed}")
        if failed:
            print("SOME TESTS FAILED")
            sys.exit(1)
        else:
            print("ALL TESTS PASSED")

    finally:
        us.SOURCES = original_sources
        us.STAGING_DIR = original_staging
        us.executableDir = original_exec_dir
        us.fetchFile = original_fetchFile
        server.shutdown()
        cleanup()


if __name__ == "__main__":
    main()
