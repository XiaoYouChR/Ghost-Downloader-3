from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from dataclasses import fields
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api import TaskConfig


class TaskConfigModelTests(unittest.TestCase):
    def testTaskConfigUsesContractFieldOrderAndDefaults(self) -> None:
        config = TaskConfig(
            source="https://example.com/file.zip",
            folder=Path("downloads"),
            name="file.zip",
        )

        self.assertEqual(
            [field.name for field in fields(TaskConfig)],
            [
                "source",
                "folder",
                "name",
                "headers",
                "proxies",
                "chunks",
            ],
        )
        self.assertEqual(config.source, "https://example.com/file.zip")
        self.assertEqual(config.folder, Path("downloads"))
        self.assertEqual(config.name, "file.zip")
        self.assertEqual(config.headers, {})
        self.assertIsNone(config.proxies)
        self.assertEqual(config.chunks, 1)

    def testTaskConfigRequiresKeywordArguments(self) -> None:
        with self.assertRaises(TypeError):
            _ = TaskConfig("https://example.com/file.zip", Path("downloads"), "file.zip")  # pyright: ignore[reportCallIssue]

    def testTaskConfigIsFrozen(self) -> None:
        config = TaskConfig(
            source="https://example.com/file.zip",
            folder=Path("downloads"),
            name="file.zip",
        )

        with self.assertRaises(FrozenInstanceError):
            config.__setattr__("name", "renamed.zip")

    def testTaskConfigAcceptsExplicitHeadersProxiesAndChunks(self) -> None:
        config = TaskConfig(
            source="https://example.com/video.mp4",
            folder=Path("media"),
            name="video.mp4",
            headers={"Authorization": "Bearer token"},
            proxies={"https": "socks5://127.0.0.1:1080"},
            chunks=8,
        )

        self.assertEqual(config.headers, {"Authorization": "Bearer token"})
        self.assertEqual(config.proxies, {"https": "socks5://127.0.0.1:1080"})
        self.assertEqual(config.chunks, 8)

    def testTaskConfigSupportsReplaceForUnifiedConfigUpdates(self) -> None:
        originalConfig = TaskConfig(
            source="https://example.com/file.zip",
            folder=Path("downloads"),
            name="file.zip",
            headers={"User-Agent": "Ghost Downloader"},
            proxies={"https": "http://127.0.0.1:7890"},
            chunks=4,
        )

        updatedConfig = replace(
            originalConfig,
            source="https://mirror.example.com/file.zip",
            folder=Path("archive"),
            name="renamed.zip",
            proxies=None,
            chunks=2,
        )

        self.assertEqual(originalConfig.source, "https://example.com/file.zip")
        self.assertEqual(originalConfig.folder, Path("downloads"))
        self.assertEqual(originalConfig.name, "file.zip")
        self.assertEqual(originalConfig.proxies, {"https": "http://127.0.0.1:7890"})
        self.assertEqual(originalConfig.chunks, 4)
        self.assertEqual(updatedConfig.source, "https://mirror.example.com/file.zip")
        self.assertEqual(updatedConfig.folder, Path("archive"))
        self.assertEqual(updatedConfig.name, "renamed.zip")
        self.assertEqual(
            updatedConfig.headers,
            {"User-Agent": "Ghost Downloader"},
        )
        self.assertIsNone(updatedConfig.proxies)
        self.assertEqual(updatedConfig.chunks, 2)


if __name__ == "__main__":
    _ = unittest.main()
