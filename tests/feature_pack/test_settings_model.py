from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from dataclasses import fields
from pathlib import Path
from typing import Callable
from typing import cast


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api import FormChoice
from app.feature_pack.api import SettingItem
from app.feature_pack.api import SettingSection


class SettingModelTests(unittest.TestCase):
    def testSettingItemUsesContractFieldOrderAndDefaults(self) -> None:
        item = SettingItem(
            key="enableDash",
            label="启用 DASH",
            kind="toggle",
        )

        self.assertEqual(
            [field.name for field in fields(SettingItem)],
            ["key", "label", "kind", "note", "options", "extra"],
        )
        self.assertEqual(item.key, "enableDash")
        self.assertEqual(item.label, "启用 DASH")
        self.assertEqual(item.kind, "toggle")
        self.assertEqual(item.note, "")
        self.assertEqual(item.options, ())
        self.assertEqual(item.extra, {})

    def testSettingItemRequiresKeywordArguments(self) -> None:
        settingItemFactory = cast(Callable[..., object], SettingItem)

        with self.assertRaises(TypeError):
            _ = settingItemFactory("enableDash", "启用 DASH", "toggle")

    def testSettingItemAcceptsOptionsAndExtraMetadata(self) -> None:
        item = SettingItem(
            key="quality",
            label="默认清晰度",
            kind="choice",
            note="仅对新任务生效",
            options=(
                FormChoice(value="1080p", label="1080P"),
                FormChoice(value="720p", label="720P"),
            ),
            extra={"restartRequired": True, "group": "playback"},
        )

        self.assertEqual(item.note, "仅对新任务生效")
        self.assertEqual(
            item.options,
            (
                FormChoice(value="1080p", label="1080P"),
                FormChoice(value="720p", label="720P"),
            ),
        )
        self.assertEqual(item.extra, {"restartRequired": True, "group": "playback"})

        with self.assertRaises(FrozenInstanceError):
            item.__setattr__("kind", "text")

    def testSettingItemUsesIndependentExtraMappings(self) -> None:
        firstItem = SettingItem(
            key="first",
            label="First",
            kind="text",
        )
        secondItem = SettingItem(
            key="second",
            label="Second",
            kind="text",
        )

        self.assertIsNot(firstItem.extra, secondItem.extra)

    def testSettingSectionUsesContractFieldOrderAndDefaults(self) -> None:
        section = SettingSection(
            id="bili_pack",
            title="哔哩哔哩",
        )

        self.assertEqual(
            [field.name for field in fields(SettingSection)],
            ["id", "title", "items"],
        )
        self.assertEqual(section.id, "bili_pack")
        self.assertEqual(section.title, "哔哩哔哩")
        self.assertEqual(section.items, ())

    def testSettingSectionAcceptsExplicitItemsAndIsFrozen(self) -> None:
        section = SettingSection(
            id="m3u8_pack",
            title="M3U8 下载",
            items=(
                SettingItem(key="ffmpegPath", label="FFmpeg 路径", kind="path"),
                SettingItem(
                    key="quality",
                    label="默认清晰度",
                    kind="choice",
                    options=(FormChoice(value="best", label="最佳"),),
                ),
            ),
        )

        self.assertEqual(len(section.items), 2)
        self.assertEqual(section.items[0].key, "ffmpegPath")
        self.assertEqual(section.items[1].options, (FormChoice(value="best", label="最佳"),))

        with self.assertRaises(FrozenInstanceError):
            section.__setattr__("title", "改名")


if __name__ == "__main__":
    _ = unittest.main()
