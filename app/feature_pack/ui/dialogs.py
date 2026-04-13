# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportAny=false, reportImplicitOverride=false, reportMissingParameterType=false, reportMissingTypeStubs=false, reportUnusedCallResult=false

"""Default host dialogs for Feature Pack V1."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
import re
from typing import final

from PySide6.QtWidgets import QFileDialog
from PySide6.QtWidgets import QFormLayout
from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget
from qfluentwidgets import BodyLabel
from qfluentwidgets import CaptionLabel
from qfluentwidgets import ComboBox
from qfluentwidgets import FluentIcon
from qfluentwidgets import InfoBar
from qfluentwidgets import LineEdit
from qfluentwidgets import MessageBoxBase
from qfluentwidgets import SpinBox
from qfluentwidgets import SubtitleLabel
from qfluentwidgets import ToolButton

from app.view.components.editors import AutoSizingEdit

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

        summaryLabel = BodyLabel(self._fileSummaryText(), self.formWidget)
        summaryLabel.setObjectName(f"taskConfigInput:{field.key}")
        return summaryLabel, lambda: set(self._selectedIds)

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


__all__ = ["TaskConfigDialog"]
