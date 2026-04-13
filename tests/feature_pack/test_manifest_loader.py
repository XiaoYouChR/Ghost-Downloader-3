from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api.manifest import Manifest
from app.feature_pack.api.manifest import ManifestError
from app.feature_pack.api.manifest import loadManifest
from app.feature_pack.api.manifest import parseManifest


class ManifestLoaderTests(unittest.TestCase):
    _temporaryDirectory: tempfile.TemporaryDirectory[str] | None = None
    workspace: Path = ROOT

    def setUp(self) -> None:  # pyright: ignore[reportImplicitOverride]
        temporaryDirectory = tempfile.TemporaryDirectory()
        self._temporaryDirectory = temporaryDirectory
        self.addCleanup(temporaryDirectory.cleanup)
        self.workspace = Path(temporaryDirectory.name)

    def writeManifest(self, body: str, *, relativePath: str = "manifest.toml") -> Path:
        manifestPath = self.workspace / relativePath
        manifestPath.parent.mkdir(parents=True, exist_ok=True)
        _ = manifestPath.write_text(
            textwrap.dedent(body).strip() + "\n",
            encoding="utf-8",
        )
        return manifestPath

    def testLoadManifestReturnsReadonlyManifestModel(self) -> None:
        manifestPath = self.writeManifest(
            """
            [pack]
            id = "http_pack"
            name = "HTTP Pack"
            version = "1.0.0"
            api = 1
            entry = "custom_pack.py"
            dependencies = ["extract_pack", "ffmpeg_pack"]
            schemes = ["https", "http"]
            tasks = ["download"]
            stages = ["resolve", "download"]
            """
        )

        manifest = loadManifest(manifestPath)

        self.assertIsInstance(manifest, Manifest)
        self.assertEqual(manifest.id, "http_pack")
        self.assertEqual(manifest.name, "HTTP Pack")
        self.assertEqual(manifest.version, "1.0.0")
        self.assertEqual(manifest.api, 1)
        self.assertEqual(manifest.entry, "custom_pack.py")
        self.assertEqual(manifest.dependencies, ("extract_pack", "ffmpeg_pack"))
        self.assertEqual(manifest.schemes, ("https", "http"))
        self.assertEqual(manifest.tasks, ("download",))
        self.assertEqual(manifest.stages, ("resolve", "download"))

    def testLoadManifestUsesContractDefaultsForOptionalFields(self) -> None:
        manifestPath = self.writeManifest(
            """
            [pack]
            id = "ftp_pack"
            name = "FTP Pack"
            version = "3.0.0"
            api = 1
            """
        )

        manifest = loadManifest(manifestPath)

        self.assertEqual(manifest.entry, "pack.py")
        self.assertEqual(manifest.dependencies, ())
        self.assertEqual(manifest.schemes, ())
        self.assertEqual(manifest.tasks, ())
        self.assertEqual(manifest.stages, ())

    def testLoadManifestReportsMissingFileWithStableCode(self) -> None:
        manifestPath = self.workspace / "missing" / "manifest.toml"

        with self.assertRaises(ManifestError) as context:
            _ = loadManifest(manifestPath)

        error = context.exception
        self.assertEqual(error.code, "missing-file")
        self.assertIsNone(error.field)
        self.assertEqual(error.manifestPath, manifestPath)
        self.assertIn("manifest.toml 文件不存在", error.reason)

    def testLoadManifestReportsTomlSyntaxErrors(self) -> None:
        manifestPath = self.writeManifest(
            """
            [pack
            id = "broken"
            """
        )

        with self.assertRaises(ManifestError) as context:
            _ = loadManifest(manifestPath)

        error = context.exception
        self.assertEqual(error.code, "invalid-toml")
        self.assertIsNone(error.field)
        self.assertEqual(error.manifestPath, manifestPath)
        self.assertTrue(error.reason)

    def testParseManifestRejectsMissingPackSection(self) -> None:
        with self.assertRaises(ManifestError) as context:
            _ = parseManifest({"name": "legacy"}, manifestPath=self.workspace / "manifest.toml")

        error = context.exception
        self.assertEqual(error.code, "missing-pack-section")
        self.assertIsNone(error.field)
        self.assertEqual(error.reason, "manifest 必须包含 [pack] 节")

    def testParseManifestRejectsMissingRequiredStringField(self) -> None:
        with self.assertRaises(ManifestError) as context:
            _ = parseManifest(
                {
                    "pack": {
                        "name": "HTTP Pack",
                        "version": "1.0.0",
                        "api": 1,
                    }
                },
                manifestPath=self.workspace / "manifest.toml",
            )

        error = context.exception
        self.assertEqual(error.code, "missing-field")
        self.assertEqual(error.field, "id")
        self.assertEqual(error.reason, "缺少必填字段")

    def testParseManifestRejectsBlankStringField(self) -> None:
        with self.assertRaises(ManifestError) as context:
            _ = parseManifest(
                {
                    "pack": {
                        "id": "http_pack",
                        "name": " ",
                        "version": "1.0.0",
                        "api": 1,
                    }
                },
                manifestPath=self.workspace / "manifest.toml",
            )

        error = context.exception
        self.assertEqual(error.code, "invalid-field-value")
        self.assertEqual(error.field, "name")
        self.assertEqual(error.reason, "不能为空字符串")

    def testParseManifestRejectsNonIntegerApi(self) -> None:
        with self.assertRaises(ManifestError) as context:
            _ = parseManifest(
                {
                    "pack": {
                        "id": "http_pack",
                        "name": "HTTP Pack",
                        "version": "1.0.0",
                        "api": "1",
                    }
                },
                manifestPath=self.workspace / "manifest.toml",
            )

        error = context.exception
        self.assertEqual(error.code, "invalid-field-type")
        self.assertEqual(error.field, "api")
        self.assertEqual(error.reason, "必须是整数")

    def testParseManifestRejectsNonListDependencies(self) -> None:
        with self.assertRaises(ManifestError) as context:
            _ = parseManifest(
                {
                    "pack": {
                        "id": "bili_pack",
                        "name": "Bilibili Pack",
                        "version": "1.0.0",
                        "api": 1,
                        "dependencies": "http_pack",
                    }
                },
                manifestPath=self.workspace / "manifest.toml",
            )

        error = context.exception
        self.assertEqual(error.code, "invalid-field-type")
        self.assertEqual(error.field, "dependencies")
        self.assertEqual(error.reason, "必须是字符串数组")

    def testParseManifestRejectsBlankSequenceItems(self) -> None:
        with self.assertRaises(ManifestError) as context:
            _ = parseManifest(
                {
                    "pack": {
                        "id": "bili_pack",
                        "name": "Bilibili Pack",
                        "version": "1.0.0",
                        "api": 1,
                        "tasks": ["video", " "],
                    }
                },
                manifestPath=self.workspace / "manifest.toml",
            )

        error = context.exception
        self.assertEqual(error.code, "invalid-field-value")
        self.assertEqual(error.field, "tasks")
        self.assertEqual(error.reason, "第 2 项不能为空字符串")


if __name__ == "__main__":
    _ = unittest.main()
