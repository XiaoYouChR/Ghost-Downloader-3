# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportAny=false, reportImplicitOverride=false, reportMissingParameterType=false, reportMissingTypeStubs=false, reportUnusedCallResult=false

"""Default host dialogs for Feature Pack V1."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from pathlib import PurePosixPath
import re
from typing import final

from PySide6.QtCore import QFileInfo
from PySide6.QtCore import QSignalBlocker
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView
from PySide6.QtWidgets import QFileDialog
from PySide6.QtWidgets import QFileIconProvider
from PySide6.QtWidgets import QFormLayout
from PySide6.QtWidgets import QHeaderView
from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget
from PySide6.QtWidgets import QDialog
from qfluentwidgets import Action
from qfluentwidgets import BodyLabel
from qfluentwidgets import CaptionLabel
from qfluentwidgets import ComboBox
from qfluentwidgets import DropDownPushButton
from qfluentwidgets import FluentIcon
from qfluentwidgets import InfoBar
from qfluentwidgets import LineEdit
from qfluentwidgets import MessageBoxBase
from qfluentwidgets import SpinBox
from qfluentwidgets import SubtitleLabel
from qfluentwidgets import ToolButton
from qfluentwidgets import PrimaryPushButton
from qfluentwidgets import PushButton
from qfluentwidgets import RoundMenu

from app.supports.utils import getReadableSize
from app.view.components.editors import AutoSizingEdit
from app.view.components.tree_view import AutoSizingTreeView

from ..api.config import TaskConfig
from ..api.form import EditMode
from ..api.form import FormField
from ..api.form import TaskForm
from ..api.task import MultiFileTask
from ..api.task import Task

_MAPPING_LINE_PATTERN = re.compile(r"^\s*([^:=\s][^:=]*?)\s*[:=]\s*(.*)$")
_CONFIG_KEYS = frozenset({"source", "folder", "name", "headers", "proxies", "chunks"})
_REQUIRED_KEYS = frozenset({"source", "folder", "name"})


@final
class MultiFileSelectDialog(MessageBoxBase):
    """Default tree-based selector for ``MultiFileTask.files``."""

    _FILE_TYPE_RULES = (
        ("video", "视频", FluentIcon.VIDEO, {
            ".avi", ".flv", ".m2ts", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".rmvb", ".ts", ".webm", ".wmv",
        }),
        ("audio", "音频", FluentIcon.MUSIC, {
            ".aac", ".ape", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav", ".wma",
        }),
        ("image", "图片", FluentIcon.PHOTO, {
            ".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".tif", ".tiff", ".webp",
        }),
        ("subtitle", "字幕", FluentIcon.CHAT, {
            ".ass", ".idx", ".lrc", ".psb", ".smi", ".srt", ".ssa", ".sub", ".sup", ".vtt",
        }),
        ("document", "文档", FluentIcon.DOCUMENT, {
            ".chm", ".csv", ".doc", ".docx", ".epub", ".md", ".nfo", ".odt", ".pdf", ".ppt", ".pptx", ".rtf",
            ".txt", ".xls", ".xlsx",
        }),
        ("archive", "压缩包", FluentIcon.ZIP_FOLDER, {
            ".001", ".7z", ".bz2", ".cab", ".gz", ".iso", ".rar", ".tar", ".tbz2", ".tgz", ".xz", ".zip", ".zst",
            ".tar.bz2", ".tar.gz", ".tar.xz", ".tar.zst",
        }),
        ("application", "程序", FluentIcon.APPLICATION, {
            ".apk", ".appimage", ".bat", ".com", ".deb", ".dmg", ".exe", ".iso", ".jar", ".msi", ".pkg", ".rpm",
            ".sh",
        }),
    )
    _FILE_TYPE_META: dict[str, tuple[str, FluentIcon]] = {
        key: (label, icon)
        for key, label, icon, _ in _FILE_TYPE_RULES
    }
    _FILE_TYPE_SUFFIXES: dict[str, set[str]] = {
        key: suffixes
        for key, _, _, suffixes in _FILE_TYPE_RULES
    }

    @classmethod
    def _fileSuffix(cls, path: str) -> str:
        suffixes = [suffix.lower() for suffix in PurePosixPath(path).suffixes]
        if not suffixes:
            return ""
        if len(suffixes) > 1:
            combined = "".join(suffixes[-2:])
            if combined in cls._FILE_TYPE_SUFFIXES["archive"]:
                return combined
        return suffixes[-1]

    @classmethod
    def _fileType(cls, path: str) -> str:
        suffix = cls._fileSuffix(path)
        for key, _, _, suffixes in cls._FILE_TYPE_RULES:
            if suffix in suffixes:
                return key
        return "other"

    def __init__(
        self,
        *,
        task: MultiFileTask,
        title: str = "选择内容",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.task: MultiFileTask = task
        self._fileItems: dict[str, QStandardItem] = {}

        self.titleLabel: SubtitleLabel = SubtitleLabel(title, self.widget)
        self.summaryLabel: BodyLabel = BodyLabel("", self.widget)
        self.treeView: AutoSizingTreeView = AutoSizingTreeView(self.widget)
        self.treeModel: QStandardItemModel = QStandardItemModel(self.treeView)
        self.actionsWidget: QWidget = QWidget(self.widget)
        self.actionsLayout: QHBoxLayout = QHBoxLayout(self.actionsWidget)
        self.selectAllButton: PrimaryPushButton = PrimaryPushButton(self.tr("全选"), self.actionsWidget)
        self.clearButton: PushButton = PushButton(self.tr("全不选"), self.actionsWidget)
        self.invertButton: PushButton = PushButton(self.tr("反选"), self.actionsWidget)
        self.selectByTypeButton: DropDownPushButton = DropDownPushButton(self.tr("按类型选择"), self.actionsWidget)
        self.selectByTypeMenu: RoundMenu = RoundMenu(parent=self)

        self._initWidget()
        self._buildTree()
        self._updateSummary()

    def _initWidget(self) -> None:
        self.setObjectName("MultiFileSelectDialog")
        self.widget.setMinimumSize(720, 520)
        self.yesButton.setText(self.tr("应用"))
        self.cancelButton.setText(self.tr("取消"))

        self.treeModel.setHorizontalHeaderLabels(
            [self.tr("内容"), self.tr("大小"), self.tr("备注")]
        )
        self.treeView.setModel(self.treeModel)
        self.treeView.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.treeView.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.treeView.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.treeView.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.treeModel.itemChanged.connect(self._onItemChanged)

        self.actionsLayout.setContentsMargins(0, 0, 0, 0)
        self.actionsLayout.setSpacing(8)
        self.actionsLayout.addWidget(self.selectAllButton)
        self.actionsLayout.addWidget(self.clearButton)
        self.actionsLayout.addWidget(self.invertButton)
        self.actionsLayout.addWidget(self.selectByTypeButton)
        self.actionsLayout.addStretch(1)

        _ = self.selectAllButton.clicked.connect(self._selectAll)
        _ = self.clearButton.clicked.connect(self._clearAll)
        _ = self.invertButton.clicked.connect(self._invertSelection)
        self._initTypeMenu()

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.summaryLabel)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.treeView)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.actionsWidget)

    def _buildTree(self) -> None:
        folderItems: dict[tuple[str, ...], QStandardItem] = {}
        provider = QFileIconProvider()
        root = self.treeModel.invisibleRootItem()

        for taskFile in self.task.files:
            path = PurePosixPath(taskFile.path)
            parts = path.parts if path.parts else (taskFile.path,)
            parent = root
            prefix: list[str] = []

            for part in parts[:-1]:
                prefix.append(part)
                key = tuple(prefix)
                item = folderItems.get(key)
                if item is None:
                    item = QStandardItem(part)
                    item.setEditable(False)
                    item.setCheckable(True)
                    item.setCheckState(Qt.CheckState.Unchecked)
                    item.setIcon(provider.icon(QFileIconProvider.IconType.Folder))
                    sizeItem = QStandardItem("")
                    noteItem = QStandardItem("")
                    sizeItem.setEditable(False)
                    noteItem.setEditable(False)
                    parent.appendRow([item, sizeItem, noteItem])
                    folderItems[key] = item
                parent = item

            name = parts[-1] if parts else taskFile.path
            item = QStandardItem(name)
            item.setEditable(False)
            item.setCheckable(True)
            item.setCheckState(Qt.CheckState.Checked if taskFile.selected else Qt.CheckState.Unchecked)
            item.setIcon(provider.icon(QFileInfo(name)))
            item.setToolTip(taskFile.path)

            sizeItem = QStandardItem(getReadableSize(taskFile.size))
            sizeItem.setEditable(False)

            noteItem = QStandardItem(taskFile.note)
            noteItem.setEditable(False)
            if taskFile.note:
                noteItem.setToolTip(taskFile.note)

            parent.appendRow([item, sizeItem, noteItem])
            self._fileItems[taskFile.id] = item

        with QSignalBlocker(self.treeModel):
            for row in range(root.rowCount()):
                child = root.child(row)
                self._syncBranchCheckState(child)

        self.treeView.expandAll()
        self.treeView.resizeColumnToContents(0)
        self.treeView.resizeColumnToContents(1)

    def _initTypeMenu(self) -> None:
        for typeKey, count in self._availableFileTypes().items():
            label, icon = self._FILE_TYPE_META.get(typeKey, (self.tr("其他"), FluentIcon.FOLDER))
            action = Action(icon, self.tr("仅选{0} ({1})").format(self.tr(label), count), self)
            _ = action.triggered.connect(self._makeTypeSelectionHandler(typeKey))
            self.selectByTypeMenu.addAction(action)

        self.selectByTypeButton.setMenu(self.selectByTypeMenu)
        self.selectByTypeButton.setEnabled(bool(self.selectByTypeMenu.actions()))

    def _makeTypeSelectionHandler(self, typeKey: str) -> Callable[[bool], None]:
        def handleTypeSelection(_checked: bool) -> None:
            self._selectOnlyFileType(typeKey)

        return handleTypeSelection

    def _syncBranchCheckState(self, item: QStandardItem) -> Qt.CheckState:
        if item.rowCount() == 0:
            return item.checkState()

        states = [self._syncBranchCheckState(item.child(row)) for row in range(item.rowCount())]
        if states and all(state == Qt.CheckState.Checked for state in states):
            item.setCheckState(Qt.CheckState.Checked)
        elif states and all(state == Qt.CheckState.Unchecked for state in states):
            item.setCheckState(Qt.CheckState.Unchecked)
        else:
            item.setCheckState(Qt.CheckState.PartiallyChecked)
        return item.checkState()

    def _syncAncestorCheckStates(self, item: QStandardItem | None) -> None:
        while item is not None:
            states = [item.child(row).checkState() for row in range(item.rowCount())]
            if states and all(state == Qt.CheckState.Checked for state in states):
                item.setCheckState(Qt.CheckState.Checked)
            elif states and all(state == Qt.CheckState.Unchecked for state in states):
                item.setCheckState(Qt.CheckState.Unchecked)
            else:
                item.setCheckState(Qt.CheckState.PartiallyChecked)
            item = item.parent()

    def _setChildrenCheckState(self, item: QStandardItem, state: Qt.CheckState) -> None:
        for row in range(item.rowCount()):
            child = item.child(row)
            child.setCheckState(state)
            self._setChildrenCheckState(child, state)

    def _availableFileTypes(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for taskFile in self.task.files:
            typeKey = self._fileType(taskFile.path)
            counts[typeKey] = counts.get(typeKey, 0) + 1
        return counts

    def _collectSelectedIds(self) -> set[str]:
        return {
            taskFile.id
            for taskFile in self.task.files
            if self._fileItems[taskFile.id].checkState() == Qt.CheckState.Checked
        }

    def _setSelectedIds(self, selectedIds: set[str]) -> None:
        root = self.treeModel.invisibleRootItem()
        with QSignalBlocker(self.treeModel):
            for taskFile in self.task.files:
                item = self._fileItems[taskFile.id]
                state = (
                    Qt.CheckState.Checked
                    if taskFile.id in selectedIds
                    else Qt.CheckState.Unchecked
                )
                item.setCheckState(state)
            for row in range(root.rowCount()):
                child = root.child(row)
                self._syncBranchCheckState(child)
        self._updateSummary()

    def setSelectedIds(self, selectedIds: set[str]) -> None:
        """Replace the current selection using stable ``TaskFile.id`` values."""
        self._setSelectedIds(selectedIds)

    def _updateSummary(self) -> None:
        selectedIds = self._collectSelectedIds()
        selectedFiles = [
            taskFile
            for taskFile in self.task.files
            if taskFile.id in selectedIds
        ]
        self.summaryLabel.setText(
            self.tr("已选择 {0}/{1} 项，共 {2}").format(
                len(selectedFiles),
                self.task.fileCount,
                getReadableSize(sum(taskFile.size for taskFile in selectedFiles)),
            )
        )

    def _onItemChanged(self, item: QStandardItem) -> None:
        if item.column() != 0:
            return

        with QSignalBlocker(self.treeModel):
            if item.rowCount() > 0 and item.checkState() != Qt.CheckState.PartiallyChecked:
                self._setChildrenCheckState(item, item.checkState())
            self._syncAncestorCheckStates(item.parent())
        self._updateSummary()
        self.treeView.viewport().update()

    def _selectAll(self) -> None:
        self._setSelectedIds({taskFile.id for taskFile in self.task.files})
        self.treeView.viewport().update()

    def _clearAll(self) -> None:
        self._setSelectedIds(set())
        self.treeView.viewport().update()

    def _invertSelection(self) -> None:
        currentSelected = self._collectSelectedIds()
        self._setSelectedIds({
            taskFile.id
            for taskFile in self.task.files
            if taskFile.id not in currentSelected
        })
        self.treeView.viewport().update()

    def _selectOnlyFileType(self, typeKey: str) -> None:
        self._setSelectedIds({
            taskFile.id
            for taskFile in self.task.files
            if self._fileType(taskFile.path) == typeKey
        })
        self.treeView.viewport().update()

    def validate(self) -> bool:
        if self._collectSelectedIds():
            return True

        _ = InfoBar.warning(
            self.tr("至少保留一项"),
            self.tr("当前没有任何条目被勾选"),
            parent=self,
        )
        return False

    def selectedIds(self) -> set[str]:
        return self._collectSelectedIds()


@final
class TaskConfigDialog(MessageBoxBase):
    """Default dialog that edits ``TaskConfig`` from a declarative ``TaskForm``."""

    def __init__(
        self,
        *,
        task: Task,
        form: TaskForm,
        mode: EditMode,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.task: Task = task
        self.form: TaskForm = form
        self.mode: EditMode = mode
        self._fieldReaders: dict[str, Callable[[], object]] = {}
        self._selectedIds: set[str] = (
            set(task.selectedIds)
            if isinstance(task, MultiFileTask)
            else set()
        )

        self.titleLabel: SubtitleLabel = SubtitleLabel(form.title, self.widget)
        self.formWidget: QWidget = QWidget(self.widget)
        self.formLayout: QFormLayout = QFormLayout(self.formWidget)
        self.emptyLabel: BodyLabel = BodyLabel(self.tr("当前没有可编辑字段"), self.widget)

        self._initWidget()
        self._buildFields()

    def _initWidget(self) -> None:
        self.setObjectName("TaskConfigDialog")
        self.widget.setMinimumWidth(560)
        self.yesButton.setText(self.tr("应用"))
        self.cancelButton.setText(self.tr("取消"))

        self.formLayout.setContentsMargins(0, 0, 0, 0)
        self.formLayout.setSpacing(12)
        self.formLayout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        self.formLayout.setLabelAlignment(self.formLayout.labelAlignment())

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.formWidget)
        self.viewLayout.addWidget(self.emptyLabel)
        self.emptyLabel.hide()

    def _buildFields(self) -> None:
        visibleFields = [field for field in self.form.fields if self.mode in field.modes]
        if not visibleFields:
            self.formWidget.hide()
            self.emptyLabel.show()
            return

        for field in visibleFields:
            editorWidget, readValue = self._createFieldEditor(field)
            self._fieldReaders[field.key] = readValue

            rowWidget = self._wrapFieldWithNote(field, editorWidget)
            label = BodyLabel(field.label, self.formWidget)
            label.setObjectName(f"taskConfigLabel:{field.key}")
            self.formLayout.addRow(label, rowWidget)

    def _wrapFieldWithNote(self, field: FormField, editorWidget: QWidget) -> QWidget:
        if not field.note:
            return editorWidget

        container = QWidget(self.formWidget)
        container.setObjectName(f"taskConfigField:{field.key}")
        containerLayout = QVBoxLayout(container)
        containerLayout.setContentsMargins(0, 0, 0, 0)
        containerLayout.setSpacing(6)
        containerLayout.addWidget(editorWidget)

        noteLabel = CaptionLabel(field.note, container)
        noteLabel.setWordWrap(True)
        noteLabel.setObjectName(f"taskConfigNote:{field.key}")
        containerLayout.addWidget(noteLabel)
        return container

    def _createFieldEditor(self, field: FormField) -> tuple[QWidget, Callable[[], object]]:
        if field.kind == "files":
            return self._createFilesEditor(field)

        if field.key not in _CONFIG_KEYS:
            raise ValueError(f"Unsupported task config field key: {field.key}")

        currentValue = getattr(self.task.config, field.key)

        if field.kind == "text":
            lineEdit = LineEdit(self.formWidget)
            lineEdit.setObjectName(f"taskConfigInput:{field.key}")
            lineEdit.setClearButtonEnabled(True)
            lineEdit.setPlaceholderText(field.placeholder)
            lineEdit.setText(str(currentValue))
            return lineEdit, lineEdit.text

        if field.kind == "folder":
            return self._createFolderEditor(field, currentValue)

        if field.kind == "headers":
            editor = AutoSizingEdit(self.formWidget, minimumVisibleLines=3)
            editor.setObjectName(f"taskConfigInput:{field.key}")
            editor.setPlaceholderText(field.placeholder)
            editor.setPlainText(self._formatMapping(currentValue))
            return editor, lambda: self._parseMapping(editor.toPlainText(), emptyValue={})

        if field.kind == "proxy":
            editor = AutoSizingEdit(self.formWidget, minimumVisibleLines=3)
            editor.setObjectName(f"taskConfigInput:{field.key}")
            editor.setPlaceholderText(field.placeholder)
            editor.setPlainText(self._formatMapping(currentValue))
            return editor, lambda: self._parseMapping(editor.toPlainText(), emptyValue=None)

        if field.kind == "int":
            spinBox = SpinBox(self.formWidget)
            spinBox.setObjectName(f"taskConfigInput:{field.key}")
            minimum = field.min if field.min is not None else (1 if field.key == "chunks" else 0)
            maximum = field.max if field.max is not None else 1_000_000
            spinBox.setRange(minimum, maximum)
            spinBox.setSingleStep(field.step)
            spinBox.setValue(int(currentValue))
            return spinBox, spinBox.value

        if field.kind == "choice":
            comboBox = ComboBox(self.formWidget)
            comboBox.setObjectName(f"taskConfigInput:{field.key}")
            comboBox.setPlaceholderText(field.placeholder)
            currentText = str(currentValue)
            if currentText and currentText not in {choice.value for choice in field.choices}:
                comboBox.addItem(currentText, userData=currentText)
            for choice in field.choices:
                comboBox.addItem(choice.label, userData=choice.value)

            currentIndex = self._comboBoxIndexByValue(comboBox, currentText)
            if currentIndex >= 0:
                comboBox.setCurrentIndex(currentIndex)
            return comboBox, comboBox.currentData

        raise ValueError(f"Unsupported field kind for task config dialog: {field.kind}")

    def _createFolderEditor(
        self,
        field: FormField,
        currentValue: object,
    ) -> tuple[QWidget, Callable[[], object]]:
        container = QWidget(self.formWidget)
        container.setObjectName(f"taskConfigField:{field.key}")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        lineEdit = LineEdit(container)
        lineEdit.setObjectName(f"taskConfigInput:{field.key}")
        lineEdit.setClearButtonEnabled(True)
        lineEdit.setPlaceholderText(field.placeholder)
        lineEdit.setText(str(currentValue))

        browseButton = ToolButton(FluentIcon.FOLDER, container)
        browseButton.setObjectName(f"taskConfigBrowse:{field.key}")
        browseButton.setToolTip(self.tr("选择文件夹"))
        _ = browseButton.clicked.connect(lambda: self._chooseFolder(lineEdit))

        layout.addWidget(lineEdit, 1)
        layout.addWidget(browseButton)
        return container, lineEdit.text

    def _createFilesEditor(self, field: FormField) -> tuple[QWidget, Callable[[], object]]:
        if not isinstance(self.task, MultiFileTask):
            raise TypeError("files field requires MultiFileTask")

        container = QWidget(self.formWidget)
        container.setObjectName(f"taskConfigField:{field.key}")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        summaryLabel = BodyLabel(self._fileSummaryText(), container)
        summaryLabel.setObjectName(f"taskConfigInput:{field.key}")

        selectButton = PrimaryPushButton(self.tr("选择"), container)
        selectButton.setObjectName(f"taskConfigAction:{field.key}")
        _ = selectButton.clicked.connect(
            lambda: self._openMultiFileSelector(field.label, summaryLabel)
        )

        layout.addWidget(summaryLabel, 1)
        layout.addWidget(selectButton)
        return container, lambda: set(self._selectedIds)

    def _openMultiFileSelector(self, title: str, summaryLabel: BodyLabel) -> None:
        if not isinstance(self.task, MultiFileTask):
            return

        dialog = MultiFileSelectDialog(
            task=self.task,
            title=title,
            parent=self,
        )
        dialog.setSelectedIds(self._selectedIds)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._selectedIds = dialog.selectedIds()
            summaryLabel.setText(self._fileSummaryText())

    def _chooseFolder(self, lineEdit: LineEdit) -> None:
        currentText = lineEdit.text().strip()
        browseRoot = self._browseRoot(currentText)
        selectedPath = QFileDialog.getExistingDirectory(
            self,
            self.tr("选择文件夹"),
            str(browseRoot),
        )
        if selectedPath:
            lineEdit.setText(selectedPath)

    def _browseRoot(self, currentText: str) -> Path:
        if not currentText:
            return Path.cwd()

        currentPath = Path(currentText)
        if currentPath.exists():
            return currentPath.absolute()
        if currentPath.parent != currentPath:
            return currentPath.parent
        return Path.cwd()

    def _fileSummaryText(self) -> str:
        if not isinstance(self.task, MultiFileTask):
            return self.tr("当前任务不支持多项选择")

        return self.tr("已保留 {0}/{1} 项选择").format(
            len(self._selectedIds),
            self.task.fileCount,
        )

    def _comboBoxIndexByValue(self, comboBox: ComboBox, value: str) -> int:
        for index in range(comboBox.count()):
            if str(comboBox.itemData(index)) == value:
                return index
        return -1

    def _formatMapping(self, value: object) -> str:
        if not value:
            return ""
        if not isinstance(value, dict):
            raise TypeError("Mapping fields require dict values")
        return "\n".join(f"{key}: {itemValue}" for key, itemValue in value.items())

    def _parseMapping(
        self,
        text: str,
        *,
        emptyValue: dict[str, str] | None,
    ) -> dict[str, str] | None:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return emptyValue

        parsed: dict[str, str] = {}
        for lineNumber, line in enumerate(lines, start=1):
            match = _MAPPING_LINE_PATTERN.fullmatch(line)
            if match is None:
                raise ValueError(
                    self.tr("第 {0} 行格式无效，应使用 key: value").format(lineNumber)
                )

            key = match.group(1).strip()
            value = match.group(2).strip()
            if not key:
                raise ValueError(
                    self.tr("第 {0} 行缺少键名").format(lineNumber)
                )
            parsed[key] = value

        return parsed

    def config(self) -> TaskConfig:
        values: dict[str, object] = {
            "source": self.task.config.source,
            "folder": self.task.config.folder,
            "name": self.task.config.name,
            "headers": self.task.config.headers,
            "proxies": self.task.config.proxies,
            "chunks": self.task.config.chunks,
        }

        for key, readValue in self._fieldReaders.items():
            if key == "files":
                continue
            values[key] = readValue()

        normalizedValues = {
            "source": self._normalizeTextValue("source", values["source"]),
            "folder": self._normalizeFolderValue(values["folder"]),
            "name": self._normalizeTextValue("name", values["name"]),
            "headers": self._normalizeHeadersValue(values["headers"]),
            "proxies": self._normalizeProxiesValue(values["proxies"]),
            "chunks": self._normalizeChunksValue(values["chunks"]),
        }
        return replace(self.task.config, **normalizedValues)

    def selectedIds(self) -> set[str]:
        return set(self._selectedIds)

    def validate(self) -> bool:
        try:
            _ = self.config()
        except (TypeError, ValueError) as error:
            _ = InfoBar.error(
                self.tr("配置无效"),
                str(error),
                parent=self,
            )
            return False

        if "files" in self._fieldReaders and not self.selectedIds():
            _ = InfoBar.warning(
                self.tr("至少保留一项"),
                self.tr("当前没有任何条目被保留"),
                parent=self,
            )
            return False

        return True

    def _normalizeTextValue(self, key: str, value: object) -> str:
        text = "" if value is None else str(value).strip()
        if key in _REQUIRED_KEYS and not text:
            raise ValueError(self.tr("{0}不能为空").format(key))
        return text

    def _normalizeFolderValue(self, value: object) -> Path:
        if isinstance(value, Path):
            folder = value
        else:
            text = str(value).strip()
            if not text:
                raise ValueError(self.tr("folder不能为空"))
            folder = Path(text)
        return folder

    def _normalizeHeadersValue(self, value: object) -> dict[str, str]:
        if isinstance(value, dict):
            return {str(key): str(itemValue) for key, itemValue in value.items()}
        raise TypeError("headers must be a dict[str, str]")

    def _normalizeProxiesValue(self, value: object) -> dict[str, str] | None:
        if value is None:
            return None
        if isinstance(value, dict):
            return {str(key): str(itemValue) for key, itemValue in value.items()}
        raise TypeError("proxies must be a dict[str, str] | None")

    def _normalizeChunksValue(self, value: object) -> int:
        if isinstance(value, int):
            chunks = value
        elif isinstance(value, str):
            strippedValue = value.strip()
            if not strippedValue:
                raise ValueError(self.tr("chunks不能为空"))
            chunks = int(strippedValue)
        else:
            raise TypeError("chunks must be an int")
        if chunks < 1:
            raise ValueError(self.tr("chunks必须大于0"))
        return chunks

__all__ = ["MultiFileSelectDialog", "TaskConfigDialog"]
