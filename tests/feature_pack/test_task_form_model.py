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
from app.feature_pack.api import FormField
from app.feature_pack.api import TaskForm


class TaskFormModelTests(unittest.TestCase):
    def testFormChoiceUsesContractFieldOrderAndIsFrozen(self) -> None:
        choice = FormChoice(value="1080p", label="1080P")

        self.assertEqual([field.name for field in fields(FormChoice)], ["value", "label"])
        self.assertEqual(choice.value, "1080p")
        self.assertEqual(choice.label, "1080P")

        with self.assertRaises(FrozenInstanceError):
            choice.__setattr__("label", "720P")

    def testFormFieldUsesContractFieldOrderAndDefaults(self) -> None:
        fieldModel = FormField(
            key="name",
            label="文件名",
            kind="text",
        )

        self.assertEqual(
            [field.name for field in fields(FormField)],
            [
                "key",
                "label",
                "kind",
                "choices",
                "placeholder",
                "note",
                "min",
                "max",
                "step",
                "modes",
            ],
        )
        self.assertEqual(fieldModel.key, "name")
        self.assertEqual(fieldModel.label, "文件名")
        self.assertEqual(fieldModel.kind, "text")
        self.assertEqual(fieldModel.choices, ())
        self.assertEqual(fieldModel.placeholder, "")
        self.assertEqual(fieldModel.note, "")
        self.assertIsNone(fieldModel.min)
        self.assertIsNone(fieldModel.max)
        self.assertEqual(fieldModel.step, 1)
        self.assertEqual(fieldModel.modes, frozenset({"before", "running"}))

    def testFormFieldRequiresKeywordArguments(self) -> None:
        formFieldFactory = cast(Callable[..., object], FormField)

        with self.assertRaises(TypeError):
            _ = formFieldFactory("name", "文件名", "text")

    def testFormFieldAcceptsChoicesAndExplicitModeConstraints(self) -> None:
        fieldModel = FormField(
            key="quality",
            label="清晰度",
            kind="choice",
            choices=(
                FormChoice(value="1080p", label="1080P"),
                FormChoice(value="720p", label="720P"),
            ),
            placeholder="选择清晰度",
            note="运行中不可切换",
            min=1,
            max=2,
            step=1,
            modes=frozenset({"before"}),
        )

        self.assertEqual(
            fieldModel.choices,
            (
                FormChoice(value="1080p", label="1080P"),
                FormChoice(value="720p", label="720P"),
            ),
        )
        self.assertEqual(fieldModel.placeholder, "选择清晰度")
        self.assertEqual(fieldModel.note, "运行中不可切换")
        self.assertEqual(fieldModel.min, 1)
        self.assertEqual(fieldModel.max, 2)
        self.assertEqual(fieldModel.step, 1)
        self.assertEqual(fieldModel.modes, frozenset({"before"}))

    def testTaskFormUsesContractFieldOrderAndDefaults(self) -> None:
        taskForm = TaskForm()

        self.assertEqual([field.name for field in fields(TaskForm)], ["title", "fields"])
        self.assertEqual(taskForm.title, "编辑任务")
        self.assertEqual(taskForm.fields, ())

    def testTaskFormAcceptsExplicitFieldsAndIsFrozen(self) -> None:
        taskForm = TaskForm(
            title="编辑下载任务",
            fields=(
                FormField(key="source", label="来源", kind="text"),
                FormField(key="files", label="选择文件", kind="files"),
            ),
        )

        self.assertEqual(taskForm.title, "编辑下载任务")
        self.assertEqual(
            taskForm.fields,
            (
                FormField(key="source", label="来源", kind="text"),
                FormField(key="files", label="选择文件", kind="files"),
            ),
        )

        with self.assertRaises(FrozenInstanceError):
            taskForm.__setattr__("title", "别名")


if __name__ == "__main__":
    _ = unittest.main()
