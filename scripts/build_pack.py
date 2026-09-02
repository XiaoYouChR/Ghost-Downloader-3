#!/usr/bin/env python3
"""Build pack zips and update versions.json.

Usage:
    python scripts/build_pack.py http_pack [bili_pack ...]
    python scripts/build_pack.py --all
"""
import argparse
import hashlib
import json
import sys
import tomllib
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FEATURES_DIR = REPO / "features"
DIST_PACKS = REPO / "dist" / "packs"
VERSIONS_FILE = REPO / "versions.json"
EXCLUDED_PACKS = {"jack_yao"}
IGNORE_SUFFIXES = {".svg", ".qrc", ".pyc"}


def buildPackZip(packId: str) -> Path:
    packDir = FEATURES_DIR / packId
    if not packDir.is_dir():
        raise FileNotFoundError(f"Pack not found: {packDir}")
    if not (packDir / "manifest.toml").is_file():
        raise FileNotFoundError(f"No manifest.toml in {packDir}")

    DIST_PACKS.mkdir(parents=True, exist_ok=True)
    zipPath = DIST_PACKS / f"{packId}.zip"

    with zipfile.ZipFile(zipPath, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(packDir.rglob("*")):
            if not file.is_file():
                continue
            if file.suffix in IGNORE_SUFFIXES:
                continue
            if any(p.name == "__pycache__" for p in file.relative_to(packDir).parents):
                continue
            zf.write(file, file.relative_to(packDir))

    return zipPath


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def readManifest(packId: str) -> dict:
    with open(FEATURES_DIR / packId / "manifest.toml", "rb") as f:
        return tomllib.load(f).get("pack", {})


def allPackIds() -> list[str]:
    return [
        d.name for d in sorted(FEATURES_DIR.iterdir())
        if d.is_dir() and d.name not in EXCLUDED_PACKS and (d / "manifest.toml").is_file()
    ]


def main():
    parser = argparse.ArgumentParser(description="Build pack zips and update versions.json")
    parser.add_argument("packs", nargs="*", help="Pack IDs to build")
    parser.add_argument("--all", action="store_true", help="Build all packs")
    args = parser.parse_args()

    if args.all:
        packIds = allPackIds()
    elif args.packs:
        packIds = args.packs
    else:
        parser.error("Specify pack IDs or --all")
        return

    versions = json.loads(VERSIONS_FILE.read_text()) if VERSIONS_FILE.is_file() else {"app": {}, "packs": {}}
    packs = versions.setdefault("packs", {})

    for packId in packIds:
        print(f"Building {packId}...")
        zipPath = buildPackZip(packId)
        manifest = readManifest(packId)

        entry = {
            "version": manifest.get("version", ""),
            "file": f"{packId}.zip",
            "sha256": sha256(zipPath),
        }
        gdMin = manifest.get("gdMinVersion", "")
        if gdMin:
            entry["gdMinVersion"] = gdMin
        packs[packId] = entry

        print(f"  {zipPath.name}  {zipPath.stat().st_size} bytes  sha256={entry['sha256'][:12]}...")

    VERSIONS_FILE.write_text(json.dumps(versions, indent=2, ensure_ascii=False) + "\n")
    print(f"\nUpdated {VERSIONS_FILE}")


if __name__ == "__main__":
    main()
