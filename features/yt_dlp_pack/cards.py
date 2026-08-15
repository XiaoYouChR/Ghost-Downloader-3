from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, QT_TRANSLATE_NOOP as N
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QWidget
from qfluentwidgets import (
    BodyLabel, FluentIcon, IndeterminateProgressRing,
    MessageBoxBase, PrimaryPushButton, ProgressBar, PushButton, SubtitleLabel,
    ToolTipFilter, TransparentToolButton,
)

from app.format import toReadableSize
from app.models.task import TaskStatus
from app.platform.filesystem import toSafeFilename
from app.view.cards.draft_cards import DraftCard
from app.view.cards.task_cards import MultiFileTaskCard, FieldSpec, SPEED_FIELD, ETA_FIELD
from app.view.components.range_slider import RangeSlider
from app.view.components.track_bar import TrackBar, TrackButton
from app.view.components.tree_view import AutoSizingTreeView
from app.view.dialogs.subtitle_select import SubtitleSelectDialog
from .config import ytDlpConfig
from .task import STEPS_PER_VIDEO, YouTubeCoverStep, YouTubeTask, buildFormatPair


def toCodecName(codec: str) -> str:
    if not codec or codec == "none":
        return ""
    c = codec.lower()
    if c.startswith("av01"):
        return "AV1"
    if c.startswith("vp9") or c.startswith("vp09"):
        return "VP9"
    if c.startswith("avc") or c.startswith("h264"):
        return "H.264"
    if c.startswith("hev") or c.startswith("hvc") or c.startswith("h265"):
        return "H.265"
    if c == "opus":
        return "Opus"
    if c.startswith("mp4a"):
        return "AAC"
    return ""


def toCodecLabel(fmt: dict) -> str:
    codec = toCodecName(fmt.get("vcodec", "")) or toCodecName(fmt.get("acodec", ""))
    br = fmt.get("vbr") or fmt.get("abr") or fmt.get("tbr") or 0
    parts = []
    if codec:
        parts.append(codec)
    if br >= 1000:
        parts.append(f"{br / 1000:.1f}Mbps")
    elif br > 0:
        parts.append(f"{int(br)}Kbps")
    return ", ".join(parts)


def buildVideoTiers(mediaInfo: dict, bestLabel: str) -> list[tuple[str, str]]:
    formats = mediaInfo.get("formats") or []
    best: dict[int, dict] = {}

    for f in formats:
        if f.get("vcodec") in (None, "none"):
            continue
        height = f.get("height") or 0
        if height <= 0:
            continue
        vbr = f.get("vbr") or f.get("tbr") or 0
        if height not in best or vbr > (best[height].get("vbr") or best[height].get("tbr") or 0):
            best[height] = f

    tiers = sorted(best.keys(), reverse=True)

    result: list[tuple[str, str]] = []
    if tiers:
        fmt = best[tiers[0]]
        fps = fmt.get("fps") or 0
        fpsLabel = "60" if fps > 30 else ""
        info = toCodecLabel(fmt)
        label = bestLabel + (f" ({tiers[0]}p{fpsLabel}, {info})" if info else f" ({tiers[0]}p{fpsLabel})")
        result.append(("0", label))

    for height in tiers:
        fmt = best[height]
        fps = fmt.get("fps") or 0
        fpsLabel = "60" if fps > 30 else ""
        info = toCodecLabel(fmt)
        label = f"{height}p{fpsLabel} ({info})" if info else f"{height}p{fpsLabel}"
        result.append((str(height), label))

    return result


def buildAudioTiers(mediaInfo: dict, bestLabel: str) -> list[tuple[str, str]]:
    formats = mediaInfo.get("formats") or []
    best: dict[int, dict] = {}

    for f in formats:
        if f.get("acodec") in (None, "none"):
            continue
        if f.get("vcodec", "none") != "none":
            continue
        abr = int(f.get("abr") or f.get("tbr") or 0)
        if abr <= 0:
            continue
        bucket = round(abr / 16) * 16
        if bucket not in best or abr > int(best[bucket].get("abr") or best[bucket].get("tbr") or 0):
            best[bucket] = f

    tiers = sorted(best.keys(), reverse=True)

    result: list[tuple[str, str]] = []
    if tiers:
        info = toCodecLabel(best[tiers[0]])
        result.append(("0", bestLabel + f" ({info})" if info else bestLabel))
    for bucket in tiers:
        fmt = best[bucket]
        abr = int(fmt.get("abr") or fmt.get("tbr") or 0)
        codec = toCodecName(fmt.get("acodec", ""))
        label = f"{abr}Kbps ({codec})" if codec else f"{abr}Kbps"
        result.append((str(abr), label))

    return result


