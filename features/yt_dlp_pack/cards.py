from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QWidget
from qfluentwidgets import (
    BodyLabel, ComboBox, FluentIcon, IndeterminateProgressRing,
    MessageBoxBase, PrimaryPushButton, ProgressBar, PushButton, SubtitleLabel,
    ToolButton, ToolTipFilter, TransparentToolButton,
)

from app.format import toReadableSize
from app.models.task import TaskStatus
from app.view.cards.draft_cards import UniversalDraftCard
from app.view.cards.task_cards import UniversalTaskCard
from app.view.components.tree_view import AutoSizingTreeView
from .config import ytDlpConfig
from .task import STEPS_PER_VIDEO, YouTubeTask


def buildQualityTiers(mediaInfo: dict) -> list[tuple[str, str]]:
    formats = mediaInfo.get("formats") or []
    seen: set[tuple[int, int]] = set()
    tiers: list[tuple[int, int]] = []

    for f in formats:
        if f.get("vcodec") in (None, "none"):
            continue
        height = f.get("height") or 0
        fps = f.get("fps") or 0
        if height <= 0:
            continue
        key = (height, 60 if fps > 30 else 0)
        if key not in seen:
            seen.add(key)
            tiers.append(key)

    tiers.sort(key=lambda t: (t[0], t[1]), reverse=True)

    result: list[tuple[str, str]] = []
    if tiers:
        bestH, bestFps = tiers[0]
        result.append(("bv*+ba/b", f"最佳画质 ({bestH}p{'60' if bestFps else ''})"))

    for height, fps in tiers:
        fpsLabel = "60" if fps else ""
        result.append((f"bv*[height<={height}]+ba/b", f"{height}p{fpsLabel}"))

    result.append(("ba/b", "仅音频"))
    return result


def buildSubtitleChoices(mediaInfo: dict) -> list[tuple[str, str, bool]]:
    choices: list[tuple[str, str, bool]] = []
    seen: set[str] = set()

    for lang in (mediaInfo.get("subtitles") or {}):
        if lang not in seen:
            seen.add(lang)
            choices.append((lang, lang, False))

    for lang in (mediaInfo.get("automatic_captions") or {}):
        if lang not in seen:
            seen.add(lang)
            choices.append((lang, f"{lang} (自动)", True))

    return choices


STEP_LABELS = {
    1: "提取信息",
    2: "下载视频",
    3: "下载音频",
    4: "合并",
}


