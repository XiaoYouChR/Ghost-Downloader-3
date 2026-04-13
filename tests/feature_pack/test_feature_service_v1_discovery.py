from __future__ import annotations

# pyright: reportImplicitOverride=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportPrivateUsage=false

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api import DefaultFeatureService
from app.feature_pack.api import FeatureService
from app.feature_pack.api import Manifest
from app.feature_pack.api import PackDiscoveryError


class FeatureServiceV1DiscoveryTests(unittest.TestCase):
    _temporaryDirectory: tempfile.TemporaryDirectory[str] | None = None
    featuresPath: Path = ROOT

    def setUp(self) -> None:
        temporaryDirectory = tempfile.TemporaryDirectory()
        self._temporaryDirectory = temporaryDirectory
        self.addCleanup(temporaryDirectory.cleanup)
        self.featuresPath = Path(temporaryDirectory.name)

    def createService(self) -> DefaultFeatureService:
        return DefaultFeatureService(featuresPath=self.featuresPath)

    def writePack(
        self,
        *,
        directoryName: str,
        packId: str | None = None,
        name: str | None = None,
        dependencies: tuple[str, ...] = (),
        entry: str = "pack.py",
        createEntry: bool = True,
    ) -> Path:
        packDirectory = self.featuresPath / directoryName
        packDirectory.mkdir(parents=True, exist_ok=True)

        manifestBody = textwrap.dedent(
            f"""
            [pack]
            id = "{packId or directoryName}"
            name = "{name or directoryName}"
            version = "1.0.0"
            api = 1
            entry = "{entry}"
            dependencies = [{", ".join(f'"{dependency}"' for dependency in dependencies)}]
            """
        ).strip()
        _ = (packDirectory / "manifest.toml").write_text(manifestBody + "\n", encoding="utf-8")

        if createEntry:
            _ = (packDirectory / entry).write_text("# feature pack entry\n", encoding="utf-8")
        return packDirectory

    def testFeatureServiceAbstractSurfaceMatchesContract(self) -> None:
        self.assertEqual(
            FeatureService.__abstractmethods__,
            frozenset(
                {
                    "configureTask",
                    "createResultCard",
                    "createTask",
                    "createTaskCard",
                    "discoverPacks",
                    "editTask",
                    "installSettings",
                    "loadPacks",
                    "pack",
                    "packForSource",
                    "packForTask",
                }
            ),
        )

    def testDiscoverPacksReturnsRepositoryManifestsInDependencyOrder(self) -> None:
        service = DefaultFeatureService(featuresPath=ROOT / "features")

        discovered = service.discoverPacks()

        self.assertEqual(
            [manifest.id for manifest in discovered],
            [
                "http_pack",
                "extract_pack",
                "ffmpeg_pack",
                "bili_pack",
                "bittorrent_pack",
                "ftp_pack",
                "github_pack",
                "jack_yao",
                "m3u8_pack",
            ],
        )
        self.assertEqual([type(manifest) for manifest in discovered], [Manifest] * len(discovered))
        self.assertEqual(discovered[0].dependencies, ())
        self.assertEqual(discovered[2].dependencies, ("http_pack", "extract_pack"))
        self.assertEqual(discovered[3].dependencies, ("http_pack", "ffmpeg_pack"))
        self.assertEqual(discovered[-1].dependencies, ("http_pack", "extract_pack", "ffmpeg_pack"))

    def testDiscoverPacksSkipsDirectoriesWithoutManifest(self) -> None:
        _ = self.writePack(directoryName="valid_pack")
        _ = (self.featuresPath / "notes").mkdir()

        service = self.createService()

        discovered = service.discoverPacks()

        self.assertEqual([manifest.id for manifest in discovered], ["valid_pack"])

    def testDiscoverPacksRaisesWhenEntryFileIsMissing(self) -> None:
        _ = self.writePack(directoryName="broken_pack", createEntry=False)

        service = self.createService()

        with self.assertRaises(PackDiscoveryError) as context:
            _ = service.discoverPacks()

        error = context.exception
        self.assertEqual(error.code, "missing-entry-file")
        self.assertEqual(error.packId, "broken_pack")
        self.assertIsNotNone(error.path)
        if error.path is None:
            self.fail("missing-entry-file must include the entry path")
        self.assertEqual(error.path.name, "pack.py")

    def testDiscoverPacksRaisesWhenDependencyIsMissing(self) -> None:
        _ = self.writePack(directoryName="video_pack", dependencies=("http_pack",))

        service = self.createService()

        with self.assertRaises(PackDiscoveryError) as context:
            _ = service.discoverPacks()

        error = context.exception
        self.assertEqual(error.code, "missing-dependency")
        self.assertEqual(error.packId, "video_pack")
        self.assertIn("http_pack", error.reason)

    def testDiscoverPacksRaisesOnDependencyCycle(self) -> None:
        _ = self.writePack(directoryName="alpha", dependencies=("beta",))
        _ = self.writePack(directoryName="beta", dependencies=("alpha",))

        service = self.createService()

        with self.assertRaises(PackDiscoveryError) as context:
            _ = service.discoverPacks()

        error = context.exception
        self.assertEqual(error.code, "dependency-cycle")
        self.assertIn("alpha -> beta -> alpha", error.reason)

    def testDiscoverPacksRejectsDuplicatePackIds(self) -> None:
        _ = self.writePack(directoryName="pack_a", packId="shared_pack")
        _ = self.writePack(directoryName="pack_b", packId="shared_pack")

        service = self.createService()

        with self.assertRaises(PackDiscoveryError) as context:
            _ = service.discoverPacks()

        error = context.exception
        self.assertEqual(error.code, "duplicate-pack-id")
        self.assertEqual(error.packId, "shared_pack")

    def testDiscoverPacksCachesOrderedPackIdsForLaterRounds(self) -> None:
        _ = self.writePack(directoryName="base_pack")
        _ = self.writePack(directoryName="child_pack", dependencies=("base_pack",))

        service = self.createService()

        discovered = service.discoverPacks()

        self.assertEqual([manifest.id for manifest in discovered], ["base_pack", "child_pack"])
        self.assertEqual(service._packOrder, ("base_pack", "child_pack"))
        self.assertEqual(sorted(service._discoveredPacksById), ["base_pack", "child_pack"])


if __name__ == "__main__":
    _ = unittest.main()
