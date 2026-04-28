# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportAny=false, reportMissingTypeStubs=false, reportImplicitOverride=false

"""Host-side service helpers and FeatureService contract for Feature Pack V1."""

from __future__ import annotations

import importlib.util
import sys
from abc import ABC
from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
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

from .config import TaskConfig
from .form import EditMode
from .input import TaskInput
from .manifest import Manifest
from .manifest import loadManifest
from .pack import FeaturePack
from .settings import SettingItem
from .settings import SettingSection
from .task import MultiFileTask
from .task import Task
from ..ui.cards import DefaultResultCard
from ..ui.cards import DefaultTaskCard
from ..ui.dialogs import TaskConfigDialog


def _translate(context: str, text: str) -> str:
    return QCoreApplication.translate(context, text)


def _defaultFeaturesPath() -> Path:
    return Path(__file__).resolve().parents[3] / "features"


@dataclass(frozen=True, slots=True, kw_only=True)
class DiscoveredPack:
    """Resolved manifest metadata and filesystem paths for one pack."""

    manifest: Manifest
    directory: Path
    manifestPath: Path
    entryPath: Path


@dataclass(frozen=True, slots=True, kw_only=True)
class LoadedPack:
    """Runtime state for one successfully loaded pack instance."""

    manifest: Manifest
    directory: Path
    manifestPath: Path
    entryPath: Path
    moduleName: str
    module: ModuleType
    packClass: type[FeaturePack]
    pack: FeaturePack


class PackDiscoveryError(RuntimeError):
    """Stable discovery failure for manifest scanning and dependency sorting."""

    code: str
    reason: str
    packId: str | None
    path: Path | None

    def __init__(
        self,
        *,
        code: str,
        reason: str,
        packId: str | None = None,
        path: Path | None = None,
    ) -> None:
        self.code = code
        self.reason = reason
        self.packId = packId
        self.path = path

        messageParts: list[str] = [f"[{code}]"]
        if packId is not None:
            messageParts.append(packId)
        if path is not None:
            messageParts.append(str(path))
        messageParts.append(reason)
        super().__init__(" ".join(messageParts))


class PackLoadError(RuntimeError):
    """Stable pack loading failure for module import and pack instantiation."""

    code: str
    reason: str
    packId: str | None
    path: Path | None

    def __init__(
        self,
        *,
        code: str,
        reason: str,
        packId: str | None = None,
        path: Path | None = None,
    ) -> None:
        self.code = code
        self.reason = reason
        self.packId = packId
        self.path = path

        messageParts: list[str] = [f"[{code}]"]
        if packId is not None:
            messageParts.append(packId)
        if path is not None:
            messageParts.append(str(path))
        messageParts.append(reason)
        super().__init__(" ".join(messageParts))


class FeatureService(ABC):
    """Host-facing Feature Pack service contract."""

    @abstractmethod
    def discoverPacks(self) -> list[Manifest]:
        """Discover and dependency-sort all manifests under ``features/``."""

    @abstractmethod
    def loadPacks(self, window: object) -> None:
        """Load pack modules and register them into the host."""

    @abstractmethod
    def pack(self, packId: str) -> FeaturePack | None:
        """Return one loaded pack instance by id when available."""

    @abstractmethod
    def packForSource(self, source: str) -> FeaturePack | None:
        """Route one source string to its owning pack."""

    @abstractmethod
    def packForTask(self, task: Task) -> FeaturePack | None:
        """Route one existing task back to its owning pack."""

    @abstractmethod
    async def createTask(self, data: TaskInput) -> Task:
        """Create one task through the selected pack."""

    @abstractmethod
    def configureTask(self, taskId: str, config: TaskConfig) -> None:
        """Apply one ``TaskConfig`` update through the host service."""

    @abstractmethod
    def installSettings(self, page: object) -> None:
        """Install pack settings onto one host settings page."""

    @abstractmethod
    def editTask(
        self,
        task: Task,
        mode: EditMode,
        parent: QWidget | None = None,
    ) -> bool:
        """Open the host edit flow for one task."""

    @abstractmethod
    def createTaskCard(self, task: Task, parent: QWidget | None = None) -> object:
        """Create one task card for a routed task."""

    @abstractmethod
    def createResultCard(self, task: Task, parent: QWidget | None = None) -> object:
        """Create one result card for a routed task."""


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
            task.requestCommand("select", dialog.selectedIds())
        task.requestCommand("configure", dialog.config())
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
        {"toggle", "choice", "text", "action", "primaryAction", "custom"}
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
        if item.kind == "custom":
            return self._createCustomCard(item=item, group=group)
        return _SettingPrimaryActionCard(item=item, group=group)

    def _createCustomCard(self, *, item: SettingItem, group: SettingCardGroup) -> SettingCard:
        cardFactory = item.extra.get("cardFactory")
        if not callable(cardFactory):
            raise ValueError(f"custom setting '{item.key}' requires a cardFactory")

        card = cardFactory(group)
        if not isinstance(card, SettingCard):
            raise TypeError(f"custom setting '{item.key}' must return SettingCard")

        card.setObjectName(f"settingCard:{item.key}")
        return card