def buildSubtitleChoices(mediaInfo: dict, automaticLabel: str) -> tuple[list[tuple[str, str]], set[str]]:
    choices: list[tuple[str, str]] = []
    autoLangs: set[str] = set()
    seen: set[str] = set()

    for lang in (mediaInfo.get("subtitles") or {}):
        if lang not in seen:
            seen.add(lang)
            choices.append((lang, lang))

    for lang in (mediaInfo.get("automatic_captions") or {}):
        if lang not in seen:
            seen.add(lang)
            autoLangs.add(lang)
            choices.append((lang, f"{lang} ({automaticLabel})"))

    return choices, autoLangs


STEP_LABELS = {
    1: N("YtDlpTaskCard", "提取信息"),
    2: N("YtDlpTaskCard", "下载视频"),
    3: N("YtDlpTaskCard", "下载音频"),
    4: N("YtDlpTaskCard", "合并"),
    5: N("YtDlpTaskCard", "下载字幕"),
}


def toYtDlpSizeText(task: YouTubeTask, speed: int, received: int) -> str | None:
    if task.status == TaskStatus.COMPLETED:
        if task.isPlaylist:
            videoCount = len(task.steps) // STEPS_PER_VIDEO
            totalReceived = sum(s.receivedBytes for s in task.steps)
            return QCoreApplication.translate("YtDlpTaskCard", "{0} 个视频 · {1}").format(
                videoCount, toReadableSize(totalReceived))
        return toReadableSize(task.fileSize) if task.fileSize > 0 else None
    if task.fileSize > 0:
        return f"{toReadableSize(received)}/{toReadableSize(task.fileSize)}"
    return f"{toReadableSize(received)}/--"


YTDLP_SIZE_FIELD = FieldSpec("size", FluentIcon.LIBRARY, {None: toYtDlpSizeText})


def toYtDlpNameText(task: YouTubeTask, speed: int, received: int) -> str | None:
    currentStep = next((s for s in task.steps if s.status == TaskStatus.RUNNING), None)
    if not currentStep:
        return None
    fileIndex = currentStep.fileIndex or 0
    stepInGroup = currentStep.stepIndex - fileIndex * STEPS_PER_VIDEO
    sourceLabel = STEP_LABELS.get(stepInGroup, "")
    label = QCoreApplication.translate("YtDlpTaskCard", sourceLabel) if sourceLabel else ""
    if task.isPlaylist:
        videoCount = len(task.steps) // STEPS_PER_VIDEO
        videoStem = getattr(currentStep, "videoStem", "") or task.name
        return f"{videoStem} ({fileIndex + 1}/{videoCount} · {label})" if label else None
    return f"{task.name} ({label})" if label else None


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


COL_START = 2
COL_END = 3


class VideoSelectDialog(MessageBoxBase):

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self._files = task.files or []

        self.titleLabel = SubtitleLabel(self.tr("选择视频"), self)
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
        self.widget.setMinimumWidth(650)
        self.yesButton.setText(self.tr("确定"))
        self.cancelButton.setText(self.tr("取消"))

        self.treeView.setRootIsDecorated(False)
        self.treeView.setUniformRowHeights(True)
        self.treeView.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)

        self.treeModel.setHorizontalHeaderLabels([
            self.tr("标题"), self.tr("时长"), self.tr("开始"), self.tr("结束"),
        ])
        self.treeView.setModel(self.treeModel)
        self.treeView.header().setStretchLastSection(False)
        self.treeView.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.treeView.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.treeView.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.treeView.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        for file in self._files:
            title = file.relativePath.strip() or f"视频 {file.index + 1}"

            nameItem = QStandardItem(f"{file.index + 1}. {title}")
            nameItem.setCheckable(True)
            nameItem.setCheckState(Qt.CheckState.Checked if file.selected else Qt.CheckState.Unchecked)
            nameItem.setData(file.index, Qt.ItemDataRole.UserRole)

            durationText = ""
            if file.duration > 0:
                minutes, seconds = divmod(int(file.duration), 60)
                durationText = f"{minutes}:{seconds:02d}"
            durationItem = QStandardItem(durationText)
            durationItem.setEditable(False)

            startItem = QStandardItem(toTimeText(file.startTime))
            startItem.setData(file.index, Qt.ItemDataRole.UserRole)
            endItem = QStandardItem(toTimeText(file.endTime))
            endItem.setData(file.index, Qt.ItemDataRole.UserRole)

            self.treeModel.appendRow([nameItem, durationItem, startItem, endItem])

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
        self.summaryLabel.setText(self.tr("{0}/{1} 个视频").format(count, self.treeModel.rowCount()))
        self.yesButton.setEnabled(count > 0)

    def selectedIndexes(self) -> set[int]:
        return {
            self.treeModel.item(row, 0).data(Qt.ItemDataRole.UserRole)
            for row in range(self.treeModel.rowCount())
            if self.treeModel.item(row, 0).checkState() == Qt.CheckState.Checked
        }

    def updateTimeRanges(self, files) -> None:
        for row in range(self.treeModel.rowCount()):
            fileIndex = self.treeModel.item(row, 0).data(Qt.ItemDataRole.UserRole)
            startText = self.treeModel.item(row, COL_START).text() if self.treeModel.item(row, COL_START) else ""
            endText = self.treeModel.item(row, COL_END).text() if self.treeModel.item(row, COL_END) else ""
            for f in files:
                if f.index == fileIndex:
                    f.startTime = parseTimeInput(startText)
                    f.endTime = parseTimeInput(endText)
                    break


