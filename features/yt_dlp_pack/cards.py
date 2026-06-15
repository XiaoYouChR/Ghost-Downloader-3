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


class YtDlpResultCard(UniversalResultCard):
    def __init__(self, task: Task, parent: QWidget = None):
        super().__init__(task, parent)
        self._pendingFormat = self.task.stage.videoFormat
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
        videoFormat = self.qualityCombo.currentData() or _QUALITY_TIERS[0][1]
        self.task.applySettings({"videoFormat": videoFormat})
        self._pendingFormat = videoFormat
        self.sizeLabel.setText(self.tr("计算中…"))
        coreService.runCoroutine(
            probeMediaInfo(self.task.url, getProxies(), videoFormat, self.task.stage.headers),
            lambda result, error, fmt=videoFormat: self._onSizeProbed(fmt, result, error),
        )

    def _onSizeProbed(self, videoFormat: str, result, error):
        if videoFormat != self._pendingFormat:
            return  # 用户又改了档，丢弃过期结果
        size = result[1] if (not error and result) else SpecialFileSize.UNKNOWN
        self.task.fileSize = size
        self._renderSize(size)

    def _renderSize(self, size: int):
        if size in {SpecialFileSize.UNKNOWN, SpecialFileSize.NOT_SUPPORTED}:
            self.sizeLabel.setText(self.tr("未知"))
        else:
            self.sizeLabel.setText(self.tr("约 {0}").format(toReadableSize(size)))
