from __future__ import annotations

import sys
import unittest
from dataclasses import fields
from pathlib import Path
from typing import Callable
from typing import cast


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api import TaskFile


class TaskFileModelTests(unittest.TestCase):
    def testTaskFileUsesContractFieldOrderAndDefaults(self) -> None:
        taskFile = TaskFile(
            id="episode-01",
            path="Season 1/episode-01.mp4",
            size=4096,
        )

        self.assertEqual(
            [field.name for field in fields(TaskFile)],
            [
                "id",
                "path",
                "size",
                "selected",
                "note",
                "doneBytes",
                "finished",
            ],
        )
        self.assertEqual(taskFile.id, "episode-01")
        self.assertEqual(taskFile.path, "Season 1/episode-01.mp4")
        self.assertEqual(taskFile.size, 4096)
        self.assertTrue(taskFile.selected)
        self.assertEqual(taskFile.note, "")
        self.assertEqual(taskFile.doneBytes, 0)
        self.assertFalse(taskFile.finished)

    def testTaskFileRequiresKeywordArguments(self) -> None:
        taskFileFactory = cast(Callable[..., object], TaskFile)

        with self.assertRaises(TypeError):
            _ = taskFileFactory("episode-01", "Season 1/episode-01.mp4", 4096)

    def testTaskFileAcceptsExplicitSelectionAndSummaryFields(self) -> None:
        taskFile = TaskFile(
            id="track-2",
            path="Album/track-02.flac",
            size=8192,
            selected=False,
            note="Lossless",
            doneBytes=2048,
            finished=True,
        )

        self.assertFalse(taskFile.selected)
        self.assertEqual(taskFile.note, "Lossless")
        self.assertEqual(taskFile.doneBytes, 2048)
        self.assertTrue(taskFile.finished)

    def testTaskFileRemainsMutableForRuntimeSelectionAndProgressUpdates(self) -> None:
        taskFile = TaskFile(
            id="file-1",
            path="Downloads/file-1.bin",
            size=1024,
        )

        taskFile.selected = False
        taskFile.note = "Skipped by user"
        taskFile.doneBytes = 1024
        taskFile.finished = True

        self.assertFalse(taskFile.selected)
        self.assertEqual(taskFile.note, "Skipped by user")
        self.assertEqual(taskFile.doneBytes, 1024)
        self.assertTrue(taskFile.finished)


if __name__ == "__main__":
    _ = unittest.main()
