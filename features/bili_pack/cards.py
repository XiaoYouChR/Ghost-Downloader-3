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
from app.view.cards.draft_cards import MultiFileDraftCard
from app.view.cards.task_cards import MultiFileTaskCard
from app.view.components.range_slider import RangeSlider
from app.view.components.track_bar import TrackBar, TrackButton
from app.view.components.tree_view import AutoSizingTreeView
from app.view.dialogs.subtitle_select import SubtitleSelectDialog
from .task import AUDIO_QUALITY_LABELS, BilibiliTask, streamUrl

CODEC_NAMES = {7: "H.264", 12: "H.265", 13: "AV1"}

StoryboardData = namedtuple("StoryboardData", ["sheets", "timestamps", "columns", "rows"])

COL_START = 2
COL_END = 3


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
        self.widget.setMinimumWidth(600)
        self.yesButton.setText(self.tr("确定"))
        self.cancelButton.setText(self.tr("取消"))

        self.treeView.setRootIsDecorated(False)
        self.treeView.setUniformRowHeights(True)
        self.treeView.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)

        self.treeModel.setHorizontalHeaderLabels([
            self.tr("分P"), self.tr("大小"), self.tr("开始"), self.tr("结束"),
        ])
        self.treeView.setModel(self.treeModel)
        self.treeView.header().setStretchLastSection(False)
        self.treeView.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.treeView.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.treeView.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.treeView.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

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

            startItem = QStandardItem(toTimeText(page.startTime))
            startItem.setData(pageNumber, Qt.ItemDataRole.UserRole)
            endItem = QStandardItem(toTimeText(page.endTime))
            endItem.setData(pageNumber, Qt.ItemDataRole.UserRole)

            self.treeModel.appendRow([nameItem, sizeItem, startItem, endItem])

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

    def _onItemChanged(self, item: QStandardItem) -> None:
        if item.column() in (COL_START, COL_END):
            formatted = toTimeText(parseTimeInput(item.text()))
            if item.text() != formatted:
                item.setText(formatted)
        self._refreshSummary()

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

    def timeRanges(self) -> dict[int, tuple[int, int]]:
        result: dict[int, tuple[int, int]] = {}
        for row in range(self.treeModel.rowCount()):
            pageNumber = self.treeModel.item(row, 0).data(Qt.ItemDataRole.UserRole)
            startText = self.treeModel.item(row, COL_START).text() if self.treeModel.item(row, COL_START) else ""
            endText = self.treeModel.item(row, COL_END).text() if self.treeModel.item(row, COL_END) else ""
            start = parseTimeInput(startText)
            end = parseTimeInput(endText)
            if start or end:
                result[pageNumber] = (start, end)
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
            self._selectFilesButton.setToolTip(self.tr("选择分P"))
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
            task._rebuildSteps()
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
                self._task._rebuildSteps()
        w = self
        while w := w.parentWidget():
            w.updateGeometry()

    def _onRangeChanged(self, start: int, end: int) -> None:
        file = self._task.files[0] if self._task.files else None
        if file:
            file.startTime = start
            file.endTime = end
            self._task._rebuildSteps()
            self._refreshSummary()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rangeSlider.setGeometry(10, 37, self.width() - 20, 50)

    def _onSelectFilesClicked(self) -> None:
        task: BilibiliTask = self._task
        dialog = PageSelectDialog(task, self.window())
        try:
            if dialog.exec():
                selected = dialog.selectedPageNumbers()
                if selected:
                    for page in task.files or []:
                        ranges = dialog.timeRanges()
                        if page.pageNumber in ranges:
                            page.startTime, page.endTime = ranges[page.pageNumber]
                        else:
                            page.startTime = page.endTime = 0
                    task.setSelection({n - 1 for n in selected})
                    task._rebuildSteps()
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
                ranges = dialog.timeRanges()
                for page in self._task.files or []:
                    if page.pageNumber in ranges:
                        page.startTime, page.endTime = ranges[page.pageNumber]
                    else:
                        page.startTime = page.endTime = 0
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
