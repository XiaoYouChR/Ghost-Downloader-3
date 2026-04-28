from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api import Task
from app.feature_pack.api import TaskStage
from app.feature_pack.internal.recorder import TaskRecorder as InternalTaskRecorder
from app.feature_pack.internal.recorder import taskRecorder as internalTaskRecorder
from app.supports.recorder import TaskRecorder
from app.supports.recorder import taskRecorder


class TaskPersistenceBaselineTests(unittest.TestCase):
    def testApplicationRecorderEntryPointUsesV1Recorder(self) -> None:
        self.assertIs(TaskRecorder, InternalTaskRecorder)
        self.assertIs(taskRecorder, internalTaskRecorder)

    def testFreshRecorderUsesV1SchemaOnly(self) -> None:
        with tempfile.TemporaryDirectory() as temporaryDirectory:
            recordFile = Path(temporaryDirectory) / "FeaturePackMemory.log"
            recorder = TaskRecorder(recordFile=recordFile)

        self.assertEqual(recorder.recordSchemaVersion, 1)
        self.assertEqual(recorder.memorizedTasks, {})

    def testV0DeserializeEntryPointsAreRemovedFromTaskContracts(self) -> None:
        self.assertFalse(hasattr(Task, "deserialize"))
        self.assertFalse(hasattr(TaskStage, "deserialize"))


if __name__ == "__main__":
    _ = unittest.main()
