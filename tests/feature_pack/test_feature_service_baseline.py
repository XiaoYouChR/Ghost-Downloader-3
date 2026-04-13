from __future__ import annotations
# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportUnknownLambdaType=false, reportImplicitOverride=false

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import cast


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.services.feature_service import FeatureService


PackInfo = dict[str, object]


def createFeatureService() -> FeatureService:
    return FeatureService()


def discoverFeaturePacks(service: FeatureService) -> list[PackInfo]:
    return cast(list[PackInfo], service.discoverFeaturePacks())


def sortFeaturePacks(service: FeatureService, featurePacks: list[PackInfo]) -> list[PackInfo]:
    return cast(list[PackInfo], service._sortFeaturePacksByDependencies(featurePacks))


def normalizePackNames(featurePacks: list[PackInfo]) -> list[str]:
    return [cast(str, pack["name"]) for pack in featurePacks]


class FeatureServiceBaselineTests(unittest.TestCase):
    _temporaryDirectory: tempfile.TemporaryDirectory[str] | None = None
    featuresPath: Path = ROOT

    def setUp(self) -> None:
        temporaryDirectory = tempfile.TemporaryDirectory()
        self._temporaryDirectory = temporaryDirectory
        self.addCleanup(temporaryDirectory.cleanup)
        self.featuresPath = Path(temporaryDirectory.name)

    def writePack(
        self,
        *,
        name: str,
        manifestBody: str,
        entryName: str = "pack.py",
        createEntry: bool = True,
    ) -> Path:
        packDirectory = self.featuresPath / name
        packDirectory.mkdir(parents=True, exist_ok=True)
        manifestPath = packDirectory / "manifest.toml"
        _ = manifestPath.write_text(
            textwrap.dedent(manifestBody).strip() + "\n",
            encoding="utf-8",
        )
        if createEntry:
            _ = (packDirectory / entryName).write_text(
                "# baseline test entry\n",
                encoding="utf-8",
            )
        return packDirectory

    def testDiscoverFeaturePacksMatchesCurrentRepositoryBaseline(self) -> None:
        service = createFeatureService()

        discovered = discoverFeaturePacks(service)
        discoveredByName = {
            cast(str, pack["name"]): pack
            for pack in discovered
        }

        self.assertEqual(
            normalizePackNames(discovered),
            [
                "bili_pack",
                "bittorrent_pack",
                "extract_pack",
                "ffmpeg_pack",
                "ftp_pack",
                "github_pack",
                "http_pack",
                "jack_yao",
                "m3u8_pack",
            ],
        )
        self.assertEqual(
            cast(tuple[str, ...], discoveredByName["bili_pack"]["dependencies"]),
            ("http_pack", "ffmpeg_pack"),
        )
        self.assertEqual(
            cast(tuple[str, ...], discoveredByName["extract_pack"]["dependencies"]),
            (),
        )
        self.assertEqual(
            cast(tuple[str, ...], discoveredByName["ftp_pack"]["dependencies"]),
            (),
        )
        self.assertEqual(
            Path(cast(str, discoveredByName["http_pack"]["manifestPath"])).name,
            "manifest.toml",
        )
        self.assertEqual(
            Path(cast(str, discoveredByName["github_pack"]["path"])).name,
            "pack.py",
        )

    def testDiscoverFeaturePacksKeepsLegacyDefaultEntryAndDependenciesBehavior(self) -> None:
        # 当前 loader 仍允许只写一个极简 [pack] 节，并把缺失字段补成默认值。
        _ = self.writePack(
            name="legacy_pack",
            manifestBody="""
            [pack]
            """,
        )

        service = createFeatureService()
        service.featuresPath = self.featuresPath

        discovered = discoverFeaturePacks(service)

        self.assertEqual(len(discovered), 1)
        self.assertEqual(cast(str, discovered[0]["name"]), "legacy_pack")
        self.assertEqual(Path(cast(str, discovered[0]["path"])).name, "pack.py")
        self.assertEqual(cast(tuple[str, ...], discovered[0]["dependencies"]), ())

    def testDiscoverFeaturePacksSkipsManifestsWithMissingRequiredParts(self) -> None:
        _ = self.writePack(
            name="valid_pack",
            manifestBody="""
            [pack]
            entry = "pack.py"
            dependencies = []
            """,
        )
        _ = self.writePack(
            name="missing_pack_section",
            manifestBody="""
            title = "legacy"
            """,
        )
        _ = self.writePack(
            name="missing_entry_file",
            manifestBody="""
            [pack]
            entry = "missing.py"
            """,
            entryName="pack.py",
            createEntry=False,
        )

        service = createFeatureService()
        service.featuresPath = self.featuresPath

        discovered = discoverFeaturePacks(service)

        self.assertEqual(normalizePackNames(discovered), ["valid_pack"])

    def testSortFeaturePacksByDependenciesMatchesCurrentRepositoryOrder(self) -> None:
        service = createFeatureService()

        discovered = discoverFeaturePacks(service)
        ordered = sortFeaturePacks(service, discovered)

        self.assertEqual(
            normalizePackNames(ordered),
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

    def testSortFeaturePacksByDependenciesSkipsCyclesAfterLogging(self) -> None:
        # 历史包袱: 当前排序器不会把循环依赖抛给调用方，而是记录错误后跳过坏分支。
        featurePacks: list[PackInfo] = [
            {"name": "alpha", "dependencies": ("beta",)},
            {"name": "beta", "dependencies": ("alpha",)},
            {"name": "healthy", "dependencies": ()},
        ]

        service = createFeatureService()

        ordered = sortFeaturePacks(service, featurePacks)

        self.assertEqual(normalizePackNames(ordered), ["healthy"])


if __name__ == "__main__":
    _ = unittest.main()
