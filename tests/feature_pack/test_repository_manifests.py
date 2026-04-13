from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api.manifest import loadManifest


FEATURES_PATH = ROOT / "features"

EXPECTED_MANIFESTS: dict[str, dict[str, object]] = {
    "bili_pack": {
        "name": "Bilibili Pack",
        "dependencies": ("http_pack", "ffmpeg_pack"),
        "schemes": ("http", "https"),
        "tasks": ("bilibili_download",),
        "stages": ("http_download", "ffmpeg_merge"),
    },
    "bittorrent_pack": {
        "name": "BitTorrent Pack",
        "dependencies": (),
        "schemes": ("magnet", "http", "https", "file"),
        "tasks": ("bittorrent_download",),
        "stages": ("bittorrent_download",),
    },
    "extract_pack": {
        "name": "Extract Pack",
        "dependencies": (),
        "schemes": (),
        "tasks": (),
        "stages": ("extract_archive",),
    },
    "ffmpeg_pack": {
        "name": "FFmpeg Pack",
        "dependencies": ("http_pack", "extract_pack"),
        "schemes": ("gd3+ffmpeg",),
        "tasks": ("ffmpeg_install", "ffmpeg_merge"),
        "stages": ("http_download", "extract_archive", "ffmpeg_merge"),
    },
    "ftp_pack": {
        "name": "FTP Pack",
        "dependencies": (),
        "schemes": ("ftp", "ftps"),
        "tasks": ("ftp_download",),
        "stages": ("ftp_download",),
    },
    "github_pack": {
        "name": "GitHub Pack",
        "dependencies": ("http_pack",),
        "schemes": ("http", "https"),
        "tasks": ("github_download",),
        "stages": ("http_download",),
    },
    "http_pack": {
        "name": "HTTP Pack",
        "dependencies": (),
        "schemes": ("http", "https"),
        "tasks": ("http_download",),
        "stages": ("http_download",),
    },
    "jack_yao": {
        "name": "Jack Yao Pack",
        "dependencies": (),
        "schemes": (),
        "tasks": (),
        "stages": (),
    },
    "m3u8_pack": {
        "name": "M3U8 Pack",
        "dependencies": ("http_pack", "extract_pack", "ffmpeg_pack"),
        "schemes": ("http", "https"),
        "tasks": ("m3u8_download", "m3u8_install"),
        "stages": ("m3u8_download", "http_download", "extract_archive"),
    },
}


class RepositoryManifestTests(unittest.TestCase):
    def testAllRepositoryManifestsPassStrictValidation(self) -> None:
        manifestPaths = sorted(FEATURES_PATH.glob("*/manifest.toml"))

        self.assertEqual(
            [manifestPath.parent.name for manifestPath in manifestPaths],
            sorted(EXPECTED_MANIFESTS),
        )

        for manifestPath in manifestPaths:
            packId = manifestPath.parent.name
            expected = EXPECTED_MANIFESTS[packId]

            with self.subTest(packId=packId):
                manifest = loadManifest(manifestPath)

                self.assertEqual(manifest.id, packId)
                self.assertEqual(manifest.id, manifestPath.parent.name)
                self.assertEqual(manifest.name, expected["name"])
                self.assertEqual(manifest.version, "1.0.0")
                self.assertEqual(manifest.api, 1)
                self.assertEqual(manifest.entry, "pack.py")
                self.assertEqual(manifest.dependencies, expected["dependencies"])
                self.assertEqual(manifest.schemes, expected["schemes"])
                self.assertEqual(manifest.tasks, expected["tasks"])
                self.assertEqual(manifest.stages, expected["stages"])


if __name__ == "__main__":
    _ = unittest.main()
