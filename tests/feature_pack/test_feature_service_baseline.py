from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api import DefaultFeatureService
from app.services.feature_service import HostFeatureService
from app.services.feature_service import featureService


class FeatureServiceBaselineTests(unittest.TestCase):
    def testLegacyAppBasesModulesAreRemoved(self) -> None:
        legacyDirectory = ROOT / "app" / "bases"

        self.assertFalse((legacyDirectory / "interfaces.py").exists())
        self.assertFalse((legacyDirectory / "models.py").exists())

    def testApplicationFeatureServiceExposesOnlyV1ServiceEntry(self) -> None:
        self.assertIsInstance(featureService, HostFeatureService)
        self.assertIsInstance(featureService, DefaultFeatureService)

        legacyMethodNames = (
            "discoverFeature" + "Packs",
            "getDialog" + "Cards",
            "can" + "Handle",
            "canCreateTaskFrom" + "Payload",
            "getPackForUrl",
            "parse",
            "createTaskFrom" + "Payload",
            "load" + "Features",
            "_loadPack" + "Config",
        )
        for methodName in legacyMethodNames:
            self.assertFalse(hasattr(featureService, methodName), methodName)

    def testApplicationPythonFilesDoNotImportLegacyBasePackage(self) -> None:
        forbiddenImport = "app." + "bases"
        checkedRoots = (ROOT / "app", ROOT / "features")
        matches: list[str] = []

        for checkedRoot in checkedRoots:
            for pythonFile in checkedRoot.rglob("*.py"):
                relativePath = pythonFile.relative_to(ROOT)
                text = pythonFile.read_text(encoding="utf-8")
                if forbiddenImport in text:
                    matches.append(str(relativePath))

        self.assertEqual(matches, [])


if __name__ == "__main__":
    _ = unittest.main()
