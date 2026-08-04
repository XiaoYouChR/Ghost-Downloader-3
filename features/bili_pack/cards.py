from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView
from qfluentwidgets import (
    BodyLabel, FluentIcon, MessageBoxBase,
    PrimaryPushButton, PushButton, SubtitleLabel,
    ToolTipFilter, TransparentToolButton,
)

from app.format import toReadableSize
from app.view.cards.draft_cards import MultiFileDraftCard
from app.view.cards.task_cards import MultiFileTaskCard
from app.view.components.track_bar import TrackBar
from app.view.components.tree_view import AutoSizingTreeView
from app.view.dialogs.subtitle_select import SubtitleSelectDialog
from .task import AUDIO_QUALITY_LABELS, BilibiliTask, streamUrl

CODEC_NAMES = {7: "H.264", 12: "H.265", 13: "AV1"}


class PageSelectDialog(MessageBoxBase):

    def __init__(self, task: BilibiliTask, parent=None):
        super().__init__(parent)
        self._pages = task.files or []

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
            pageNumber = page.pageNumber
            pagePart = page.pagePart.strip()
            totalSize = page.size

            label = f"P{pageNumber}"
            if pagePart:
                label += f": {pagePart}"

            nameItem = QStandardItem(label)
            nameItem.setCheckable(True)
            nameItem.setCheckState(Qt.CheckState.Checked if page.selected else Qt.CheckState.Unchecked)
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

    def selectedIndexes(self) -> set[int]:
        return {n - 1 for n in self.selectedPageNumbers()}


