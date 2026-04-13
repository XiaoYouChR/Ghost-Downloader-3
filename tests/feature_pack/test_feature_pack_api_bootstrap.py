from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

import app.feature_pack as featurePackPackage
import app.feature_pack.api as apiPackage
from app.feature_pack.api import EditMode
from app.feature_pack.api import FieldKind
from app.feature_pack.api import FeaturePack
from app.feature_pack.api import FormChoice
from app.feature_pack.api import FormField
from app.feature_pack.api import Manifest
from app.feature_pack.api import ManifestError
from app.feature_pack.api import cards
from app.feature_pack.api import config
from app.feature_pack.api import form
from app.feature_pack.api import input
from app.feature_pack.api import loadManifest
from app.feature_pack.api import manifest
from app.feature_pack.api import MultiFileTask
from app.feature_pack.api import MultiFileSelectDialog
from app.feature_pack.api import pack
from app.feature_pack.api import parseManifest
from app.feature_pack.api import service
from app.feature_pack.api import settings
from app.feature_pack.api import SingleFileTask
from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import snapshot
from app.feature_pack.api import stage
from app.feature_pack.api import task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskConfigDialog
from app.feature_pack.api import TaskFile
from app.feature_pack.api import TaskForm
from app.feature_pack.api import TaskInput
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import Task
from app.feature_pack.api import TaskStage
from app.feature_pack.api import testing


EXPECTED_EXPORTS = [
    "cards",
    "config",
    "form",
    "input",
    "manifest",
    "pack",
    "service",
    "settings",
    "snapshot",
    "stage",
    "task",
    "testing",
    "EditMode",
    "FieldKind",
    "FeaturePack",
    "FormChoice",
    "FormField",
    "Manifest",
    "ManifestError",
    "MultiFileTask",
    "MultiFileSelectDialog",
    "SingleFileTask",
    "StageSnapshot",
    "TaskConfig",
    "TaskConfigDialog",
    "TaskFile",
    "TaskForm",
    "TaskInput",
    "TaskSnapshot",
    "Task",
    "TaskStage",
    "loadManifest",
    "parseManifest",
]


class FeaturePackApiBootstrapTests(unittest.TestCase):
    def testFeaturePackPackageExportsApiNamespace(self) -> None:
        self.assertIs(featurePackPackage.api, apiPackage)

    def testApiPackageExportsStablePlaceholderModules(self) -> None:
        self.assertEqual(apiPackage.__all__, EXPECTED_EXPORTS)
        self.assertIs(apiPackage.cards, cards)
        self.assertIs(apiPackage.config, config)
        self.assertIs(apiPackage.form, form)
        self.assertIs(apiPackage.input, input)
        self.assertIs(apiPackage.manifest, manifest)
        self.assertIs(apiPackage.pack, pack)
        self.assertIs(apiPackage.service, service)
        self.assertIs(apiPackage.settings, settings)
        self.assertIs(apiPackage.snapshot, snapshot)
        self.assertIs(apiPackage.stage, stage)
        self.assertIs(apiPackage.task, task)
        self.assertIs(apiPackage.testing, testing)
        self.assertIs(apiPackage.EditMode, EditMode)
        self.assertIs(apiPackage.FieldKind, FieldKind)
        self.assertIs(apiPackage.FeaturePack, FeaturePack)
        self.assertIs(apiPackage.FormChoice, FormChoice)
        self.assertIs(apiPackage.FormField, FormField)
        self.assertIs(apiPackage.Manifest, Manifest)
        self.assertIs(apiPackage.ManifestError, ManifestError)
        self.assertIs(apiPackage.MultiFileTask, MultiFileTask)
        self.assertIs(apiPackage.MultiFileSelectDialog, MultiFileSelectDialog)
        self.assertIs(apiPackage.SingleFileTask, SingleFileTask)
        self.assertIs(apiPackage.StageSnapshot, StageSnapshot)
        self.assertIs(apiPackage.TaskConfig, TaskConfig)
        self.assertIs(apiPackage.TaskConfigDialog, TaskConfigDialog)
        self.assertIs(apiPackage.TaskFile, TaskFile)
        self.assertIs(apiPackage.TaskForm, TaskForm)
        self.assertIs(apiPackage.TaskInput, TaskInput)
        self.assertIs(apiPackage.TaskSnapshot, TaskSnapshot)
        self.assertIs(apiPackage.Task, Task)
        self.assertIs(apiPackage.TaskStage, TaskStage)
        self.assertIs(apiPackage.loadManifest, loadManifest)
        self.assertIs(apiPackage.parseManifest, parseManifest)
        self.assertIs(pack.FeaturePack, FeaturePack)
        self.assertIs(config.TaskConfig, TaskConfig)
        self.assertIs(form.EditMode, EditMode)
        self.assertIs(form.FieldKind, FieldKind)
        self.assertIs(form.FormChoice, FormChoice)
        self.assertIs(form.FormField, FormField)
        self.assertIs(form.TaskForm, TaskForm)
        self.assertIs(input.TaskInput, TaskInput)
        self.assertIs(manifest.Manifest, Manifest)
        self.assertIs(manifest.ManifestError, ManifestError)
        self.assertIs(manifest.loadManifest, loadManifest)
        self.assertIs(manifest.parseManifest, parseManifest)
        self.assertIs(snapshot.StageSnapshot, StageSnapshot)
        self.assertIs(snapshot.TaskSnapshot, TaskSnapshot)
        self.assertIs(stage.TaskStage, TaskStage)
        self.assertIs(task.MultiFileTask, MultiFileTask)
        self.assertIs(task.SingleFileTask, SingleFileTask)
        self.assertIs(task.TaskFile, TaskFile)
        self.assertIs(task.Task, Task)


if __name__ == "__main__":
    _ = unittest.main()