class YtDlpDraftCard(DraftCard):

    def _initWidget(self) -> None:
        super()._initWidget()
        task: YouTubeTask = self._task
        mediaInfo: dict = getattr(task, "_mediaInfo", {})
        hasMediaInfo = bool(mediaInfo.get("formats"))

        self._trackBar = TrackBar(self)
        self._subtitleChoices: list[tuple[str, str]] = []
        self._autoLangs: set[str] = set()

        if hasMediaInfo:
            self._trackBar.videoButton.setOptions(buildVideoTiers(mediaInfo, self.tr("最佳画质")))
            self._trackBar.audioButton.setOptions(buildAudioTiers(mediaInfo, self.tr("最佳音质")))
            choices, autoLangs = buildSubtitleChoices(mediaInfo, self.tr("自动"))
            self._subtitleChoices = choices
            self._autoLangs = autoLangs
            self._trackBar.subtitleButton.setTrackEnabled(bool(choices))
            thumbnailUrl = mediaInfo.get("thumbnail") or ""
            if thumbnailUrl:
                task.setCoverUrl(thumbnailUrl)
                self._trackBar.coverButton.setTrackEnabled(True)
        else:
            self._trackBar.videoButton.setOptions([("0", self.tr("最佳画质"))])
            self._trackBar.audioButton.setOptions([("0", self.tr("最佳音质"))])
            self._trackBar.subtitleButton.setTrackEnabled(False)
            self._trackBar.coverButton.setTrackEnabled(False)
            self._trackBar.spinner.show()

        self._trimButton = TrackButton(FluentIcon.CUT, self)
        self._trimButton.setToolTip(self.tr("截取片段"))
        self._trimButton.setChecked(False)

        self._rangeSlider = RangeSlider(
            self,
            formatter=lambda s: f"{s // 60}:{s % 60:02d}",
            parser=parseTimeInput,
        )
        self._rangeSlider.hide()
        if hasMediaInfo:
            duration = int(mediaInfo.get("duration", 0))
            if duration > 0:
                self._rangeSlider.setRange(0, duration)
                self._rangeSlider.setValues(0, duration)

        self._videoSelectButton = TransparentToolButton(FluentIcon.LIBRARY, self)
        self._videoSelectButton.setFixedSize(28, 28)
        self._videoSelectButton.installEventFilter(ToolTipFilter(self._videoSelectButton))
        self._videoSelectButton.setToolTip(self.tr("选择视频"))
        self._videoSelectButton.setVisible(task.isPlaylist)

        self._playlistSpinner = IndeterminateProgressRing(self)
        self._playlistSpinner.setFixedSize(20, 20)
        self._playlistSpinner.setStrokeWidth(3)
        self._playlistSpinner.hide()

        if not hasMediaInfo:
            self._startMediaInfoFetch()

    def _initLayout(self) -> None:
        super()._initLayout()
        self.layout().addWidget(self._trackBar)
        self.layout().addWidget(self._trimButton)
        self.layout().addWidget(self._videoSelectButton)
        self.layout().addWidget(self._playlistSpinner)

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
        self._videoSelectButton.clicked.connect(self._onVideoSelectClicked)

    def _onTrackToggled(self) -> None:
        task: YouTubeTask = self._task
        task.isVideoEnabled = self._trackBar.videoButton.isChecked()
        task.isAudioEnabled = self._trackBar.audioButton.isChecked()
        task.isCoverEnabled = self._trackBar.coverButton.isChecked()

        stem = Path(task.name).stem
        if task.isVideoEnabled:
            task.setName(f"{stem}.mp4")
        elif task.isAudioEnabled:
            task.setName(f"{stem}.m4a")
        elif task.isCoverEnabled:
            task.setName(f"{stem}.jpg")

        self._refreshSummary()

        hasMedia = task.isVideoEnabled or task.isAudioEnabled
        subtitleEnabled = hasMedia and bool(self._subtitleChoices)
        self._trackBar.subtitleButton.setTrackEnabled(subtitleEnabled)
        if subtitleEnabled:
            self._trackBar.subtitleButton.setChecked(bool(task.subtitleLanguages.strip()))
        self._videoSelectButton.setVisible(hasMedia and task.isPlaylist)

    def _onTrimToggled(self) -> None:
        checked = not self._trimButton.isChecked()
        self._trimButton.setChecked(checked)
        self._rangeSlider.setVisible(checked)
        if checked:
            self.setFixedHeight(87)
            self.layout().setContentsMargins(10, 2, 10, 54)
            task: YouTubeTask = self._task
            if not task.files:
                from .task import YouTubeFile
                task.files = [YouTubeFile(index=0, relativePath="")]
        else:
            self.setFixedHeight(35)
            self.layout().setContentsMargins(10, 2, 10, 2)
            self._rangeSlider.clear()
            file = self._task.files[0] if self._task.files else None
            if file:
                file.startTime = 0
                file.endTime = 0
        w = self
        while w := w.parentWidget():
            w.updateGeometry()

    def _onRangeChanged(self, start: int, end: int) -> None:
        file = self._task.files[0] if self._task.files else None
        if file:
            file.startTime = start
            file.endTime = end

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rangeSlider.setGeometry(10, 37, self.width() - 20, 50)

    def _onVideoQualityPicked(self, value: str) -> None:
        self._task.maxVideoHeight = int(value)
        self._refreshSummary()

    def _onAudioQualityPicked(self, value: str) -> None:
        self._task.maxAudioBitrate = int(value)
        self._refreshSummary()

    def _refreshSummary(self) -> None:
        task: YouTubeTask = self._task
        mediaInfo = getattr(task, "_mediaInfo", None)
        if mediaInfo:
            videoFmt, audioFmt = buildFormatPair(mediaInfo, task)
            videoSize = int(videoFmt.get("filesize") or videoFmt.get("filesize_approx") or 0) if videoFmt else 0
            audioSize = int(audioFmt.get("filesize") or audioFmt.get("filesize_approx") or 0) if audioFmt else 0
            task.fileSize = videoSize + audioSize
        self.sizeLabel.setText(toReadableSize(task.fileSize) if task.fileSize > 0 else "")
        self.nameLabel.setText(task.name)
        self._refreshFileIcon()

    def _startMediaInfoFetch(self) -> None:
        from features.yt_dlp_pack.pack import YouTubeParser
        parser = YouTubeParser()
        self._coroutineRunner.submit(
            parser.fetchFormats(self._task.url),
            done=self._onMediaInfoLoaded,
            failed=self._onMediaInfoFailed,
            owner=self,
        )

    def _onMediaInfoLoaded(self, mediaInfo: dict) -> None:
        self._trackBar.spinner.hide()
        if not mediaInfo:
            return
        task: YouTubeTask = self._task
        task._mediaInfo = mediaInfo

        title = mediaInfo.get("title") or ""
        if title:
            ext = "mp4" if task.isVideoEnabled else "m4a" if task.isAudioEnabled else "jpg"
            task.setName(toSafeFilename(f"{title}.{ext}"))

        self._trackBar.videoButton.setOptions(buildVideoTiers(mediaInfo, self.tr("最佳画质")))
        self._trackBar.audioButton.setOptions(buildAudioTiers(mediaInfo, self.tr("最佳音质")))

        choices, autoLangs = buildSubtitleChoices(mediaInfo, self.tr("自动"))
        self._subtitleChoices = choices
        self._autoLangs = autoLangs
        self._trackBar.subtitleButton.setTrackEnabled(bool(choices))
        thumbnailUrl = mediaInfo.get("thumbnail") or ""
        if thumbnailUrl:
            task.setCoverUrl(thumbnailUrl)
            self._trackBar.coverButton.setTrackEnabled(True)

        duration = int(mediaInfo.get("duration", 0))
        if duration > 0:
            self._rangeSlider.setRange(0, duration)
            self._rangeSlider.setValues(0, duration)

        storyboardCandidates = [
            f for f in (mediaInfo.get("formats") or [])
            if f.get("format_note") == "storyboard" and f.get("columns") and f.get("rows")
        ]
        storyboardFmt = max(storyboardCandidates, key=lambda f: f.get("width", 0), default=None)
        if storyboardFmt:
            self._fetchStoryboard(storyboardFmt)

        self._refreshSummary()

    def _fetchStoryboard(self, fmt: dict) -> None:
        fragments = fmt.get("fragments") or []
        if not fragments:
            return
        columns = fmt.get("columns", 5)
        rows = fmt.get("rows", 5)
        framesPerSheet = columns * rows
        firstDuration = fragments[0].get("duration", 5.0)
        interval = firstDuration / framesPerSheet

        async def download():
            from PySide6.QtGui import QPixmap
            from app.client import buildClient
            client = buildClient()
            try:
                sheets: list[QPixmap] = []
                for frag in fragments:
                    url = frag.get("url") or frag.get("path", "")
                    if not url:
                        continue
                    response = await client.get(url)
                    try:
                        data = await response.bytes()
                    finally:
                        response.close()
                    pm = QPixmap()
                    pm.loadFromData(data)
                    if not pm.isNull():
                        sheets.append(pm)
                return sheets
            finally:
                client.close()

        self._coroutineRunner.submit(
            download(),
            done=lambda sheets: self._onStoryboardLoaded(sheets, interval, columns, rows),
            owner=self,
        )

    def _onStoryboardLoaded(self, sheets, interval, columns, rows) -> None:
        if not sheets:
            return
        framesPerSheet = columns * rows

        def provider(value: int):
            from PySide6.QtGui import QPixmap
            frameIndex = int(value / interval)
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

    def _onMediaInfoFailed(self, error: str) -> None:
        self._trackBar.spinner.hide()

    def _onSubtitleClicked(self) -> None:
        currentLangs = [s.strip() for s in self._task.subtitleLanguages.split(",") if s.strip()]
        dialog = SubtitleSelectDialog(self._subtitleChoices, currentLangs, self.window())
        try:
            if dialog.exec():
                selected = dialog.selectedLanguages()
                self._task.subtitleLanguages = ",".join(selected)
                self._task.shouldIncludeAutoSubs = bool(self._autoLangs & set(selected))
                self._trackBar.subtitleButton.setChecked(bool(selected))
        finally:
            dialog.deleteLater()

    def _onVideoSelectClicked(self) -> None:
        task: YouTubeTask = self._task
        if not task.files:
            self._videoSelectButton.hide()
            self._playlistSpinner.show()
            from features.yt_dlp_pack.pack import YouTubeParser
            parser = YouTubeParser()
            self._coroutineRunner.submit(
                parser.fetchPlaylist(task.url),
                done=self._onPlaylistLoaded,
                failed=self._onPlaylistFailed,
                owner=self,
            )
            return
        dialog = VideoSelectDialog(task, self.window())
        try:
            if dialog.exec():
                dialog.updateTimeRanges(task.files)
                task.setSelection(dialog.selectedIndexes())
                self.nameLabel.setText(task.name)
        finally:
            dialog.deleteLater()

    def _onPlaylistLoaded(self, videos: list[dict]) -> None:
        self._playlistSpinner.hide()
        self._videoSelectButton.show()
        task: YouTubeTask = self._task
        if videos:
            task.setVideos(videos)
            self._onVideoSelectClicked()
        else:
            self._videoSelectButton.setEnabled(False)
            self._videoSelectButton.setToolTip(self.tr("未找到播放列表"))

    def _onPlaylistFailed(self, error: str) -> None:
        self._playlistSpinner.hide()
        self._videoSelectButton.show()
        self._videoSelectButton.setToolTip(self.tr("加载播放列表失败"))


class YtDlpTaskCard(MultiFileTaskCard):
    fileSelectDialog = VideoSelectDialog
    infoFields = [SPEED_FIELD, ETA_FIELD, YTDLP_SIZE_FIELD]
    nameFormats = {TaskStatus.RUNNING: toYtDlpNameText}

    def _onSelectFilesClicked(self) -> None:
        dialog = VideoSelectDialog(self._task, self.window())
        try:
            if dialog.exec():
                dialog.updateTimeRanges(self._task.files)
                self._taskService.applySelection(self._task, dialog.selectedIndexes())
                self.refresh(force=True)
        finally:
            dialog.deleteLater()

    def _createProgressBar(self) -> QWidget:
        bar = ProgressBar(self)
        bar.setCustomBackgroundColor(QColor(0, 0, 0, 0), QColor(0, 0, 0, 0))
        return bar
