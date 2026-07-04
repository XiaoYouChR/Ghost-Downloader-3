from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView
from qfluentwidgets import (
    BodyLabel, ComboBox, FluentIcon, MessageBoxBase,
    PrimaryPushButton, PushButton, SubtitleLabel,
    ToolTipFilter, TransparentToolButton,
)

from app.format import toReadableSize
from app.view.cards.draft_cards import UniversalDraftCard
from app.view.components.tree_view import AutoSizingTreeView
from .task import BilibiliTask, DownloadMode

MODE_LABELS = ("视频", "音频", "封面")


class BilibiliDraftCard(UniversalDraftCard):

    def _initWidget(self) -> None:
        super()._initWidget()
        self._modeCombo = ComboBox(self)
        self._modeCombo.setMinimumWidth(80)
        for label in MODE_LABELS:
            self._modeCombo.addItem(self.tr(label))
        self._modeCombo.setCurrentIndex(self.task.mode.value)

        self._subtitleChoices = self._buildSubtitleChoices()

        self._subtitleButton = TransparentToolButton(FluentIcon.LANGUAGE, self)
        self._subtitleButton.installEventFilter(ToolTipFilter(self._subtitleButton))
        self._subtitleButton.setToolTip(self.tr("选择字幕"))
        self._subtitleButton.setEnabled(bool(self._subtitleChoices))

        self._selectPagesButton = TransparentToolButton(FluentIcon.LIBRARY, self)
        self._selectPagesButton.installEventFilter(ToolTipFilter(self._selectPagesButton))
        self._selectPagesButton.setToolTip(self.tr("选择分P"))
        self._refreshButtonVisibility()

    def _initLayout(self) -> None:
        super()._initLayout()
        self.layout().addWidget(self._modeCombo)
        self.layout().addWidget(self._subtitleButton)
        self.layout().addWidget(self._selectPagesButton)

    def _bind(self) -> None:
        super()._bind()
        self._modeCombo.currentIndexChanged.connect(self._onModeChanged)
        self._subtitleButton.clicked.connect(self._onSubtitleClicked)
        self._selectPagesButton.clicked.connect(self._onSelectPagesClicked)

    def _onModeChanged(self, index: int) -> None:
        task: BilibiliTask = self._task
        task.setMode(DownloadMode(index))
        self._refreshSummary()

    def _onSubtitleClicked(self) -> None:
        task: BilibiliTask = self._task
        dialog = SubtitleSelectDialog(self._subtitleChoices, task.subtitleLanguages, self.window())
        if dialog.exec():
            task.setSubtitleLanguages(dialog.selectedLanguages())

    def _onSelectPagesClicked(self) -> None:
        task: BilibiliTask = self._task
        dialog = PageSelectDialog(task, self.window())
        if dialog.exec():
            selected = dialog.selectedPageNumbers()
            if selected:
                task.setPageSelection(selected)
                self._refreshSummary()

    def _refreshSummary(self) -> None:
        self.sizeLabel.setText(toReadableSize(self._task.fileSize))
        self.nameLabel.setText(self._task.name)
        self._refreshButtonVisibility()

    def _buildSubtitleChoices(self) -> list[tuple[str, str]]:
        seen: set[str] = set()
        choices: list[tuple[str, str]] = []
        for page in self.task.pages:
            for sub in page.get("subtitles") or []:
                lan = sub.get("lan", "")
                if lan and lan not in seen:
                    seen.add(lan)
                    label = sub.get("lan_doc", lan)
                    if sub.get("isAi"):
                        label += "（自动生成）"
                    choices.append((lan, label))
        return choices

    def _refreshButtonVisibility(self) -> None:
        task: BilibiliTask = self._task
        isCover = task.mode == DownloadMode.COVER
        self._selectPagesButton.setVisible(not isCover and len(task.pages) > 1)
        self._subtitleButton.setVisible(not isCover)
        self._subtitleButton.setEnabled(bool(self._subtitleChoices))



class SubtitleSelectDialog(MessageBoxBase):

    def __init__(self, choices: list[tuple[str, str]], selected: list[str], parent=None):
        super().__init__(parent)
        self._choices = choices

        self.titleLabel = SubtitleLabel(self.tr("选择字幕语言"), self)
        self.summaryLabel = BodyLabel("", self)

        self.selectAllButton = PrimaryPushButton(self.tr("全选"), self)
        self.clearButton = PushButton(self.tr("全不选"), self)

        self.treeView = AutoSizingTreeView(self, minimumVisibleRows=3, maximumVisibleRows=16)
        self.treeModel = QStandardItemModel(self.treeView)

        self._initWidget(set(selected))
        self._initLayout()
        self._bind()
        self._refreshSummary()

    def _initWidget(self, selected: set[str]) -> None:
        self.widget.setMinimumWidth(400)
        self.yesButton.setText(self.tr("确定"))
        self.cancelButton.setText(self.tr("取消"))

        self.treeView.setRootIsDecorated(False)
        self.treeView.setUniformRowHeights(True)
        self.treeView.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.treeView.setHeaderHidden(True)
        self.treeView.setModel(self.treeModel)

        for langCode, label in self._choices:
            item = QStandardItem(label)
            item.setCheckable(True)
            item.setCheckState(Qt.CheckState.Checked if langCode in selected else Qt.CheckState.Unchecked)
            item.setData(langCode, Qt.ItemDataRole.UserRole)
            self.treeModel.appendRow(item)

    def _initLayout(self) -> None:
        actionsLayout = QHBoxLayout()
        actionsLayout.setContentsMargins(0, 0, 0, 0)
        actionsLayout.setSpacing(8)
        actionsLayout.addWidget(self.selectAllButton)
        actionsLayout.addWidget(self.clearButton)
        actionsLayout.addStretch(1)
        actionsLayout.addWidget(self.summaryLabel)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.treeView)
        self.viewLayout.addSpacing(4)
        self.viewLayout.addLayout(actionsLayout)

    def _bind(self) -> None:
        self.selectAllButton.clicked.connect(lambda: self._setAll(True))
        self.clearButton.clicked.connect(lambda: self._setAll(False))
        self.treeModel.itemChanged.connect(lambda _: self._refreshSummary())

    def _setAll(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.treeModel.rowCount()):
            self.treeModel.item(row, 0).setCheckState(state)

    def _refreshSummary(self) -> None:
        count = sum(
            1 for row in range(self.treeModel.rowCount())
            if self.treeModel.item(row, 0).checkState() == Qt.CheckState.Checked
        )
        self.summaryLabel.setText(self.tr("{0}/{1} 种语言").format(count, self.treeModel.rowCount()))

    def selectedLanguages(self) -> list[str]:
        return [
            self.treeModel.item(row, 0).data(Qt.ItemDataRole.UserRole)
            for row in range(self.treeModel.rowCount())
            if self.treeModel.item(row, 0).checkState() == Qt.CheckState.Checked
        ]