class YtDlpDraftCard(UniversalDraftCard):

    def _initWidget(self) -> None:
        super()._initWidget()
        task: YouTubeTask = self._task
        mediaInfo: dict = getattr(task, "_mediaInfo", {})
        hasMediaInfo = bool(mediaInfo.get("formats"))

        self._qualityTiers = buildQualityTiers(mediaInfo) if hasMediaInfo else [("bv*+ba/b", self.tr("最佳画质"))]
        self._subtitleChoices = buildSubtitleChoices(mediaInfo) if hasMediaInfo else []

        self._mediaSpinner = IndeterminateProgressRing(self)
        self._mediaSpinner.setFixedSize(20, 20)
        self._mediaSpinner.setStrokeWidth(3)
        self._mediaSpinner.setVisible(not hasMediaInfo)

        self._qualityCombo = ComboBox(self)
        self._qualityCombo.setMinimumWidth(160)
        for _selector, label in self._qualityTiers:
            self._qualityCombo.addItem(label)
        if self._qualityTiers:
            self._qualityCombo.setCurrentIndex(0)

        self._subtitleButton = TransparentToolButton(FluentIcon.LANGUAGE, self)
        self._subtitleButton.installEventFilter(ToolTipFilter(self._subtitleButton))
        self._subtitleButton.setToolTip(self.tr("选择字幕"))
        self._subtitleButton.setEnabled(bool(self._subtitleChoices))

        self._videoSelectButton = TransparentToolButton(FluentIcon.LIBRARY, self)
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
        self.layout().addWidget(self._mediaSpinner)
        self.layout().addWidget(self._qualityCombo)
        self.layout().addWidget(self._subtitleButton)
        self.layout().addWidget(self._videoSelectButton)
        self.layout().addWidget(self._playlistSpinner)

    def _bind(self) -> None:
        super()._bind()
        self._qualityCombo.currentIndexChanged.connect(self._onQualityChanged)
        self._subtitleButton.clicked.connect(self._onSubtitleClicked)
        self._videoSelectButton.clicked.connect(self._onVideoSelectClicked)

    def _startMediaInfoFetch(self) -> None:
        from app.services.coroutine_runner import coroutineRunner
        from features.yt_dlp_pack.pack import YouTubeParser
        parser = YouTubeParser()
        coroutineRunner.submit(
            parser.fetchFormats(self._task.url),
            done=self._onMediaInfoLoaded,
            failed=self._onMediaInfoFailed,
            owner=self,
        )

    def _onMediaInfoLoaded(self, mediaInfo: dict) -> None:
        self._mediaSpinner.hide()
        if not mediaInfo:
            return
        task: YouTubeTask = self._task
        task._mediaInfo = mediaInfo

        try:
            fileSize = int(float(mediaInfo.get("filesize_approx") or 0))
        except (TypeError, ValueError):
            fileSize = 0
        if fileSize:
            task.fileSize = fileSize
            self.sizeLabel.setText(toReadableSize(fileSize))

        self._qualityTiers = buildQualityTiers(mediaInfo)
        self._qualityCombo.clear()
        for _selector, label in self._qualityTiers:
            self._qualityCombo.addItem(label)
        if self._qualityTiers:
            self._qualityCombo.setCurrentIndex(0)

        self._subtitleChoices = buildSubtitleChoices(mediaInfo)
        self._subtitleButton.setEnabled(bool(self._subtitleChoices))

    def _onMediaInfoFailed(self, error: str) -> None:
        self._mediaSpinner.hide()

    def _onQualityChanged(self, index: int) -> None:
        if 0 <= index < len(self._qualityTiers):
            self._task.videoFormatFilter = self._qualityTiers[index][0]

    def _onSubtitleClicked(self) -> None:
        dialog = SubtitleSelectDialog(self._subtitleChoices, self.window())
        if dialog.exec():
            langs, includeAuto = dialog.selectedLanguages()
            self._task.subtitleLanguages = langs
            self._task.shouldIncludeAutoSubs = includeAuto

    def _onVideoSelectClicked(self) -> None:
        task: YouTubeTask = self._task
        if not task.files:
            self._videoSelectButton.hide()
            self._playlistSpinner.show()
            from app.services.coroutine_runner import coroutineRunner
            from features.yt_dlp_pack.pack import YouTubeParser
            parser = YouTubeParser()
            coroutineRunner.submit(
                parser.fetchPlaylist(task.url),
                done=self._onPlaylistLoaded,
                failed=self._onPlaylistFailed,
            )
            return
        dialog = VideoSelectDialog(task.files, self.window())
        if dialog.exec():
            task.setSelection(dialog.selectedIndices())
            self.nameLabel.setText(task.name)

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


class SubtitleSelectDialog(MessageBoxBase):

    def __init__(self, choices: list[tuple[str, str, bool]], parent=None):
        super().__init__(parent)
        self._choices = choices

        self.titleLabel = SubtitleLabel(self.tr("选择字幕语言"), self)
        self.summaryLabel = BodyLabel("", self)

        self.selectAllButton = PrimaryPushButton(self.tr("全选"), self)
        self.clearButton = PushButton(self.tr("全不选"), self)

        self.treeView = AutoSizingTreeView(self, minimumVisibleRows=3, maximumVisibleRows=16)
        self.treeModel = QStandardItemModel(self.treeView)

        self._initWidget()
        self._initLayout()
        self._bind()
        self._refreshSummary()

    def _initWidget(self) -> None:
        self.widget.setMinimumWidth(400)
        self.yesButton.setText(self.tr("确定"))
        self.cancelButton.setText(self.tr("取消"))

        self.treeView.setRootIsDecorated(False)
        self.treeView.setUniformRowHeights(True)
        self.treeView.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.treeView.setHeaderHidden(True)

        self.treeView.setModel(self.treeModel)

        defaultLangs = {s.strip() for s in ytDlpConfig.subtitleLanguages.value.split(",") if s.strip()}

        for langCode, label, _isAuto in self._choices:
            item = QStandardItem(label)
            item.setCheckable(True)
            item.setCheckState(Qt.CheckState.Checked if langCode in defaultLangs else Qt.CheckState.Unchecked)
            item.setData(langCode, Qt.ItemDataRole.UserRole)
            item.setData(_isAuto, Qt.ItemDataRole.UserRole + 1)
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

    def selectedLanguages(self) -> tuple[str, bool]:
        langs: list[str] = []
        hasAuto = False
        for row in range(self.treeModel.rowCount()):
            item = self.treeModel.item(row, 0)
            if item.checkState() == Qt.CheckState.Checked:
                langs.append(item.data(Qt.ItemDataRole.UserRole))
                if item.data(Qt.ItemDataRole.UserRole + 1):
                    hasAuto = True
        return ",".join(langs), hasAuto


