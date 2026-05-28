from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    FluentIcon,
    IconWidget,
    LineEdit,
    MessageBoxBase,
    PushButton,
    SettingCard,
    StrongBodyLabel,
    SubtitleLabel,
    ToolButton,
    ToolTipFilter,
    TransparentToolButton,
)

from app.supports.config import DEFAULT_USER_AGENT_PRESETS, cfg
from app.view.components.editors import AutoSizingEdit


class UserAgentSettingCard(SettingCard):
    def __init__(self, parent=None) -> None:
        super().__init__(
            FluentIcon.ROBOT,
            self.tr("默认 User-Agent"),
            self.tr("新建任务时填入请求标头的 User-Agent，可通过管理预设维护常用项"),
            parent,
        )
        # instant widget
        self.comboBox = ComboBox(self)
        self.manageButton = TransparentToolButton(FluentIcon.SETTING, self)

        self._initWidget()
        self._initLayout()
        self._bind()
        self._refreshComboBox()

    def _initWidget(self) -> None:
        self.comboBox.setMinimumWidth(220)
        self.manageButton.setToolTip(self.tr("管理 User-Agent 预设"))
        self.manageButton.installEventFilter(ToolTipFilter(self.manageButton))

    def _initLayout(self) -> None:
        self.hBoxLayout.addWidget(self.comboBox, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.manageButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def _bind(self) -> None:
        self.comboBox.currentIndexChanged.connect(self._onComboChanged)
        self.manageButton.clicked.connect(self._onManageClicked)
        cfg.userAgents.valueChanged.connect(self._refreshComboBox)
        cfg.activeUserAgent.valueChanged.connect(self._refreshComboBox)

    def _refreshComboBox(self) -> None:
        # 不需要 blockSignals: clear() 触发的 currentIndexChanged(-1) 走 _onComboChanged
        # 时 itemData 是 None 直接跳过; setCurrentIndex 之后即便回写 cfg 也是同值, 不会
        # 再次触发 valueChanged 形成环
        self.comboBox.clear()
        active = cfg.activeUserAgent.value
        activeIndex = 0
        for i, preset in enumerate(cfg.userAgents.value):
            name = preset.get("name", "")
            value = preset.get("value", "")
            if not name or not value:
                continue
            self.comboBox.addItem(name, userData=value)
            if value == active:
                activeIndex = i
        if self.comboBox.count() > 0:
            self.comboBox.setCurrentIndex(activeIndex)

    def _onComboChanged(self, index: int) -> None:
        value = self.comboBox.itemData(index)
        if value:
            cfg.set(cfg.activeUserAgent, value)

    def _onManageClicked(self) -> None:
        dialog = UserAgentPresetsDialog(self.window())
        dialog.exec()
        dialog.deleteLater()


_VALUE_PREVIEW_LIMIT = 48


class _UserAgentRowWidget(QWidget):
    def __init__(
        self,
        name: str,
        value: str,
        parent=None,
        *,
        onEdit: Callable[[str], None],
        onRemove: Callable[[str], None],
    ) -> None:
        super().__init__(parent)
        self._value = value
        self._onEdit = onEdit
        self._onRemove = onRemove

        preview = value if len(value) <= _VALUE_PREVIEW_LIMIT else f"{value[:_VALUE_PREVIEW_LIMIT]}..."

        # instant widget
        self.iconWidget = IconWidget(FluentIcon.ROBOT, self)
        self.nameLabel = StrongBodyLabel(name, self)
        self.valueLabel = BodyLabel(preview, self)
        self.editButton = ToolButton(FluentIcon.EDIT, self)
        self.removeButton = ToolButton(FluentIcon.DELETE, self)

        # instant layout
        self.hBoxLayout = QHBoxLayout(self)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.iconWidget.setFixedSize(16, 16)
        self.valueLabel.setStyleSheet("color: gray;")
        self.editButton.setToolTip(self.tr("编辑"))
        self.removeButton.setToolTip(self.tr("删除"))
        self.editButton.installEventFilter(ToolTipFilter(self.editButton))
        self.removeButton.installEventFilter(ToolTipFilter(self.removeButton))

    def _initLayout(self) -> None:
        self.hBoxLayout.setContentsMargins(8, 6, 8, 6)
        self.hBoxLayout.setSpacing(10)
        self.hBoxLayout.addWidget(self.iconWidget)
        self.hBoxLayout.addWidget(self.nameLabel)
        self.hBoxLayout.addWidget(self.valueLabel, 1)
        self.hBoxLayout.addWidget(self.editButton)
        self.hBoxLayout.addWidget(self.removeButton)

    def _bind(self) -> None:
        self.editButton.clicked.connect(lambda: self._onEdit(self._value))
        self.removeButton.clicked.connect(lambda: self._onRemove(self._value))


class _UserAgentEntryDialog(MessageBoxBase):
    def __init__(self, parent=None, *, name: str = "", value: str = "") -> None:
        super().__init__(parent)
        # instant widget
        self.titleLabel = SubtitleLabel(
            self.tr("编辑预设") if name or value else self.tr("添加预设"), self
        )
        self.nameLabel = BodyLabel(self.tr("名称"), self)
        self.nameEdit = LineEdit(self)
        self.valueLabel = BodyLabel(self.tr("User-Agent 字符串"), self)
        self.valueEdit = AutoSizingEdit(self, minimumVisibleLines=3, maximumVisibleLines=6)

        self._initWidget()
        self._initLayout()

        self.nameEdit.setText(name)
        self.valueEdit.setPlainText(value)

    def _initWidget(self) -> None:
        self.widget.setMinimumWidth(520)
        self.yesButton.setText(self.tr("保存"))
        self.cancelButton.setText(self.tr("取消"))
        self.nameEdit.setPlaceholderText(self.tr("如 Chrome 桌面 / iOS Safari"))
        self.valueEdit.setPlaceholderText(self.tr("粘贴完整的 User-Agent 字符串"))

    def _initLayout(self) -> None:
        self.viewLayout.setSpacing(6)
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.nameLabel)
        self.viewLayout.addWidget(self.nameEdit)
        self.viewLayout.addWidget(self.valueLabel)
        self.viewLayout.addWidget(self.valueEdit)

    def validate(self) -> bool:
        # MessageBoxBase 在 accept 前会调 validate, 返回 False 能阻止关闭
        return bool(
            self.nameEdit.text().strip()
            and self.valueEdit.toPlainText().strip()
        )

    def preset(self) -> dict:
        return {
            "name": self.nameEdit.text().strip(),
            "value": self.valueEdit.toPlainText().strip(),
        }


