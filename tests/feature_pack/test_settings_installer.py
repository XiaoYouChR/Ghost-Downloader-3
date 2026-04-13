# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportAny=false, reportMissingTypeStubs=false, reportImplicitOverride=false

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from typing import cast
from typing import final

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget
from qfluentwidgets import BodyLabel
from qfluentwidgets import ComboBox
from qfluentwidgets import PrimaryPushSettingCard
from qfluentwidgets import PushSettingCard
from qfluentwidgets import SettingCard
from qfluentwidgets import SettingCardGroup
from qfluentwidgets import SwitchButton

from app.feature_pack.api import DefaultSettingsInstaller
from app.feature_pack.api import FeaturePack
from app.feature_pack.api import FormChoice
from app.feature_pack.api import Manifest
from app.feature_pack.api import SettingItem
from app.feature_pack.api import SettingSection
from app.feature_pack.api import Task
from app.feature_pack.api import TaskInput


def ensureApplication() -> QApplication:
    application = QApplication.instance()
    if application is not None:
        return cast(QApplication, application)

    return QApplication([])


class FakeSettingPage:
    container: QWidget
    vBoxLayout: QVBoxLayout

    def __init__(self) -> None:
        self.container = QWidget()
        self.vBoxLayout = QVBoxLayout(self.container)


@final
class DeclarativePack(FeaturePack):
    manifest: Manifest = Manifest(
        id="demo_pack",
        name="Demo Pack",
        version="1.0.0",
        api=1,
    )
    _section: SettingSection | None

    def __init__(self, section: SettingSection | None) -> None:
        self._section = section

    def accepts(self, source: str) -> bool:
        return source.startswith("demo:")

    async def createTask(self, data: TaskInput) -> Task | None:
        _ = data
        return None

    def owns(self, task: Task) -> bool:
        _ = task
        return False

    def settingSection(self) -> SettingSection | object | None:
        return self._section


class SettingsInstallerTests(unittest.TestCase):
    application: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = ensureApplication()

    def showWidget(self, widget: QWidget) -> None:
        widget.show()
        application = self.application
        assert application is not None
        application.processEvents()
        self.addCleanup(widget.close)
        self.addCleanup(widget.deleteLater)

    def testSettingsInstallerKeepsSectionOrderAndMapsItemsToSettingCards(self) -> None:
        installer = DefaultSettingsInstaller()
        settingPage = FakeSettingPage()
        self.showWidget(settingPage.container)

        firstPack = DeclarativePack(
            SettingSection(
                id="alpha_pack",
                title="Alpha 设置",
                items=(
                    SettingItem(
                        key="enabled",
                        label="启用 Alpha",
                        kind="toggle",
                        note="开关说明",
                        extra={"value": True},
                    ),
                    SettingItem(
                        key="quality",
                        label="默认清晰度",
                        kind="choice",
                        options=(
                            FormChoice(value="high", label="高"),
                            FormChoice(value="low", label="低"),
                        ),
                        extra={"value": "low"},
                    ),
                ),
            )
        )
        secondPack = DeclarativePack(
            SettingSection(
                id="beta_pack",
                title="Beta 设置",
                items=(
                    SettingItem(
                        key="summary",
                        label="状态摘要",
                        kind="text",
                        extra={"value": "就绪"},
                    ),
                    SettingItem(
                        key="open",
                        label="打开面板",
                        kind="action",
                        extra={"buttonText": "打开"},
                    ),
                    SettingItem(
                        key="sync",
                        label="立即同步",
                        kind="primaryAction",
                        extra={"buttonText": "同步"},
                    ),
                ),
            )
        )

        firstGroup = installer.install(settingPage, firstPack)
        secondGroup = installer.install(settingPage, secondPack)

        self.assertIsInstance(firstGroup, SettingCardGroup)
        self.assertIsInstance(secondGroup, SettingCardGroup)
        assert firstGroup is not None
        assert secondGroup is not None

        self.assertEqual(settingPage.vBoxLayout.count(), 2)
        self.assertEqual(firstGroup.titleLabel.text(), "Alpha 设置")
        self.assertEqual(secondGroup.titleLabel.text(), "Beta 设置")

        firstCards = [
            widget
            for widget in firstGroup.findChildren(QWidget)
            if isinstance(widget, SettingCard)
        ]
        secondCards = [
            widget
            for widget in secondGroup.findChildren(QWidget)
            if isinstance(widget, SettingCard)
        ]
        self.assertEqual(
            [card.objectName() for card in firstCards],
            ["settingCard:enabled", "settingCard:quality"],
        )
        self.assertEqual(
            [card.objectName() for card in secondCards],
            ["settingCard:summary", "settingCard:open", "settingCard:sync"],
        )

        toggleCard = cast(SettingCard, firstGroup.findChild(SettingCard, "settingCard:enabled"))
        choiceCard = cast(SettingCard, firstGroup.findChild(SettingCard, "settingCard:quality"))
        textCard = cast(SettingCard, secondGroup.findChild(SettingCard, "settingCard:summary"))
        actionCard = cast(PushSettingCard, secondGroup.findChild(PushSettingCard, "settingCard:open"))
        primaryActionCard = cast(
            PrimaryPushSettingCard,
            secondGroup.findChild(PrimaryPushSettingCard, "settingCard:sync"),
        )

        toggleButton = cast(SwitchButton, toggleCard.findChild(SwitchButton))
        choiceComboBox = cast(ComboBox, choiceCard.findChild(ComboBox))
        summaryLabel = cast(BodyLabel, textCard.findChild(BodyLabel, "settingValue:summary"))

        self.assertTrue(toggleButton.isChecked())
        self.assertEqual(choiceComboBox.currentText(), "低")
        self.assertEqual(summaryLabel.text(), "就绪")
        self.assertEqual(actionCard.button.text(), "打开")
        self.assertEqual(primaryActionCard.button.text(), "同步")

    def testSettingsInstallerSkipsDuplicateSectionInstallOnSamePage(self) -> None:
        installer = DefaultSettingsInstaller()
        settingPage = FakeSettingPage()
        self.showWidget(settingPage.container)

        pack = DeclarativePack(
            SettingSection(
                id="shared_pack",
                title="共享设置",
                items=(SettingItem(key="enabled", label="启用", kind="toggle"),),
            )
        )

        firstGroup = installer.install(settingPage, pack)
        secondGroup = installer.install(settingPage, pack)

        self.assertIs(firstGroup, secondGroup)
        self.assertEqual(settingPage.vBoxLayout.count(), 1)
        self.assertEqual(
            [group.objectName() for group in settingPage.container.findChildren(SettingCardGroup)],
            ["featurePackSection:shared_pack"],
        )

    def testSettingsInstallerAllowsSameSectionIdOnDifferentPages(self) -> None:
        installer = DefaultSettingsInstaller()
        firstPage = FakeSettingPage()
        secondPage = FakeSettingPage()
        self.showWidget(firstPage.container)
        self.showWidget(secondPage.container)

        pack = DeclarativePack(
            SettingSection(
                id="portable_pack",
                title="跨页面设置",
                items=(SettingItem(key="enabled", label="启用", kind="toggle"),),
            )
        )

        firstGroup = installer.install(firstPage, pack)
        secondGroup = installer.install(secondPage, pack)

        self.assertIsNotNone(firstGroup)
        self.assertIsNotNone(secondGroup)
        self.assertIsNot(firstGroup, secondGroup)
        self.assertEqual(firstPage.vBoxLayout.count(), 1)
        self.assertEqual(secondPage.vBoxLayout.count(), 1)


if __name__ == "__main__":
    _ = unittest.main()
