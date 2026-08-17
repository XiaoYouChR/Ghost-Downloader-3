from __future__ import annotations

from collections import namedtuple
from urllib.parse import urlparse

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView
from qfluentwidgets import (
    BodyLabel, FluentIcon, MessageBoxBase,
    PrimaryPushButton, PushButton, SubtitleLabel,
    ToolTipFilter, TransparentToolButton,
)

from app.format import toReadableSize
from app.models.task import TaskStatus
from app.view.cards.draft_cards import MultiFileDraftCard
from app.view.cards.task_cards import MultiFileTaskCard
from app.view.components.range_slider import RangeSlider
from app.view.components.track_bar import TrackBar, TrackButton
from app.view.components.tree_view import AutoSizingTreeView
from app.view.dialogs.subtitle_select import SubtitleSelectDialog
from .stream import toStreamUrl
from .task import AUDIO_QUALITY_LABELS, BilibiliTask, setEpisodeTitle, setPagePart, setTimeRanges

CODEC_NAMES = {7: "H.264", 12: "H.265", 13: "AV1"}

StoryboardData = namedtuple("StoryboardData", ["sheets", "timestamps", "columns", "rows"])

COL_START = 2
COL_END = 3
ROLE_PAGES = Qt.ItemDataRole.UserRole + 1
ROLE_LABEL = Qt.ItemDataRole.UserRole + 2


def parseTimeInput(text: str) -> int:
    text = text.strip()
    if not text:
        return 0
    parts = text.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        return int(text)
    except ValueError:
        return 0


def toTimeText(seconds: int) -> str:
    if seconds <= 0:
        return ""
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


