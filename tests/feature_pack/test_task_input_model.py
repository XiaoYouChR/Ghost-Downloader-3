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

from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskInput


class TaskInputModelTests(unittest.TestCase):
    def testTaskInputUsesContractFieldOrderAndDefaults(self) -> None:
        taskInput = TaskInput(
            config=TaskConfig(
                source="https://example.com/file.zip",
                folder=Path("downloads"),
                name="file.zip",
            )
        )

        self.assertEqual(
            [field.name for field in fields(TaskInput)],
            ["config", "size", "hints"],
        )
        self.assertEqual(
            taskInput.config,
            TaskConfig(
                source="https://example.com/file.zip",
                folder=Path("downloads"),
                name="file.zip",
            ),
        )
        self.assertEqual(taskInput.size, 0)
        self.assertEqual(taskInput.hints, ())

    def testTaskInputRequiresKeywordArguments(self) -> None:
        taskInputFactory = cast(Callable[..., object], TaskInput)

        with self.assertRaises(TypeError):
            _ = taskInputFactory(
                TaskConfig(
                    source="https://example.com/file.zip",
                    folder=Path("downloads"),
                    name="file.zip",
                )
            )

    def testTaskInputIsFrozen(self) -> None:
        taskInput = TaskInput(
            config=TaskConfig(
                source="https://example.com/file.zip",
                folder=Path("downloads"),
                name="file.zip",
            )
        )

        with self.assertRaises(FrozenInstanceError):
            taskInput.__setattr__("size", 1024)

    def testTaskInputAcceptsExplicitSizeAndHints(self) -> None:
        taskInput = TaskInput(
            config=TaskConfig(
                source="https://example.com/video.mp4",
                folder=Path("media"),
                name="video.mp4",
                headers={"User-Agent": "Ghost Downloader"},
                chunks=8,
            ),
            size=4096,
            hints=(
                {"sourceType": "browser"},
                {"resumeToken": "token-1", "priority": 2},
            ),
        )

        self.assertEqual(taskInput.size, 4096)
        self.assertEqual(
            taskInput.hints,
            (
                {"sourceType": "browser"},
                {"resumeToken": "token-1", "priority": 2},
            ),
        )
        self.assertEqual(taskInput.config.headers, {"User-Agent": "Ghost Downloader"})
        self.assertEqual(taskInput.config.chunks, 8)


if __name__ == "__main__":
    _ = unittest.main()