class PageSelectDialog(MessageBoxBase):

    def __init__(self, task: BilibiliTask, parent=None):
        super().__init__(parent)
        self._pages = task.pages

        self.titleLabel = SubtitleLabel(self.tr("选择分P"), self)
        self.summaryLabel = BodyLabel("", self)

        self.selectAllButton = PrimaryPushButton(self.tr("全选"), self)
        self.clearButton = PushButton(self.tr("全不选"), self)
        self.invertButton = PushButton(self.tr("反选"), self)

        self.treeView = AutoSizingTreeView(self, minimumVisibleRows=3, maximumVisibleRows=16)
        self.treeModel = QStandardItemModel(self.treeView)

        self._initWidget()
        self._initLayout()
        self._bind()
        self._refreshSummary()

    def _initWidget(self) -> None:
        self.widget.setMinimumWidth(500)
        self.yesButton.setText(self.tr("确定"))
        self.cancelButton.setText(self.tr("取消"))

        self.treeView.setRootIsDecorated(False)
        self.treeView.setUniformRowHeights(True)
        self.treeView.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self.treeModel.setHorizontalHeaderLabels([self.tr("分P"), self.tr("大小")])
        self.treeView.setModel(self.treeModel)
        self.treeView.header().setStretchLastSection(False)
        self.treeView.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.treeView.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

        for page in self._pages:
            pageNumber = page["pageNumber"]
            pagePart = page.get("pagePart", "").strip()
            videoSize = page.get("videoSize", 0)
            audioSize = page.get("audioSize", 0)
            totalSize = videoSize + audioSize

            label = f"P{pageNumber}"
            if pagePart:
                label += f": {pagePart}"

            nameItem = QStandardItem(label)
            nameItem.setCheckable(True)
            nameItem.setCheckState(Qt.CheckState.Checked if page.get("selected", True) else Qt.CheckState.Unchecked)
            nameItem.setData(pageNumber, Qt.ItemDataRole.UserRole)

            sizeItem = QStandardItem(toReadableSize(totalSize) if totalSize > 0 else "")
            sizeItem.setEditable(False)

            self.treeModel.appendRow([nameItem, sizeItem])

    def _initLayout(self) -> None:
        actionsLayout = QHBoxLayout()
        actionsLayout.setContentsMargins(0, 0, 0, 0)
        actionsLayout.setSpacing(8)
        actionsLayout.addWidget(self.selectAllButton)
        actionsLayout.addWidget(self.clearButton)
        actionsLayout.addWidget(self.invertButton)
        actionsLayout.addStretch(1)
        actionsLayout.addWidget(self.summaryLabel)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.treeView)
        self.viewLayout.addSpacing(4)
        self.viewLayout.addLayout(actionsLayout)

    def _bind(self) -> None:
        self.selectAllButton.clicked.connect(lambda: self._setAll(True))
        self.clearButton.clicked.connect(lambda: self._setAll(False))
        self.invertButton.clicked.connect(self._onInvert)
        self.treeModel.itemChanged.connect(lambda _: self._refreshSummary())

    def _setAll(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.treeModel.rowCount()):
            self.treeModel.item(row, 0).setCheckState(state)

    def _onInvert(self) -> None:
        for row in range(self.treeModel.rowCount()):
            item = self.treeModel.item(row, 0)
            item.setCheckState(
                Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
            )

    def _refreshSummary(self) -> None:
        count = sum(
            1 for row in range(self.treeModel.rowCount())
            if self.treeModel.item(row, 0).checkState() == Qt.CheckState.Checked
        )
        self.summaryLabel.setText(self.tr("{0}/{1} 个分P").format(count, self.treeModel.rowCount()))
        self.yesButton.setEnabled(count > 0)

    def selectedPageNumbers(self) -> set[int]:
        return {
            self.treeModel.item(row, 0).data(Qt.ItemDataRole.UserRole)
            for row in range(self.treeModel.rowCount())
            if self.treeModel.item(row, 0).checkState() == Qt.CheckState.Checked
        }