class DefaultFeatureService(FeatureService):
    """Default host service implementation for pack discovery and loading."""

    featuresPath: Path
    settingsInstaller: SettingsInstaller
    taskEditor: TaskEditor

    def __init__(
        self,
        *,
        featuresPath: str | Path | None = None,
        settingsInstaller: SettingsInstaller | None = None,
        taskEditor: TaskEditor | None = None,
    ) -> None:
        self.featuresPath = Path(featuresPath) if featuresPath is not None else _defaultFeaturesPath()
        self.settingsInstaller = (
            settingsInstaller if settingsInstaller is not None else DefaultSettingsInstaller()
        )
        self.taskEditor = taskEditor if taskEditor is not None else DefaultTaskEditor()
        self._discoveredPacksById: dict[str, DiscoveredPack] = {}
        self._packOrder: tuple[str, ...] = ()
        self._loadedPacksById: dict[str, LoadedPack] = {}
        self._loadedPackOrder: tuple[str, ...] = ()
        self._knownTasksById: dict[str, Task] = {}

    def discoverPacks(self) -> list[Manifest]:
        discoveredPacks = self._discoverPackDescriptors()
        orderedPacks = self._sortDiscoveredPacksByDependencies(discoveredPacks)
        self._cacheDiscoveredPacks(orderedPacks)
        return [discoveredPack.manifest for discoveredPack in orderedPacks]

    def loadPacks(self, window: object) -> None:
        if self._loadedPackOrder:
            return

        discoveredPacks = self._orderedDiscoveredPacks()
        if not discoveredPacks:
            self._cacheLoadedPacks(())
            return

        loadedPacks: list[LoadedPack] = []
        try:
            for discoveredPack in discoveredPacks:
                loadedPacks.append(self._loadPack(discoveredPack))

            for loadedPack in loadedPacks:
                self._installLoadedPack(loadedPack, window)
        except Exception:
            self._unloadPackModuleTrees(loadedPacks)
            self._cacheLoadedPacks(())
            raise

        self._cacheLoadedPacks(loadedPacks)

    def pack(self, packId: str) -> FeaturePack | None:
        loadedPack = self._loadedPacksById.get(packId)
        if loadedPack is None:
            return None
        return loadedPack.pack

    def packForSource(self, source: str) -> FeaturePack | None:
        return self._routeLoadedPack(lambda pack: pack.accepts(source))

    def packForTask(self, task: Task) -> FeaturePack | None:
        return self._routeLoadedPack(lambda pack: pack.owns(task))

    async def createTask(self, data: TaskInput) -> Task:
        source = data.config.source.strip()
        if not source:
            raise ValueError("TaskInput.config.source 不能为空")

        pack = self.packForSource(source)
        if pack is None:
            raise ValueError(f"未找到可处理该来源的 FeaturePack: {source}")

        createdTask = await pack.createTask(data)
        if createdTask is None:
            raise ValueError(f"FeaturePack 未创建任务: {source}")

        self._rememberTask(createdTask)
        return createdTask

    def configureTask(self, taskId: str, config: TaskConfig) -> None:
        task = self._knownTasksById.get(taskId)
        if task is None:
            raise ValueError(f"未找到可配置的任务: {taskId}")

        self._rememberTask(task)
        task.requestCommand("configure", config)
        task.snapshotChanged.emit(task.snapshot())

    def installSettings(self, page: object) -> None:
        for packId in self._loadedPackOrder:
            loadedPack = self._loadedPacksById[packId]
            _ = self.settingsInstaller.install(page, loadedPack.pack)

    def editTask(
        self,
        task: Task,
        mode: EditMode,
        parent: QWidget | None = None,
    ) -> bool:
        self._rememberTask(task)
        return self.taskEditor.editTask(task, mode, parent)

    def createTaskCard(self, task: Task, parent: QWidget | None = None) -> object:
        self._rememberTask(task)
        pack = self.packForTask(task)
        if pack is not None:
            card = pack.createTaskCard(task, parent)
            if card is not None:
                return card

        return DefaultTaskCard(task=task, editor=self, parent=parent)

    def createResultCard(self, task: Task, parent: QWidget | None = None) -> object:
        self._rememberTask(task)
        pack = self.packForTask(task)
        if pack is not None:
            card = pack.createResultCard(task, parent)
            if card is not None:
                return card

        return DefaultResultCard(task=task, editor=self, parent=parent)

    def _rememberTask(self, task: Task) -> None:
        self._knownTasksById[task.id] = task

    def _discoverPackDescriptors(self) -> list[DiscoveredPack]:
        if not self.featuresPath.exists():
            self._cacheDiscoveredPacks(())
            return []

        discoveredPacks: list[DiscoveredPack] = []
        for packDirectory in self._iterPackDirectories():
            discoveredPack = self._discoverPack(packDirectory)
            if discoveredPack is not None:
                discoveredPacks.append(discoveredPack)
        return discoveredPacks

    def _iterPackDirectories(self) -> list[Path]:
        return sorted(
            (
                item
                for item in self.featuresPath.iterdir()
                if item.is_dir() and not item.name.startswith(".")
            ),
            key=lambda item: item.name,
        )

    def _discoverPack(self, packDirectory: Path) -> DiscoveredPack | None:
        manifestPath = packDirectory / "manifest.toml"
        if not manifestPath.is_file():
            return None

        manifest = loadManifest(manifestPath)
        entryPath = packDirectory / manifest.entry
        if not entryPath.is_file():
            raise PackDiscoveryError(
                code="missing-entry-file",
                reason=f"找不到入口文件: {manifest.entry}",
                packId=manifest.id,
                path=entryPath,
            )

        return DiscoveredPack(
            manifest=manifest,
            directory=packDirectory,
            manifestPath=manifestPath,
            entryPath=entryPath,
        )

    def _sortDiscoveredPacksByDependencies(
        self,
        discoveredPacks: list[DiscoveredPack],
    ) -> list[DiscoveredPack]:
        discoveredById: dict[str, DiscoveredPack] = {}
        for discoveredPack in discoveredPacks:
            packId = discoveredPack.manifest.id
            if packId in discoveredById:
                raise PackDiscoveryError(
                    code="duplicate-pack-id",
                    reason=f"重复的 pack id: {packId}",
                    packId=packId,
                    path=discoveredPack.manifestPath,
                )
            discoveredById[packId] = discoveredPack

        orderedPacks: list[DiscoveredPack] = []
        visiting: list[str] = []
        visited: set[str] = set()

        def visit(packId: str) -> None:
            if packId in visited:
                return
            if packId in visiting:
                cycleStart = visiting.index(packId)
                cyclePath = visiting[cycleStart:] + [packId]
                raise PackDiscoveryError(
                    code="dependency-cycle",
                    reason=f"检测到 Pack 循环依赖: {' -> '.join(cyclePath)}",
                    packId=packId,
                    path=discoveredById[packId].manifestPath,
                )

            discoveredPack = discoveredById[packId]
            visiting.append(packId)
            for dependencyId in discoveredPack.manifest.dependencies:
                if dependencyId not in discoveredById:
                    raise PackDiscoveryError(
                        code="missing-dependency",
                        reason=f"依赖的 Pack 不存在: {dependencyId}",
                        packId=packId,
                        path=discoveredPack.manifestPath,
                    )
                visit(dependencyId)

            _ = visiting.pop()
            visited.add(packId)
            orderedPacks.append(discoveredPack)

        for discoveredPack in discoveredPacks:
            visit(discoveredPack.manifest.id)

        return orderedPacks

    def _cacheDiscoveredPacks(self, discoveredPacks: list[DiscoveredPack] | tuple[()]) -> None:
        self._discoveredPacksById = {
            discoveredPack.manifest.id: discoveredPack
            for discoveredPack in discoveredPacks
        }
        self._packOrder = tuple(discoveredPack.manifest.id for discoveredPack in discoveredPacks)

    def _orderedDiscoveredPacks(self) -> list[DiscoveredPack]:
        if not self._packOrder:
            _ = self.discoverPacks()

        return [self._discoveredPacksById[packId] for packId in self._packOrder]

    def _loadPack(self, discoveredPack: DiscoveredPack) -> LoadedPack:
        moduleName = self._moduleNameForPack(discoveredPack.manifest.id)
        self._unloadModuleTree(moduleName)

        spec = importlib.util.spec_from_file_location(
            moduleName,
            discoveredPack.entryPath,
            submodule_search_locations=[str(discoveredPack.directory)],
        )
        if spec is None or spec.loader is None:
            raise PackLoadError(
                code="module-spec-failed",
                reason="无法创建 Pack 模块规格",
                packId=discoveredPack.manifest.id,
                path=discoveredPack.entryPath,
            )

        module = importlib.util.module_from_spec(spec)
        try:
            sys.modules[moduleName] = module
            spec.loader.exec_module(module)
        except Exception as error:
            self._unloadModuleTree(moduleName)
            raise PackLoadError(
                code="module-load-failed",
                reason=self._describeException(error),
                packId=discoveredPack.manifest.id,
                path=discoveredPack.entryPath,
            ) from error

        try:
            packClass = self._findPackClass(module=module, discoveredPack=discoveredPack)
            packInstance = packClass()
            self._bindManifest(packInstance=packInstance, discoveredPack=discoveredPack)
        except PackLoadError:
            self._unloadModuleTree(moduleName)
            raise
        except Exception as error:
            self._unloadModuleTree(moduleName)
            raise PackLoadError(
                code="pack-init-failed",
                reason=self._describeException(error),
                packId=discoveredPack.manifest.id,
                path=discoveredPack.entryPath,
            ) from error

        return LoadedPack(
            manifest=discoveredPack.manifest,
            directory=discoveredPack.directory,
            manifestPath=discoveredPack.manifestPath,
            entryPath=discoveredPack.entryPath,
            moduleName=moduleName,
            module=module,
            packClass=packClass,
            pack=packInstance,
        )

    def _findPackClass(
        self,
        *,
        module: ModuleType,
        discoveredPack: DiscoveredPack,
    ) -> type[FeaturePack]:
        packClasses = [
            attr
            for attr in vars(module).values()
            if (
                isinstance(attr, type)
                and issubclass(attr, FeaturePack)
                and attr is not FeaturePack
                and attr.__module__ == module.__name__
            )
        ]
        if not packClasses:
            raise PackLoadError(
                code="missing-pack-class",
                reason="入口模块中未找到新版 FeaturePack 子类",
                packId=discoveredPack.manifest.id,
                path=discoveredPack.entryPath,
            )
        if len(packClasses) > 1:
            classNames = ", ".join(sorted(packClass.__name__ for packClass in packClasses))
            raise PackLoadError(
                code="multiple-pack-classes",
                reason=f"入口模块中存在多个 FeaturePack 子类: {classNames}",
                packId=discoveredPack.manifest.id,
                path=discoveredPack.entryPath,
            )
        return packClasses[0]

    def _bindManifest(
        self,
        *,
        packInstance: FeaturePack,
        discoveredPack: DiscoveredPack,
    ) -> None:
        manifest = discoveredPack.manifest
        existingManifest = getattr(packInstance, "manifest", None)
        if existingManifest is None:
            setattr(type(packInstance), "manifest", manifest)
            return
        if not isinstance(existingManifest, Manifest):
            raise PackLoadError(
                code="invalid-pack-manifest",
                reason="Pack.manifest 必须是 Manifest 或保持未设置",
                packId=manifest.id,
                path=discoveredPack.entryPath,
            )
        if existingManifest != manifest:
            raise PackLoadError(
                code="manifest-mismatch",
                reason="Pack.manifest 与 manifest.toml 不一致",
                packId=manifest.id,
                path=discoveredPack.entryPath,
            )

    def _installLoadedPack(self, loadedPack: LoadedPack, window: object) -> None:
        try:
            loadedPack.pack.install(window)
        except Exception as error:
            raise PackLoadError(
                code="pack-install-failed",
                reason=self._describeException(error),
                packId=loadedPack.manifest.id,
                path=loadedPack.entryPath,
            ) from error

    def _moduleNameForPack(self, packId: str) -> str:
        safePackId = "".join(
            character if character.isalnum() or character == "_" else "_"
            for character in packId
        )
        return f"_ghost_feature_pack_{safePackId}"

    def _describeException(self, error: BaseException) -> str:
        message = str(error).strip()
        if not message:
            return error.__class__.__name__
        return f"{error.__class__.__name__}: {message}"

    def _unloadPackModuleTrees(self, loadedPacks: list[LoadedPack]) -> None:
        for loadedPack in loadedPacks:
            self._unloadModuleTree(loadedPack.moduleName)

    def _unloadModuleTree(self, moduleName: str) -> None:
        moduleKeys = [
            loadedModuleName
            for loadedModuleName in sys.modules
            if loadedModuleName == moduleName or loadedModuleName.startswith(f"{moduleName}.")
        ]
        for loadedModuleName in moduleKeys:
            _ = sys.modules.pop(loadedModuleName, None)

    def _cacheLoadedPacks(self, loadedPacks: list[LoadedPack] | tuple[()]) -> None:
        self._loadedPacksById = {
            loadedPack.manifest.id: loadedPack
            for loadedPack in loadedPacks
        }
        self._loadedPackOrder = tuple(loadedPack.manifest.id for loadedPack in loadedPacks)

    def _routeLoadedPack(
        self,
        matcher: Callable[[FeaturePack], bool],
    ) -> FeaturePack | None:
        firstMatchedPack: FeaturePack | None = None
        prioritizedMatch: tuple[int, int, FeaturePack] | None = None

        for index, packId in enumerate(self._loadedPackOrder):
            loadedPack = self._loadedPacksById[packId]
            try:
                if not matcher(loadedPack.pack):
                    continue
            except Exception:
                continue

            if firstMatchedPack is None:
                firstMatchedPack = loadedPack.pack

            priority = getattr(loadedPack.pack, "priority", None)
            if isinstance(priority, bool) or not isinstance(priority, int):
                continue

            if prioritizedMatch is None or (priority, -index) > (prioritizedMatch[0], -prioritizedMatch[1]):
                prioritizedMatch = (priority, index, loadedPack.pack)

        if prioritizedMatch is not None:
            return prioritizedMatch[2]

        return firstMatchedPack


__all__ = [
    "DefaultFeatureService",
    "DefaultSettingsInstaller",
    "DefaultTaskEditor",
    "FeatureService",
    "InstalledSettingSection",
    "PackDiscoveryError",
    "PackLoadError",
    "SettingsInstaller",
    "TaskEditor",
]
