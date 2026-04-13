from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError, fields
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api.manifest import Manifest


class ManifestModelTests(unittest.TestCase):
    def testManifestUsesContractFieldOrderAndDefaults(self) -> None:
        manifest = Manifest(
            id="http_pack",
            name="HTTP Pack",
            version="1.0.0",
            api=1,
        )

        self.assertEqual(
            [field.name for field in fields(Manifest)],
            [
                "id",
                "name",
                "version",
                "api",
                "entry",
                "dependencies",
                "schemes",
                "tasks",
                "stages",
            ],
        )
        self.assertEqual(manifest.id, "http_pack")
        self.assertEqual(manifest.name, "HTTP Pack")
        self.assertEqual(manifest.version, "1.0.0")
        self.assertEqual(manifest.api, 1)
        self.assertEqual(manifest.entry, "pack.py")
        self.assertEqual(manifest.dependencies, ())
        self.assertEqual(manifest.schemes, ())
        self.assertEqual(manifest.tasks, ())
        self.assertEqual(manifest.stages, ())

    def testManifestRequiresKeywordArguments(self) -> None:
        with self.assertRaises(TypeError):
            _ = Manifest("http_pack", "HTTP Pack", "1.0.0", 1)  # pyright: ignore[reportCallIssue]

    def testManifestIsFrozen(self) -> None:
        manifest = Manifest(
            id="http_pack",
            name="HTTP Pack",
            version="1.0.0",
            api=1,
        )

        with self.assertRaises(FrozenInstanceError):
            manifest.__setattr__("entry", "custom.py")

    def testManifestAcceptsExplicitTupleMetadata(self) -> None:
        manifest = Manifest(
            id="bili_pack",
            name="Bilibili Pack",
            version="2.0.0",
            api=1,
            entry="pack.py",
            dependencies=("http_pack", "ffmpeg_pack"),
            schemes=("https", "bilibili"),
            tasks=("video", "audio"),
            stages=("resolve", "download", "merge"),
        )

        self.assertEqual(manifest.dependencies, ("http_pack", "ffmpeg_pack"))
        self.assertEqual(manifest.schemes, ("https", "bilibili"))
        self.assertEqual(manifest.tasks, ("video", "audio"))
        self.assertEqual(manifest.stages, ("resolve", "download", "merge"))


if __name__ == "__main__":
    _ = unittest.main()