class VideoSelectDialog(MessageBoxBase):

    def __init__(self, files: list, parent=None):
        super().__init__(parent)
        self._files = files

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
        self.widget.setMinimumWidth(550)
        self.yesButton.setText(self.tr("确定"))
        self.cancelButton.setText(self.tr("取消"))

        self.treeView.setRootIsDecorated(False)
        self.treeView.setUniformRowHeights(True)
        self.treeView.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self.treeModel.setHorizontalHeaderLabels([self.tr("标题"), self.tr("时长")])
        self.treeView.setModel(self.treeModel)
        self.treeView.header().setStretchLastSection(False)
        self.treeView.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.treeView.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

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

            self.treeModel.appendRow([nameItem, durationItem])

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
        self.summaryLabel.setText(self.tr("{0}/{1} 个视频").format(count, self.treeModel.rowCount()))
        self.yesButton.setEnabled(count > 0)

    def selectedIndices(self) -> set[int]:
        return {
            self.treeModel.item(row, 0).data(Qt.ItemDataRole.UserRole)
            for row in range(self.treeModel.rowCount())
            if self.treeModel.item(row, 0).checkState() == Qt.CheckState.Checked
        }


class YtDlpTaskCard(UniversalTaskCard):

    def __init__(self, task: YouTubeTask, parent=None):
        super().__init__(task, parent)
        self.selectFilesButton = None
        if task.files and len(task.files) > 1:
            self.selectFilesButton = ToolButton(FluentIcon.LIBRARY, self)
            self.hBoxLayout.insertWidget(
                self.hBoxLayout.indexOf(self.verifyHashButton),
                self.selectFilesButton,
            )
            self.selectFilesButton.setToolTip(self.tr("选择视频"))
            self.selectFilesButton.installEventFilter(ToolTipFilter(self.selectFilesButton))
            self.selectFilesButton.clicked.connect(self._onSelectVideosClicked)

    def _onSelectVideosClicked(self) -> None:
        from app.services.task_service import taskService
        dialog = VideoSelectDialog(self._task.files, self.window())
        try:
            if dialog.exec():
                taskService.applySelection(self._task, dialog.selectedIndices())
                self.refresh(force=True)
        finally:
            dialog.deleteLater()

    def _buildProgressBar(self) -> QWidget:
        bar = ProgressBar(self)
        bar.setCustomBackgroundColor(QColor(0, 0, 0, 0), QColor(0, 0, 0, 0))
        return bar

    def refresh(self, force: bool = False) -> None:
        super().refresh(force=force)
        task: YouTubeTask = self._task
        if task.status != TaskStatus.RUNNING:
            if task.status == TaskStatus.COMPLETED and task.isPlaylist:
                videoCount = len(task.steps) // STEPS_PER_VIDEO
                receivedBytes = sum(s.receivedBytes for s in task.steps)
                self.sizeLabel.setText(
                    self.tr("{0} 个视频 · {1}").format(videoCount, toReadableSize(receivedBytes))
                )
                self.sizeLabel.show()
            return

        currentStep = next((s for s in task.steps if s.status == TaskStatus.RUNNING), None)
        if not currentStep:
            return

        fileIndex = getattr(currentStep, "fileIndex", 0)
        stepInGroup = currentStep.stepIndex - fileIndex * STEPS_PER_VIDEO
        label = STEP_LABELS.get(stepInGroup, "")

        if task.isPlaylist:
            videoCount = len(task.steps) // STEPS_PER_VIDEO
            videoStem = getattr(currentStep, "videoStem", "") or task.name
            if label:
                self.nameLabel.setText(f"{videoStem} ({fileIndex + 1}/{videoCount} · {label})")
        elif label:
            self.nameLabel.setText(f"{task.name} ({label})")