class UserAgentPresetsDialog(MessageBoxBase):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # instant widget
        self.titleRow = QWidget(self)
        self.titleLabel = SubtitleLabel(self.tr("管理 User-Agent 预设"), self.titleRow)
        self.resetButton = PushButton(FluentIcon.SYNC, self.tr("恢复默认"), self.titleRow)
        self.addButton = PushButton(FluentIcon.ADD, self.tr("添加预设"), self.titleRow)
        self.rowsContainer = QWidget(self)

        # instant layout
        self.titleRowLayout = QHBoxLayout(self.titleRow)
        self.rowsLayout = QVBoxLayout(self.rowsContainer)

        self._rowWidgets: list[_UserAgentRowWidget] = []

        self._initWidget()
        self._initLayout()
        self._bind()
        self._reload()

    def _initWidget(self) -> None:
        self.widget.setMinimumWidth(620)
        self.cancelButton.setText(self.tr("关闭"))
        # 把 yesButton 从 layout 拿走 cancelButton 才能撑满底部, 否则两个 stretch=1 各占一半
        self.buttonLayout.removeWidget(self.yesButton)
        self.yesButton.hide()

    def _initLayout(self) -> None:
        self.titleRowLayout.setContentsMargins(0, 0, 0, 0)
        self.titleRowLayout.setSpacing(8)
        self.titleRowLayout.addWidget(self.titleLabel)
        self.titleRowLayout.addStretch(1)
        self.titleRowLayout.addWidget(self.resetButton)
        self.titleRowLayout.addWidget(self.addButton)

        self.rowsLayout.setContentsMargins(0, 0, 0, 0)
        self.rowsLayout.setSpacing(0)

        self.viewLayout.setSpacing(10)
        self.viewLayout.addWidget(self.titleRow)
        self.viewLayout.addWidget(self.rowsContainer)

    def _bind(self) -> None:
        self.addButton.clicked.connect(self._onAddClicked)
        self.resetButton.clicked.connect(self._onResetClicked)
        cfg.userAgents.valueChanged.connect(self._reload)

    def _reload(self) -> None:
        for row in self._rowWidgets:
            self.rowsLayout.removeWidget(row)
            row.deleteLater()
        self._rowWidgets.clear()

        for preset in cfg.userAgents.value:
            name = preset.get("name", "")
            value = preset.get("value", "")
            if not name or not value:
                continue
            row = _UserAgentRowWidget(
                name,
                value,
                self,
                onEdit=self._onEditRequested,
                onRemove=self._onRemoveRequested,
            )
            self.rowsLayout.addWidget(row)
            self._rowWidgets.append(row)

    def _onAddClicked(self) -> None:
        dialog = _UserAgentEntryDialog(self.window())
        if dialog.exec():
            cfg.set(cfg.userAgents, [*cfg.userAgents.value, dialog.preset()])
        dialog.deleteLater()

    def _onResetClicked(self) -> None:
        cfg.set(cfg.userAgents, list(DEFAULT_USER_AGENT_PRESETS))
        cfg.set(cfg.activeUserAgent, DEFAULT_USER_AGENT_PRESETS[0]["value"])

    def _onEditRequested(self, value: str) -> None:
        target = next((p for p in cfg.userAgents.value if p.get("value") == value), None)
        if target is None:
            return
        dialog = _UserAgentEntryDialog(
            self.window(), name=target.get("name", ""), value=target.get("value", "")
        )
        if dialog.exec():
            updated = dialog.preset()
            presets = [
                updated if p.get("value") == value else p
                for p in cfg.userAgents.value
            ]
            cfg.set(cfg.userAgents, presets)
            if cfg.activeUserAgent.value == value:
                cfg.set(cfg.activeUserAgent, updated["value"])
        dialog.deleteLater()

    def _onRemoveRequested(self, value: str) -> None:
        presets = [p for p in cfg.userAgents.value if p.get("value") != value]
        cfg.set(cfg.userAgents, presets)
        if cfg.activeUserAgent.value == value:
            fallback = presets[0]["value"] if presets else ""
            cfg.set(cfg.activeUserAgent, fallback)
