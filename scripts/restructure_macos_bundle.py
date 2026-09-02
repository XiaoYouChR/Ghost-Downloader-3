"""Move everything except the main binary from Contents/MacOS/ to Contents/Resources/,
leaving relative symlinks behind. This makes the bundle pass Apple notarization."""

import os
import plistlib
import shutil
import sys
from pathlib import Path


def restructure(appBundle: Path) -> None:
    contentsDir = appBundle / "Contents"
    macosDir = contentsDir / "MacOS"
    resourcesDir = contentsDir / "Resources"

    with open(contentsDir / "Info.plist", "rb") as f:
        mainExecutable = plistlib.load(f)["CFBundleExecutable"]

    for entry in sorted(macosDir.iterdir()):
        if entry.name == mainExecutable:
            continue

        dest = resourcesDir / entry.name
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()

        shutil.move(str(entry), str(dest))
        entry.symlink_to(os.path.relpath(dest, macosDir))
        print(f"  {entry.name} → Resources/{entry.name}")

    # Match updater.c:restructureBundle() — symlink Resources entries not yet in MacOS.
    for entry in sorted(resourcesDir.iterdir()):
        if entry.name.startswith("."):
            continue
        link = macosDir / entry.name
        if not link.exists() and not link.is_symlink():
            link.symlink_to(os.path.relpath(entry, macosDir))
            print(f"  {entry.name} → Resources/{entry.name} (resources-only)")


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <path/to/App.app>", file=sys.stderr)
        return 1

    appBundle = Path(sys.argv[1])
    if not (appBundle / "Contents" / "MacOS").is_dir():
        print(f"not a valid .app bundle: {appBundle}", file=sys.stderr)
        return 1

    print(f"Restructuring {appBundle.name} ...")
    restructure(appBundle)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
