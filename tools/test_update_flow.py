"""End-to-end test for the update flow with a local HTTP server.

Exercises: _fetchVersions → _check → _downloadPack → _downloadApp (full + delta) →
_applyPack → apply → installPendingPacks. Also verifies sha256 failure, gdMinVersion
skip, and buildAssetUrl.

Usage:
    .venv/bin/python3 tools/test_update_flow.py       (macOS/Linux)
    .venv\\Scripts\\python.exe tools/test_update_flow.py  (Windows)
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
if sys.platform == "darwin":
    FAKE_EXEC_DIR = WORK_DIR / "GD.app" / "Contents" / "MacOS"
else:
    FAKE_EXEC_DIR = WORK_DIR / "exec"
FAKE_STAGING = WORK_DIR / "staging"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def setup_server_content() -> dict:
    from app.config.constants import VERSION
    from app.services.update_service import buildPlatformKey

    SERVE_DIR.mkdir(parents=True, exist_ok=True)
    platformKey = buildPlatformKey()

    pack_dir = SERVE_DIR / "dist" / "packs"
    pack_dir.mkdir(parents=True, exist_ok=True)

    pack_zip = pack_dir / "test_pack.zip"
    with zipfile.ZipFile(pack_zip, "w") as zf:
        zf.writestr("manifest.toml", '[pack]\nentry = "pack.py"\nclass = "TestPack"\nversion = "2.0.0"\ngdMinVersion = "4.2.0"\n')
        zf.writestr("pack.py", "class TestPack: pass\n")
    pack_sha = sha256(pack_zip)

    bad_pack_zip = pack_dir / "bad_pack.zip"
    with zipfile.ZipFile(bad_pack_zip, "w") as zf:
        zf.writestr("manifest.toml", '[pack]\nentry = "pack.py"\nclass = "BadPack"\nversion = "2.0.0"\n')

    release_dir = SERVE_DIR / "releases" / "v99.0.0"
    release_dir.mkdir(parents=True, exist_ok=True)
    app_filename = f"GD-v99.0.0-{platformKey}.zip"
    app_zip = release_dir / app_filename
    with zipfile.ZipFile(app_zip, "w") as zf:
        zf.writestr("ghost_downloader", "fake binary")
    app_sha = sha256(app_zip)

    patch_filename = f"GD-v99.0.0-{platformKey}.hdiff"
    patch_file = release_dir / patch_filename
    patch_file.write_bytes(b"fake delta patch content")
    patch_sha = sha256(patch_file)

    versions = {
        "app": {
            "version": "99.0.0",
            "patches": {
                platformKey: {
                    "from": VERSION,
                    "file": patch_filename,
                    "sha256": patch_sha,
                }
            },
            "full": {
                platformKey: {
                    "file": app_filename,
                    "sha256": app_sha,
                }
            },
        },
        "packs": {
            "test_pack": {
                "version": "2.0.0",
                "file": "test_pack.zip",
                "sha256": pack_sha,
                "gdMinVersion": "4.2.0",
            },
            "bad_pack": {
                "version": "2.0.0",
                "file": "bad_pack.zip",
                "sha256": "0" * 64,
                "gdMinVersion": "4.2.0",
            },
            "future_pack": {
                "version": "2.0.0",
                "file": "future_pack.zip",
                "sha256": "doesnt_matter",
                "gdMinVersion": "999.0.0",
            },
        },
    }
    (SERVE_DIR / "versions.json").write_text(json.dumps(versions, indent=2))

    return {"pack_sha": pack_sha, "app_sha": app_sha, "patch_sha": patch_sha}


def setup_local_packs():
    features = FAKE_EXEC_DIR / "features"

    pack_dir = features / "test_pack"
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "manifest.toml").write_text(
        '[pack]\nentry = "pack.py"\nclass = "TestPack"\nversion = "1.0.0"\ngdMinVersion = "4.2.0"\n'
    )
    (pack_dir / "pack.py").write_text("class TestPack: pass\n")

    future_dir = features / "future_pack"
    future_dir.mkdir(parents=True, exist_ok=True)
    (future_dir / "manifest.toml").write_text(
        '[pack]\nentry = "pack.py"\nclass = "FuturePack"\nversion = "1.0.0"\ngdMinVersion = "4.2.0"\n'
    )
    (future_dir / "pack.py").write_text("class FuturePack: pass\n")


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
    hashes = setup_server_content()
    setup_local_packs()
    server, port = start_server()
    base = f"http://127.0.0.1:{port}"
    print(f"Local server: {base}")

    import app.services.update_service as us
    import app.sources as sources

    original_sources = sources.SOURCES.copy()
    original_order = sources.SOURCE_ORDER
    original_staging = us.STAGING_DIR
    original_exec_dir = us.executableDir
    original_fetchFile = us.fetchFile
    original_extractZip = us.extractZip
    original_extractDmg = us.extractDmg
    original_extractTarXz = us.extractTarXz

    sources.SOURCES["github"] = sources.SourceEndpoints(
        api=f"http://127.0.0.1:{port}/api",
        download=f"http://127.0.0.1:{port}",
        raw=f"http://127.0.0.1:{port}",
        rawInfix="/",
    )
    sources.SOURCE_ORDER = ("github",)
    us.STAGING_DIR = FAKE_STAGING
    us.executableDir = FAKE_EXEC_DIR

    async def mock_fetchFile(url, outputPath, onProgress=None):
        import urllib.request
        urllib.request.urlretrieve(url, str(outputPath))
        if onProgress:
            onProgress(100)
    us.fetchFile = mock_fetchFile

    extract_calls = []

    def mock_extractZip(archivePath, targetDir):
        extract_calls.append(("zip", archivePath, targetDir))
        targetDir.mkdir(parents=True, exist_ok=True)

    async def mock_extractDmg(dmgPath, targetDir):
        extract_calls.append(("dmg", dmgPath, targetDir))
        targetDir.mkdir(parents=True, exist_ok=True)

    def mock_extractTarXz(archivePath, targetDir):
        extract_calls.append(("tarxz", archivePath, targetDir))
        targetDir.mkdir(parents=True, exist_ok=True)

    us.extractZip = mock_extractZip
    us.extractDmg = mock_extractDmg
    us.extractTarXz = mock_extractTarXz

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

    from app.services.update_service import (
        UpdateService, UpdateState, installPendingPacks,
        buildPlatformKey,
    )
    from app.sources import buildDownloadUrl
    from app.update import APP_REPO

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
            check("sha256 matches", sha256(zip_path) == hashes["pack_sha"])

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

        # ── Test 6: buildDownloadUrl ──
        print("\n[Test 6] buildDownloadUrl uses sources module")
        url = buildDownloadUrl(APP_REPO, "v4.3.0", "Ghost-Downloader-v4.3.0-Windows-x86_64.zip", source="github")
        check("URL contains repo and version", f"{APP_REPO}/releases/download/v4.3.0/" in url)

        # ── Test 7: _downloadApp full release ──
        print("\n[Test 7] _downloadApp full release")
        saved_patches = svc._versionsData["app"]["patches"]
        svc._versionsData["app"]["patches"] = {}
        svc._emit("app", UpdateState.AVAILABLE, latestVersion="99.0.0")
        signals.clear()
        extract_calls.clear()

        loop = asyncio.new_event_loop()
        loop.run_until_complete(svc._download("app"))
        loop.close()

        dl_states = [(s.targetId, s.state) for s in signals]
        check("DOWNLOADING emitted", ("app", UpdateState.DOWNLOADING) in dl_states)
        check("READY emitted", ("app", UpdateState.READY) in dl_states)
        check("FAILED not emitted", ("app", UpdateState.FAILED) not in dl_states)
        check("extract called once", len(extract_calls) == 1)

        if sys.platform == "darwin":
            appDir = FAKE_EXEC_DIR.parent.parent
        else:
            appDir = FAKE_EXEC_DIR
        newDir = appDir.parent / f"{appDir.name}_new"
        check("newDir created by extract", newDir.is_dir())

        archiveName = svc._versionsData["app"]["full"][buildPlatformKey()]["file"]
        check("archive cleaned up", not (FAKE_STAGING / archiveName).is_file())

        if newDir.exists():
            shutil.rmtree(newDir)
        svc._versionsData["app"]["patches"] = saved_patches

        # ── Test 8: _downloadApp delta patch ──
        print("\n[Test 8] _downloadApp delta patch")
        svc._emit("app", UpdateState.AVAILABLE, latestVersion="99.0.0")
        signals.clear()

        loop = asyncio.new_event_loop()
        loop.run_until_complete(svc._download("app"))
        loop.close()

        dl_states = [(s.targetId, s.state) for s in signals]
        check("DOWNLOADING emitted", ("app", UpdateState.DOWNLOADING) in dl_states)
        check("READY emitted", ("app", UpdateState.READY) in dl_states)
        check("FAILED not emitted", ("app", UpdateState.FAILED) not in dl_states)

        patch_path = FAKE_STAGING / "patch.hdiff"
        check("patch.hdiff downloaded", patch_path.is_file())
        if patch_path.is_file():
            check("patch sha256 matches", sha256(patch_path) == hashes["patch_sha"])

        # ── Test 9: sha256 failure ──
        print("\n[Test 9] sha256 failure → FAILED")
        svc._emit("bad_pack", UpdateState.AVAILABLE,
                   label="bad_pack 2.0.0", latestVersion="2.0.0")
        signals.clear()

        loop = asyncio.new_event_loop()
        loop.run_until_complete(svc._download("bad_pack"))
        loop.close()

        dl_states = [(s.targetId, s.state) for s in signals]
        check("DOWNLOADING emitted", ("bad_pack", UpdateState.DOWNLOADING) in dl_states)
        check("FAILED emitted", ("bad_pack", UpdateState.FAILED) in dl_states)
        check("READY not emitted", ("bad_pack", UpdateState.READY) not in dl_states)
        check("zip cleaned up", not (FAKE_STAGING / "bad_pack.zip").is_file())

        fail_info = next(
            (s for s in signals if s.targetId == "bad_pack" and s.state == UpdateState.FAILED),
            None,
        )
        check("error is 校验失败", fail_info and fail_info.error == "校验失败")

        # ── Test 10: gdMinVersion skip ──
        print("\n[Test 10] gdMinVersion skip")
        signals.clear()
        svc._source = ""
        loop = asyncio.new_event_loop()
        loop.run_until_complete(svc._check())
        loop.close()

        states = [(s.targetId, s.state) for s in signals]
        check("future_pack NOT AVAILABLE", ("future_pack", UpdateState.AVAILABLE) not in states)
        check("app still detected", ("app", UpdateState.AVAILABLE) in states)

        # ── Test 11: apply() orchestration ──
        print("\n[Test 11] apply() orchestration")
        FAKE_STAGING.mkdir(parents=True, exist_ok=True)
        apply_zip = FAKE_STAGING / "test_pack.zip"
        with zipfile.ZipFile(apply_zip, "w") as zf:
            zf.writestr("manifest.toml",
                         '[pack]\nentry = "pack.py"\nclass = "TestPack"\nversion = "3.0.0"\n')

        svc._emit("app", UpdateState.READY, latestVersion="99.0.0")
        svc.apply()

        apply_pending = FAKE_EXEC_DIR / "features" / "test_pack_pending"
        check("_applyPack ran: pending dir created", apply_pending.is_dir())
        check("zip consumed", not apply_zip.is_file())

        # ── Summary ──
        print(f"\n{'='*40}")
        print(f"Passed: {passed}  Failed: {failed}")
        if failed:
            print("SOME TESTS FAILED")
            sys.exit(1)
        else:
            print("ALL TESTS PASSED")

    finally:
        sources.SOURCES.update(original_sources)
        sources.SOURCE_ORDER = original_order
        us.STAGING_DIR = original_staging
        us.executableDir = original_exec_dir
        us.fetchFile = original_fetchFile
        us.extractZip = original_extractZip
        us.extractDmg = original_extractDmg
        us.extractTarXz = original_extractTarXz
        server.shutdown()
        cleanup()


if __name__ == "__main__":
    main()