class SelectDialog(MessageBoxBase):

    def __init__(self, task: BilibiliTask, parent=None):
        super().__init__(parent)
        self._pages = task.files or []
        self._isSeason = task.isSeason
        self._groups = task.episodeGroups() if self._isSeason else [[p] for p in self._pages]
        self._isSyncing = False

        title = self.tr("选择合集") if self._isSeason else self.tr("选择分P")
        self.titleLabel = SubtitleLabel(title, self)
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
        self.widget.setMinimumWidth(640)
        self.yesButton.setText(self.tr("确定"))
        self.cancelButton.setText(self.tr("取消"))

        self.treeView.setRootIsDecorated(self._isSeason)
        self.treeView.setUniformRowHeights(True)
        self.treeView.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)

        firstCol = self.tr("合集") if self._isSeason else self.tr("分P")
        self.treeModel.setHorizontalHeaderLabels([
            firstCol, self.tr("大小"), self.tr("开始"), self.tr("结束"),
        ])
        self.treeView.setModel(self.treeModel)
        self.treeView.header().setStretchLastSection(False)
        self.treeView.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.treeView.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.treeView.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.treeView.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        for pages in self._groups:
            if not self._isSeason or len(pages) == 1:
                page = pages[0]
                if self._isSeason:
                    label = page.episodeTitle or page.bvid or f"#{page.index}"
                else:
                    label = page.pagePart.strip() or f"P{page.pageNumber}"
                self._addLeaf(None, page, label)
                continue
            title = pages[0].episodeTitle or pages[0].bvid or f"#{pages[0].index}"
            parent = QStandardItem(title)
            parent.setCheckable(True)
            parent.setEditable(True)
            parent.setData(pages, ROLE_PAGES)
            parent.setData(title, ROLE_LABEL)
            parentSize = QStandardItem(toReadableSize(sum(p.size for p in pages if p.size > 0)) or "")
            parentSize.setEditable(False)
            sharedTimes = {(p.startTime, p.endTime) for p in pages}
            if len(sharedTimes) == 1:
                start, end = next(iter(sharedTimes))
                parentStart = QStandardItem(toTimeText(start))
                parentEnd = QStandardItem(toTimeText(end))
            else:
                parentStart = QStandardItem("")
                parentEnd = QStandardItem("")
            if pages[0].sectionTitle:
                parent.setToolTip(pages[0].sectionTitle)
            self.treeModel.appendRow([parent, parentSize, parentStart, parentEnd])
            placeholder = QStandardItem("")
            placeholder.setEnabled(False)
            parent.appendRow(placeholder)
            if all(p.selected for p in pages):
                parent.setCheckState(Qt.CheckState.Checked)
            elif any(p.selected for p in pages):
                parent.setCheckState(Qt.CheckState.PartiallyChecked)
            else:
                parent.setCheckState(Qt.CheckState.Unchecked)

    def _addLeaf(self, parent: QStandardItem | None, page, label: str) -> None:
        nameItem = QStandardItem(label)
        nameItem.setCheckable(True)
        nameItem.setEditable(True)
        nameItem.setCheckState(Qt.CheckState.Checked if page.selected else Qt.CheckState.Unchecked)
        nameItem.setData(page.index, Qt.ItemDataRole.UserRole)
        nameItem.setData(label, ROLE_LABEL)
        if page.sectionTitle:
            nameItem.setToolTip(page.sectionTitle)

        sizeItem = QStandardItem(toReadableSize(page.size) if page.size > 0 else "")
        sizeItem.setEditable(False)
        startItem = QStandardItem(toTimeText(page.startTime))
        endItem = QStandardItem(toTimeText(page.endTime))

        if parent is None:
            self.treeModel.appendRow([nameItem, sizeItem, startItem, endItem])
        else:
            parent.appendRow([nameItem, sizeItem, startItem, endItem])

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
        self.treeModel.itemChanged.connect(self._onItemChanged)
        self.treeView.expanded.connect(self._onExpanded)

    def _onExpanded(self, index) -> None:
        item = self.treeModel.itemFromIndex(index)
        if item is None:
            return
        pages = item.data(ROLE_PAGES)
        if not pages or item.child(0, 0) is None:
            return
        if item.child(0, 0).data(Qt.ItemDataRole.UserRole) is not None:
            return
        self._isSyncing = True
        try:
            item.removeRow(0)
            for page in pages:
                self._addLeaf(item, page, page.pagePart.strip() or f"P{page.pageNumber}")
            self._syncParent(item)
        finally:
            self._isSyncing = False
        self._refreshSummary()

    def _onItemChanged(self, item: QStandardItem) -> None:
        if item.column() in (COL_START, COL_END):
            formatted = toTimeText(parseTimeInput(item.text()))
            if item.text() != formatted:
                item.setText(formatted)
            self._setTime(item)
            self._refreshSummary()
            return
        if self._isSyncing or item.column() != 0:
            return
        oldLabel = item.data(ROLE_LABEL)
        if oldLabel is not None and item.text() != oldLabel:
            self._setName(item)
            item.setData(item.text(), ROLE_LABEL)
            self._refreshSummary()
            return
        self._isSyncing = True
        try:
            pages = item.data(ROLE_PAGES)
            if pages is not None:
                state = Qt.CheckState.Checked if item.checkState() != Qt.CheckState.Unchecked else Qt.CheckState.Unchecked
                if item.checkState() == Qt.CheckState.PartiallyChecked:
                    item.setCheckState(Qt.CheckState.Checked)
                    state = Qt.CheckState.Checked
                selected = state == Qt.CheckState.Checked
                for page in pages:
                    page.selected = selected
                if item.child(0, 0) and item.child(0, 0).data(Qt.ItemDataRole.UserRole) is not None:
                    for i in range(item.rowCount()):
                        item.child(i, 0).setCheckState(state)
            elif item.parent():
                self._syncParent(item.parent())
                parentPages = item.parent().data(ROLE_PAGES)
                if parentPages:
                    fileIndex = item.data(Qt.ItemDataRole.UserRole)
                    for page in parentPages:
                        if page.index == fileIndex:
                            page.selected = item.checkState() == Qt.CheckState.Checked
            elif item.rowCount() > 0:
                state = Qt.CheckState.Checked if item.checkState() != Qt.CheckState.Unchecked else Qt.CheckState.Unchecked
                for i in range(item.rowCount()):
                    child = item.child(i, 0)
                    if child.data(Qt.ItemDataRole.UserRole) is not None:
                        child.setCheckState(state)
        finally:
            self._isSyncing = False
        self._refreshSummary()

    def _setTime(self, item: QStandardItem) -> None:
        itemRow = item.row()
        parent = item.parent()
        if parent is None:
            startItem = self.treeModel.item(itemRow, COL_START)
            endItem = self.treeModel.item(itemRow, COL_END)
            top = self.treeModel.item(itemRow, 0)
            pages = top.data(ROLE_PAGES) if top else None
            start = parseTimeInput(startItem.text() if startItem else "")
            end = parseTimeInput(endItem.text() if endItem else "")
            if pages:
                for page in pages:
                    page.startTime, page.endTime = start, end
                return
            fileIndex = top.data(Qt.ItemDataRole.UserRole) if top else None
        else:
            startItem = parent.child(itemRow, COL_START)
            endItem = parent.child(itemRow, COL_END)
            start = parseTimeInput(startItem.text() if startItem else "")
            end = parseTimeInput(endItem.text() if endItem else "")
            fileIndex = parent.child(itemRow, 0).data(Qt.ItemDataRole.UserRole)
        if fileIndex is None:
            return
        for page in self._pages:
            if page.index == fileIndex:
                page.startTime, page.endTime = start, end
                return

    def _setName(self, item: QStandardItem) -> None:
        text = item.text().strip()
        pages = item.data(ROLE_PAGES)
        if pages:
            setEpisodeTitle(pages, text)
            return
        fileIndex = item.data(Qt.ItemDataRole.UserRole)
        if fileIndex is None:
            return
        page = next((p for p in self._pages if p.index == fileIndex), None)
        if page is None:
            return
        if item.parent() is None and page.episodeTitle:
            setEpisodeTitle([page], text)
        else:
            setPagePart(page, text)

    def _syncParent(self, parent: QStandardItem) -> None:
        states = [parent.child(i, 0).checkState() for i in range(parent.rowCount())]
        if all(s == Qt.CheckState.Checked for s in states):
            parent.setCheckState(Qt.CheckState.Checked)
        elif all(s == Qt.CheckState.Unchecked for s in states):
            parent.setCheckState(Qt.CheckState.Unchecked)
        else:
            parent.setCheckState(Qt.CheckState.PartiallyChecked)

    def _isLazy(self, item: QStandardItem) -> bool:
        pages = item.data(ROLE_PAGES)
        child = item.child(0, 0) if item.rowCount() else None
        return bool(pages) and child is not None and child.data(Qt.ItemDataRole.UserRole) is None

    def _setAll(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self._isSyncing = True
        try:
            for row in range(self.treeModel.rowCount()):
                top = self.treeModel.item(row, 0)
                pages = top.data(ROLE_PAGES)
                if self._isLazy(top):
                    top.setCheckState(state)
                    for page in pages:
                        page.selected = checked
                elif top.rowCount() == 0:
                    top.setCheckState(state)
                else:
                    for i in range(top.rowCount()):
                        child = top.child(i, 0)
                        if child.data(Qt.ItemDataRole.UserRole) is not None:
                            child.setCheckState(state)
                    if pages:
                        for page in pages:
                            page.selected = checked
                    self._syncParent(top)
        finally:
            self._isSyncing = False
        self._refreshSummary()

    def _onInvert(self) -> None:
        self._isSyncing = True
        try:
            for row in range(self.treeModel.rowCount()):
                top = self.treeModel.item(row, 0)
                pages = top.data(ROLE_PAGES)
                if self._isLazy(top):
                    for page in pages:
                        page.selected = not page.selected
                    if all(p.selected for p in pages):
                        top.setCheckState(Qt.CheckState.Checked)
                    elif any(p.selected for p in pages):
                        top.setCheckState(Qt.CheckState.PartiallyChecked)
                    else:
                        top.setCheckState(Qt.CheckState.Unchecked)
                elif top.rowCount() == 0:
                    top.setCheckState(
                        Qt.CheckState.Unchecked if top.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
                    )
                else:
                    for i in range(top.rowCount()):
                        child = top.child(i, 0)
                        if child.data(Qt.ItemDataRole.UserRole) is not None:
                            child.setCheckState(
                                Qt.CheckState.Unchecked if child.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
                            )
                    self._syncParent(top)
                    if pages:
                        for i in range(top.rowCount()):
                            child = top.child(i, 0)
                            fileIndex = child.data(Qt.ItemDataRole.UserRole)
                            for page in pages:
                                if page.index == fileIndex:
                                    page.selected = child.checkState() == Qt.CheckState.Checked
        finally:
            self._isSyncing = False
        self._refreshSummary()

    def _refreshSummary(self) -> None:
        selected = self.selectedIndexes()
        if self._isSeason:
            selectedEps = sum(1 for pages in self._groups if any(p.index in selected for p in pages))
            self.summaryLabel.setText(self.tr("{0}/{1} 集").format(selectedEps, len(self._groups)))
        else:
            self.summaryLabel.setText(self.tr("{0}/{1} 个分P").format(len(selected), len(self._pages)))
        self.yesButton.setEnabled(len(selected) > 0)

    def selectedIndexes(self) -> set[int]:
        result: set[int] = set()
        for row in range(self.treeModel.rowCount()):
            top = self.treeModel.item(row, 0)
            pages = top.data(ROLE_PAGES)
            if self._isLazy(top):
                if top.checkState() == Qt.CheckState.Checked:
                    result.update(p.index for p in pages)
                elif top.checkState() == Qt.CheckState.PartiallyChecked:
                    result.update(p.index for p in pages if p.selected)
            elif top.rowCount() == 0:
                fileIndex = top.data(Qt.ItemDataRole.UserRole)
                if fileIndex is not None and top.checkState() == Qt.CheckState.Checked:
                    result.add(fileIndex)
            else:
                for i in range(top.rowCount()):
                    child = top.child(i, 0)
                    fileIndex = child.data(Qt.ItemDataRole.UserRole)
                    if fileIndex is not None and child.checkState() == Qt.CheckState.Checked:
                        result.add(fileIndex)
        return result

    def timeRanges(self) -> dict[int, tuple[int, int]]:
        result: dict[int, tuple[int, int]] = {}
        for row in range(self.treeModel.rowCount()):
            top = self.treeModel.item(row, 0)
            pages = top.data(ROLE_PAGES)
            if self._isLazy(top):
                start = parseTimeInput(self.treeModel.item(row, COL_START).text() or "")
                end = parseTimeInput(self.treeModel.item(row, COL_END).text() or "")
                if start or end:
                    result.update((p.index, (start, end)) for p in pages)
                continue
            if top.rowCount() == 0:
                items = [top]
            else:
                items = [top.child(i, 0) for i in range(top.rowCount())]
            for item in items:
                fileIndex = item.data(Qt.ItemDataRole.UserRole)
                if fileIndex is None:
                    continue
                parent = item.parent()
                itemRow = item.row()
                if parent is None:
                    startItem = self.treeModel.item(itemRow, COL_START)
                    endItem = self.treeModel.item(itemRow, COL_END)
                else:
                    startItem = parent.child(itemRow, COL_START)
                    endItem = parent.child(itemRow, COL_END)
                start = parseTimeInput(startItem.text() if startItem else "")
                end = parseTimeInput(endItem.text() if endItem else "")
                result[fileIndex] = (start, end)
        return result


class BilibiliDraftCard(MultiFileDraftCard):

    def _initWidget(self) -> None:
        self._isSizeEstimated = False
        self._storyboardLoaded = False
        super()._initWidget()
        task: BilibiliTask = self._task
        self._trackBar = TrackBar(self)

        videoTiers = [("best", self.tr("最佳画质"))]
        audioTiers = [("best", self.tr("最佳音质"))]
        initialVideoKey = None
        initialAudioKey = None

        page = next((p for p in task.files or [] if p._videoStreams or p._audioStreams), None)
        if page:
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
                if toStreamUrl(s) == page.videoUrl:
                    initialVideoKey = key

            seen = set()
            audioTiers = []
            for s in page._audioStreams:
                if s["id"] not in seen:
                    seen.add(s["id"])
                    kbps = f'{s["bandwidth"] // 1000}Kbps'
                    name = AUDIO_QUALITY_LABELS.get(s["id"], str(s["id"]))
                    audioTiers.append((str(s["id"]), f'{name} ({kbps})'))
                    if toStreamUrl(s) == page.audioUrl:
                        initialAudioKey = str(s["id"])

        self._trackBar.videoButton.setOptions(videoTiers, selected=initialVideoKey)
        self._trackBar.audioButton.setOptions(audioTiers, selected=initialAudioKey)

        self._subtitleChoices = self._buildSubtitleChoices()
        self._trackBar.subtitleButton.setTrackEnabled(bool(self._subtitleChoices))
        self._trackBar.coverButton.setTrackEnabled(bool(self._task.coverUrl))

        self._trimButton = TrackButton(FluentIcon.CUT, self)
        self._trimButton.setToolTip(self.tr("截取片段"))
        self._trimButton.setChecked(False)

        self._rangeSlider = RangeSlider(
            self,
            formatter=lambda s: f"{s // 60}:{s % 60:02d}",
            parser=parseTimeInput,
        )
        self._rangeSlider.hide()
        if task.files and len(task.files) == 1:
            page = task.files[0]
            if page._duration > 0:
                self._rangeSlider.setRange(0, page._duration)
                self._rangeSlider.setValues(0, page._duration)

        if self._selectFilesButton is not None:
            tip = self.tr("选择合集") if task.isSeason else self.tr("选择分P")
            self._selectFilesButton.setToolTip(tip)
        self._refreshButtonVisibility()

    def _initLayout(self) -> None:
        super()._initLayout()
        layout = self.layout()
        if self._selectFilesButton is not None:
            layout.insertWidget(layout.indexOf(self._selectFilesButton), self._trackBar)
        else:
            layout.addWidget(self._trackBar)
        layout.addWidget(self._trimButton)

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
        self._trimButton.clicked.connect(self._onTrimToggled)
        self._rangeSlider.rangeChanged.connect(self._onRangeChanged)

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
            task.update()
        self._refreshSummary()
        self._refreshButtonVisibility()

    def _onTrimToggled(self) -> None:
        checked = not self._trimButton.isChecked()
        self._trimButton.setChecked(checked)
        self._rangeSlider.setVisible(checked)
        if checked:
            self.setFixedHeight(87)
            self.layout().setContentsMargins(10, 2, 10, 54)
            if not self._storyboardLoaded:
                self._fetchStoryboard()
        else:
            self.setFixedHeight(35)
            self.layout().setContentsMargins(10, 2, 10, 2)
            self._rangeSlider.clear()
            file = self._task.files[0] if self._task.files else None
            if file:
                file.startTime = 0
                file.endTime = 0
                self._task.update()
        w = self
        while w := w.parentWidget():
            w.updateGeometry()

    def _onRangeChanged(self, start: int, end: int) -> None:
        file = self._task.files[0] if self._task.files else None
        if file:
            file.startTime = start
            file.endTime = end
            self._task.update()
            self._refreshSummary()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rangeSlider.setGeometry(10, 37, self.width() - 20, 50)

    def _onSelectFilesClicked(self) -> None:
        task: BilibiliTask = self._task
        dialog = SelectDialog(task, self.window())
        try:
            if dialog.exec():
                selected = dialog.selectedIndexes()
                if selected:
                    setTimeRanges(task.files or [], dialog.timeRanges())
                    task.setSelection(selected)
                    task.update()
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

    def _fetchStoryboard(self) -> None:
        import re
        import urllib.parse

        task: BilibiliTask = self._task
        page = task.files[0] if task.files else None
        if not page or not page.cid:
            return

        videoIdMatch = re.match(r"/video/(BV[a-zA-Z0-9]+|av\d+)", urlparse(task.url).path)
        if not videoIdMatch:
            return
        videoId = videoIdMatch.group(1)

        params: dict = {"cid": page.cid, "index": 1}
        if videoId.startswith("av"):
            params["aid"] = videoId[2:]
        else:
            params["bvid"] = videoId

        apiUrl = f"https://api.bilibili.com/x/player/videoshot?{urllib.parse.urlencode(params)}"
        cookie = task.files[0].headers.get("cookie", "") if task.files else ""

        async def download():
            from PySide6.QtGui import QPixmap
            from app.client import buildClient

            client = buildClient(headers={"cookie": cookie} if cookie else None)
            try:
                response = await client.get(apiUrl)
                response.raise_for_status()
                payload = await response.json()
                data = payload.get("data") or {}

                imageUrls = data.get("image") or []
                timestamps = data.get("index") or []
                columns = data.get("img_x_len") or 10
                rows = data.get("img_y_len") or 10

                if not imageUrls or not timestamps:
                    return None

                sheets = []
                for imgUrl in imageUrls:
                    if imgUrl.startswith("//"):
                        imgUrl = "https:" + imgUrl
                    resp = await client.get(imgUrl)
                    try:
                        imgData = await resp.bytes()
                    finally:
                        resp.close()
                    pm = QPixmap()
                    pm.loadFromData(imgData)
                    if not pm.isNull():
                        sheets.append(pm)

                return StoryboardData(sheets, timestamps, columns, rows)
            finally:
                client.close()

        self._coroutineRunner.submit(
            download(),
            done=self._onStoryboardLoaded,
            owner=self,
        )

    def _onStoryboardLoaded(self, result: StoryboardData | None) -> None:
        self._storyboardLoaded = True
        if not result:
            return
        framesPerSheet = result.columns * result.rows

        sheets = result.sheets
        timestamps = result.timestamps
        columns = result.columns
        rows = result.rows

        def provider(value: int):
            from bisect import bisect_right
            frameIndex = max(0, bisect_right(timestamps, value) - 1)
            sheetIdx = frameIndex // framesPerSheet
            if sheetIdx >= len(sheets):
                return None
            sheet = sheets[sheetIdx]
            local = frameIndex % framesPerSheet
            col = local % columns
            row = local // columns
            frameW = sheet.width() // columns
            frameH = sheet.height() // rows
            return sheet.copy(col * frameW, row * frameH, frameW, frameH)

        self._rangeSlider.setPreviewProvider(provider)

    def _refreshSummary(self) -> None:
        size = toReadableSize(self._task.fileSize)
        if self._isSizeEstimated:
            size = f"~{size}"
        if self._task.isSeason:
            self.sizeLabel.setText(f"{self._task.seasonSummary()} · {size}")
        else:
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
    fileSelectDialog = SelectDialog

    def _refreshForStatus(self, task: BilibiliTask) -> None:
        super()._refreshForStatus(task)
        if (task.isSeason
                and task.files and len(task.files) > 1
                and not self._isFileMissing
                and task.status in {TaskStatus.WAITING, TaskStatus.COMPLETED}):
            self.statusLabel.setText(task.seasonSummary())

    def _onSelectFilesClicked(self) -> None:
        dialog = SelectDialog(self._task, self.window())
        try:
            if dialog.exec():
                setTimeRanges(self._task.files or [], dialog.timeRanges())
                self._taskService.applySelection(self._task, dialog.selectedIndexes())
                self.refresh(force=True)
        finally:
            dialog.deleteLater()

    def _initWidget(self) -> None:
        super()._initWidget()
        task: BilibiliTask = self._task
        if not task.isVideoEnabled and not task.isAudioEnabled:
            self.selectFilesButton.hide()
        tip = self.tr("选择合集") if task.isSeason else self.tr("选择分P")
        self.selectFilesButton.setToolTip(tip)
        self.selectFilesButton.installEventFilter(ToolTipFilter(self.selectFilesButton))
