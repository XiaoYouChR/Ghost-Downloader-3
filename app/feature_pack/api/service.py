# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportAny=false, reportMissingTypeStubs=false, reportImplicitOverride=false

"""Host-side service helpers for Feature Pack V1."""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Protocol
from typing import cast
from typing import final
from weakref import WeakKeyDictionary

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget
from qfluentwidgets import BodyLabel
from qfluentwidgets import ComboBoxSettingCard
from qfluentwidgets import ConfigItem
from qfluentwidgets import FluentIcon
from qfluentwidgets import OptionsConfigItem
from qfluentwidgets import OptionsValidator
from qfluentwidgets import PrimaryPushSettingCard
from qfluentwidgets import PushSettingCard
from qfluentwidgets import SettingCard
from qfluentwidgets import SettingCardGroup
from qfluentwidgets import SwitchSettingCard

from app.feature_pack.api.form import EditMode
from app.feature_pack.api.settings import SettingItem
from app.feature_pack.api.settings import SettingSection
from app.feature_pack.api.task import MultiFileTask
from app.feature_pack.api.task import Task
from app.feature_pack.ui.dialogs import TaskConfigDialog

if TYPE_CHECKING:
    from .pack import FeaturePack


def _translate(context: str, text: str) -> str:
    return QCoreApplication.translate(context, text)


class SettingPageHost(Protocol):
    """Minimal setting page shape required by the installer."""

    container: QWidget
    vBoxLayout: QVBoxLayout


@dataclass(slots=True)
class InstalledSettingSection:
    """Keep installed group state per page so duplicate installs stay idempotent."""

    section: SettingSection
    group: SettingCardGroup


class SettingsInstaller(ABC):
    """Install declarative pack settings into a host ``SettingPage``."""

    @abstractmethod
    def install(self, page: object, pack: FeaturePack | None = None) -> SettingCardGroup | None:
        """Install one pack contribution and return its created group when present."""


class TaskEditor(ABC):
    """Open the default task editor and apply accepted task changes."""

    @abstractmethod
    def editTask(
        self,
        task: Task,
        mode: EditMode,
        parent: QWidget | None = None,
    ) -> bool:
        """Edit one task and return whether the user confirmed changes."""


@final
class DefaultTaskEditor(TaskEditor):
    """Default host task editor that routes through ``TaskConfigDialog``."""

    def editTask(
        self,
        task: Task,
        mode: EditMode,
        parent: QWidget | None = None,
    ) -> bool:
        form = task.editForm(mode)
        if form is None:
            return False

        dialog = TaskConfigDialog(
            task=task,
            form=form,
            mode=mode,
            parent=parent,
        )
        accepted = dialog.exec()
        if not accepted:
            return False

        if isinstance(task, MultiFileTask):
            task.select(dialog.selectedIds())
        task.configure(dialog.config())
        task.snapshotChanged.emit(task.snapshot())
        return True


@final
class _SettingToggleCard(SwitchSettingCard):
    """Minimal host-owned switch card for declarative toggle settings."""

    settingItem: SettingItem
    configItem: ConfigItem

    def __init__(self, *, item: SettingItem, group: SettingCardGroup) -> None:
        self.settingItem = item
        configItem = ConfigItem(
            group=item.extra.get("configGroup", f"FeaturePack/{group.objectName() or 'Host'}"),
            name=item.key,
            default=bool(item.extra.get("value", False)),
        )
        super().__init__(
            FluentIcon.SETTING,
            item.label,
            item.note or None,
            configItem,
            group,
        )
        self.configItem = configItem
        self.setObjectName(f"settingCard:{item.key}")
        _ = self.checkedChanged.connect(self._onCheckedChanged)

    def _onCheckedChanged(self, value: bool) -> None:
        self.configItem.value = value


@final
class _SettingChoiceCard(ComboBoxSettingCard):
    """Minimal host-owned choice card for declarative options."""

    settingItem: SettingItem
    configItem: OptionsConfigItem

    def __init__(self, *, item: SettingItem, group: SettingCardGroup) -> None:
        self.settingItem = item
        values = tuple(choice.value for choice in item.options)
        if not values:
            raise ValueError(f"choice setting '{item.key}' requires options")

        defaultValue = str(item.extra.get("value", values[0]))
        if defaultValue not in values:
            defaultValue = values[0]

        configItem = OptionsConfigItem(
            group=item.extra.get("configGroup", f"FeaturePack/{group.objectName() or 'Host'}"),
            name=item.key,
            default=defaultValue,
            validator=OptionsValidator(values),
        )
        super().__init__(
            configItem,
            FluentIcon.SETTING,
            item.label,
            item.note or None,
            texts=[choice.label for choice in item.options],
            parent=group,
        )
        self.configItem = configItem
        self.setObjectName(f"settingCard:{item.key}")
        _ = self.comboBox.currentIndexChanged.connect(self._syncCurrentChoice)

    def _syncCurrentChoice(self, index: int) -> None:
        if index < 0 or index >= self.comboBox.count():
            return

        choice = self.comboBox.itemText(index)
        matchingValue = next(
            (
                option.value
                for option in self.settingItem.options
                if option.label == choice
            ),
            None,
        )
        if matchingValue is not None:
            self.configItem.value = matchingValue


