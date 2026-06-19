from PySide6.QtWidgets import QWidget
from qfluentwidgets import ComboBox

from app.bases.models import SpecialFileSize, Task
from app.services.core_service import coreService
from app.supports.utils import getProxies, toReadableSize
from app.view.components.cards import UniversalResultCard
from .task import DEFAULT_VIDEO_FORMAT, probeMediaInfo

_QUALITY_TIERS = (
    ("最佳画质", DEFAULT_VIDEO_FORMAT),
    ("1080p", "bv*[height<=1080]+ba/b[height<=1080]"),
    ("720p", "bv*[height<=720]+ba/b[height<=720]"),
    ("480p", "bv*[height<=480]+ba/b[height<=480]"),
    ("仅音频", "ba/b"),
)
_UNKNOWN_SIZES = (SpecialFileSize.UNKNOWN, SpecialFileSize.NOT_SUPPORTED)


class YtDlpResultCard(UniversalResultCard):
    def __init__(self, task: Task, parent: QWidget = None):
        super().__init__(task, parent)
        self._pendingFormat = self.task.stage.videoFormat
        self._sizeByFormat: dict[str, int] = {}
        if self.task.fileSize not in _UNKNOWN_SIZES:
            self._sizeByFormat[self._pendingFormat] = self.task.fileSize
        self._renderSize(self.task.fileSize)
        self.qualityCombo.currentIndexChanged.connect(lambda _: self._onQualityChanged())

    def initWidget(self):
        super().initWidget()
        self.qualityCombo = ComboBox(self)
        self.qualityCombo.setMinimumWidth(140)
        selectedIndex = 0
        for index, (label, expr) in enumerate(_QUALITY_TIERS):
            self.qualityCombo.addItem(label, userData=expr)
            if expr == self.task.stage.videoFormat:
                selectedIndex = index
        self.qualityCombo.setCurrentIndex(selectedIndex)

    def initLayout(self):
        super().initLayout()
        self.mainLayout.insertWidget(self.mainLayout.indexOf(self.sizeLabel), self.qualityCombo)

    def _onQualityChanged(self):
        videoFormat = self.qualityCombo.currentData() or DEFAULT_VIDEO_FORMAT
        self.task.applySettings({"videoFormat": videoFormat})
        self._pendingFormat = videoFormat
        if videoFormat in self._sizeByFormat:
            self._applySize(self._sizeByFormat[videoFormat])
            return
        self.sizeLabel.setText(self.tr("计算中…"))
        coreService.runCoroutine(
            probeMediaInfo(self.task.url, getProxies(), videoFormat, self.task.stage.headers),
            lambda result, error, fmt=videoFormat: self._onSizeProbed(fmt, result, error),
        )

    def _onSizeProbed(self, videoFormat: str, result, error):
        if videoFormat != self._pendingFormat:
            return
        if error or not result:
            self._renderSize(SpecialFileSize.UNKNOWN)
            return
        _, size = result
        self._sizeByFormat[videoFormat] = size
        self._applySize(size)

    def _applySize(self, size: int):
        self.task.fileSize = size
        self._renderSize(size)

    def _renderSize(self, size: int):
        if size in _UNKNOWN_SIZES:
            self.sizeLabel.setText(self.tr("未知"))
        else:
            self.sizeLabel.setText(self.tr("约 {0}").format(toReadableSize(size)))