class BilibiliDraftCard(MultiFileDraftCard):

    def _initWidget(self) -> None:
        self._isSizeEstimated = False
        super()._initWidget()
        task: BilibiliTask = self._task
        self._trackBar = TrackBar(self)

        videoTiers = [("best", self.tr("最佳画质"))]
        audioTiers = [("best", self.tr("最佳音质"))]
        initialVideoKey = None
        initialAudioKey = None

        if task.files:
            page = task.files[0]
            qualityMap = dict(zip(task._acceptQualities, task._qualityLabels))

            videoTiers = []
            for s in page._videoStreams:
                key = f'{s["id"]}-{s["codecid"]}'
                qualityName = qualityMap.get(s["id"], str(s["id"]))
                codec = CODEC_NAMES.get(s["codecid"], "")
                kbps = s["bandwidth"] / 1000
                bitrate = f'{kbps / 1000:.1f}Mbps' if kbps >= 1000 else f'{int(kbps)}Kbps'
                label = f'{qualityName} ({codec}, {bitrate})'
                videoTiers.append((key, label))
                if streamUrl(s) == page.videoUrl:
                    initialVideoKey = key

            seen = set()
            audioTiers = []
            for s in page._audioStreams:
                if s["id"] not in seen:
                    seen.add(s["id"])
                    kbps = f'{s["bandwidth"] // 1000}Kbps'
                    name = AUDIO_QUALITY_LABELS.get(s["id"], str(s["id"]))
                    audioTiers.append((str(s["id"]), f'{name} ({kbps})'))
                    if streamUrl(s) == page.audioUrl:
                        initialAudioKey = str(s["id"])

        self._trackBar.videoButton.setOptions(videoTiers, selected=initialVideoKey)
        self._trackBar.audioButton.setOptions(audioTiers, selected=initialAudioKey)

        self._subtitleChoices = self._buildSubtitleChoices()
        self._trackBar.subtitleButton.setTrackEnabled(bool(self._subtitleChoices))
        self._trackBar.coverButton.setTrackEnabled(bool(self._task.coverUrl))

        if self._selectFilesButton is not None:
            self._selectFilesButton.setToolTip(self.tr("选择分P"))
        self._refreshButtonVisibility()

    def _initLayout(self) -> None:
        super()._initLayout()
        layout = self.layout()
        if self._selectFilesButton is not None:
            layout.insertWidget(layout.indexOf(self._selectFilesButton), self._trackBar)
        else:
            layout.addWidget(self._trackBar)

    def _bind(self) -> None:
        super()._bind()
        self._trackBar.videoButton.optionPicked.connect(self._onVideoQualityPicked)
        self._trackBar.videoButton.toggled.connect(self._onTrackToggled)
        self._trackBar.audioButton.optionPicked.connect(self._onAudioQualityPicked)
        self._trackBar.audioButton.toggled.connect(self._onTrackToggled)
        self._trackBar.subtitleButton.clicked.connect(self._onSubtitleClicked)
        self._trackBar.coverButton.clicked.connect(
            lambda: self._trackBar.coverButton.setChecked(not self._trackBar.coverButton.isChecked())
        )
        self._trackBar.coverButton.toggled.connect(self._onTrackToggled)

    def _onVideoQualityPicked(self, value: str) -> None:
        if value != "best":
            qn, codecid = value.split("-")
            self._task.setVideoQuality(int(qn), int(codecid))
            self._isSizeEstimated = True
            self._refreshSummary()

    def _onAudioQualityPicked(self, value: str) -> None:
        if value != "best":
            self._task.setAudioQuality(int(value))
            self._isSizeEstimated = True
            self._refreshSummary()

    def _onTrackToggled(self) -> None:
        task: BilibiliTask = self._task
        isVideo = self._trackBar.videoButton.isChecked()
        isAudio = self._trackBar.audioButton.isChecked()
        isCover = self._trackBar.coverButton.isChecked()

        changed = (task.isVideoEnabled != isVideo
                    or task.isAudioEnabled != isAudio
                    or task.isCoverEnabled != isCover)
        if changed:
            task.isVideoEnabled = isVideo
            task.isAudioEnabled = isAudio
            task.isCoverEnabled = isCover
            task._rebuildSteps()
        self._refreshSummary()
        self._refreshButtonVisibility()

    def _onSelectFilesClicked(self) -> None:
        task: BilibiliTask = self._task
        dialog = PageSelectDialog(task, self.window())
        try:
            if dialog.exec():
                selected = dialog.selectedPageNumbers()
                if selected:
                    task.setSelection({n - 1 for n in selected})
                    self._refreshSummary()
        finally:
            dialog.deleteLater()

    def _onSubtitleClicked(self) -> None:
        task: BilibiliTask = self._task
        dialog = SubtitleSelectDialog(self._subtitleChoices, task.subtitleLanguages, self.window())
        try:
            if dialog.exec():
                selected = dialog.selectedLanguages()
                task.setSubtitleLanguages(selected)
                self._trackBar.subtitleButton.setChecked(bool(selected))
        finally:
            dialog.deleteLater()

    def _refreshSummary(self) -> None:
        size = toReadableSize(self._task.fileSize)
        if self._isSizeEstimated:
            size = f"~{size}"
        self.sizeLabel.setText(size)
        self.nameLabel.setText(self._task.name)
        self._refreshFileIcon()

    def _buildSubtitleChoices(self) -> list[tuple[str, str]]:
        seen: set[str] = set()
        choices: list[tuple[str, str]] = []
        for page in self._task.files or []:
            for sub in page.subtitles:
                lan = sub.get("lan", "")
                if lan and lan not in seen:
                    seen.add(lan)
                    label = sub.get("lan_doc", lan)
                    if sub.get("isAi"):
                        label += "（自动生成）"
                    choices.append((lan, label))
        return choices

    def _refreshButtonVisibility(self) -> None:
        hasMedia = self._task.isVideoEnabled or self._task.isAudioEnabled
        if self._selectFilesButton is not None:
            self._selectFilesButton.setVisible(hasMedia and len(self._task.files or []) > 1)
        subtitleEnabled = hasMedia and bool(self._subtitleChoices)
        self._trackBar.subtitleButton.setTrackEnabled(subtitleEnabled)
        if subtitleEnabled:
            self._trackBar.subtitleButton.setChecked(bool(self._task.subtitleLanguages))


class BilibiliTaskCard(MultiFileTaskCard):
    fileSelectDialog = PageSelectDialog

    def _onSelectFilesClicked(self) -> None:
        dialog = PageSelectDialog(self._task, self.window())
        try:
            if dialog.exec():
                self._taskService.applySelection(self._task, dialog.selectedIndexes())
                self.refresh(force=True)
        finally:
            dialog.deleteLater()

    def _initWidget(self) -> None:
        super()._initWidget()
        task: BilibiliTask = self._task
        if not task.isVideoEnabled and not task.isAudioEnabled:
            self.selectFilesButton.hide()
        self.selectFilesButton.setToolTip(self.tr("选择分P"))
        self.selectFilesButton.installEventFilter(ToolTipFilter(self.selectFilesButton))