@final
class _SettingTextCard(SettingCard):
    """Compact host-owned text display card."""

    settingItem: SettingItem
    valueLabel: BodyLabel

    def __init__(self, *, item: SettingItem, group: SettingCardGroup) -> None:
        super().__init__(FluentIcon.SETTING, item.label, item.note or None, group)
        self.settingItem = item
        self.valueLabel = BodyLabel(str(item.extra.get("value", "")), self)
        self.valueLabel.setObjectName(f"settingValue:{item.key}")
        self.hBoxLayout.addWidget(self.valueLabel)
        self.hBoxLayout.addSpacing(16)
        self.setObjectName(f"settingCard:{item.key}")


@final
class _SettingActionCard(PushSettingCard):
    """Minimal host-owned action card that emits a click callback when provided."""

    settingItem: SettingItem

    def __init__(self, *, item: SettingItem, group: SettingCardGroup) -> None:
        buttonText = str(item.extra.get("buttonText", _translate("SettingsInstaller", "打开")))
        super().__init__(
            buttonText,
            FluentIcon.SETTING,
            item.label,
            item.note or None,
            group,
        )
        self.settingItem = item
        self.setObjectName(f"settingCard:{item.key}")
        callback = item.extra.get("onClick")
        if callable(callback):
            _ = self.clicked.connect(callback)


@final
class _SettingPrimaryActionCard(PrimaryPushSettingCard):
    """Primary action variant for declarative host settings."""

    settingItem: SettingItem

    def __init__(self, *, item: SettingItem, group: SettingCardGroup) -> None:
        buttonText = str(item.extra.get("buttonText", _translate("SettingsInstaller", "执行")))
        super().__init__(
            buttonText,
            FluentIcon.SETTING,
            item.label,
            item.note or None,
            group,
        )
        self.settingItem = item
        self.setObjectName(f"settingCard:{item.key}")
        callback = item.extra.get("onClick")
        if callable(callback):
            _ = self.clicked.connect(callback)


@final
class DefaultSettingsInstaller(SettingsInstaller):
    """
    Default host implementation for declarative pack settings.

    Packs only return ``SettingSection`` data. This installer owns the mapping to
    ``SettingCardGroup`` and keeps installation idempotent per page and section id.
    """

    _SUPPORTED_KINDS: frozenset[str] = frozenset(
        {"toggle", "choice", "text", "action", "primaryAction"}
    )

    def __init__(self) -> None:
        self._installedByPage: WeakKeyDictionary[SettingPageHost, dict[str, InstalledSettingSection]] = WeakKeyDictionary()

    def install(self, page: object, pack: FeaturePack | None = None) -> SettingCardGroup | None:
        if pack is None:
            return None

        section = pack.settingSection()
        if section is None:
            return None
        if not isinstance(section, SettingSection):
            return None

        settingPage = self._coercePage(page)
        installedSections = self._installedByPage.setdefault(settingPage, {})
        installed = installedSections.get(section.id)
        if installed is not None:
            return installed.group

        group = SettingCardGroup(section.title, settingPage.container)
        group.setObjectName(f"featurePackSection:{section.id}")
        for item in section.items:
            group.addSettingCard(self._createCard(item=item, group=group))

        settingPage.vBoxLayout.addWidget(group)
        installedSections[section.id] = InstalledSettingSection(section=section, group=group)
        return group

    def _coercePage(self, page: object) -> SettingPageHost:
        container = getattr(page, "container", None)
        layout = getattr(page, "vBoxLayout", None)
        if not isinstance(container, QWidget) or not isinstance(layout, QVBoxLayout):
            raise TypeError("SettingsInstaller requires a page with container and vBoxLayout")
        return cast(SettingPageHost, page)

    def _createCard(self, *, item: SettingItem, group: SettingCardGroup) -> SettingCard:
        if item.kind not in self._SUPPORTED_KINDS:
            raise ValueError(f"Unsupported setting item kind: {item.kind}")

        if item.kind == "toggle":
            return _SettingToggleCard(item=item, group=group)
        if item.kind == "choice":
            return _SettingChoiceCard(item=item, group=group)
        if item.kind == "text":
            return _SettingTextCard(item=item, group=group)
        if item.kind == "action":
            return _SettingActionCard(item=item, group=group)
        return _SettingPrimaryActionCard(item=item, group=group)


__all__ = [
    "DefaultSettingsInstaller",
    "DefaultTaskEditor",
    "InstalledSettingSection",
    "SettingsInstaller",
    "TaskEditor",
]
