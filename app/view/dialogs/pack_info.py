from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget
from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon, MessageBoxBase, SubtitleLabel,
    TransparentToolButton,
)

if TYPE_CHECKING:
    from app.models.pack import FeaturePack
    from app.services.update_service import UpdateService

STATUS_SUCCESS_COLORS = ("#0F7B0F", "#6CCB5F")
STATUS_AVAILABLE_COLORS = ("#9D5D00", "#FFC83D")
STATUS_DOWNLOADING_COLORS = ("#0067C0", "#60CDFF")
STATUS_FAILED_COLORS = ("#C42B1C", "#FF99A4")


class PackRow(QWidget):
    def __init__(self, pack: FeaturePack, onRetry, parent=None):
        super().__init__(parent)
        self._onRetry = onRetry
        self._initWidget(pack)
        self._initLayout()
        self._bind()

    def _initWidget(self, pack: FeaturePack) -> None:
        displayName = type(pack).__name__
        self.nameLabel = BodyLabel(displayName, self)
        self.nameLabel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.versionLabel = CaptionLabel(f"v{pack.manifest.version}", self)
        self.statusLabel = CaptionLabel("✓", self)
        self.statusLabel.setFixedWidth(18)
        self.statusLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.statusLabel.setTextColor(*STATUS_SUCCESS_COLORS)
        self.retryButton = TransparentToolButton(FluentIcon.SYNC, self)
        self.retryButton.setFixedSize(24, 24)
        self.retryButton.setIconSize(self.retryButton.size() / 2)
        self.retryButton.hide()

    def _initLayout(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.nameLabel)
        layout.addWidget(self.versionLabel)
        layout.addWidget(self.statusLabel)
        layout.addWidget(self.retryButton)

    def _bind(self) -> None:
        self.retryButton.clicked.connect(self._onRetry)

    def update(self, info) -> None:
        from app.services.update_service import UpdateState

        if info.state == UpdateState.AVAILABLE:
            self.statusLabel.setText("↑")
            self.statusLabel.setTextColor(*STATUS_AVAILABLE_COLORS)
            self.retryButton.hide()
        elif info.state == UpdateState.DOWNLOADING:
            self.statusLabel.setText("↓")
            self.statusLabel.setTextColor(*STATUS_DOWNLOADING_COLORS)
            self.retryButton.hide()
        elif info.state == UpdateState.READY:
            self.statusLabel.setText("✓")
            self.statusLabel.setTextColor(*STATUS_SUCCESS_COLORS)
            self.retryButton.hide()
        elif info.state == UpdateState.FAILED:
            self.statusLabel.setText("✗")
            self.statusLabel.setTextColor(*STATUS_FAILED_COLORS)
            self.retryButton.show()


class PackInfoDialog(MessageBoxBase):
    def __init__(self, packs: list[FeaturePack], updateService: UpdateService, parent=None):
        super().__init__(parent)
        self._updateService = updateService
        self._rows: dict[str, PackRow] = {}
        self._initWidget(packs)
        self._bind()

    def _initWidget(self, packs: list[FeaturePack]) -> None:
        self.titleLabel = SubtitleLabel(self.tr("功能包"), self)
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(8)
        self.widget.setMinimumWidth(400)
        self.yesButton.setText(self.tr("关闭"))
        self.cancelButton.hide()

        for pack in packs:
            if pack.manifest is None:
                continue
            manifestName = pack.manifest.name
            row = PackRow(pack, lambda n=manifestName: self._updateService.download(n), self)
            self._rows[manifestName] = row
            self.viewLayout.addWidget(row)

    def _bind(self) -> None:
        self._updateService.changed.connect(self._onUpdateChanged)

    def _onUpdateChanged(self, info) -> None:
        row = self._rows.get(info.targetId)
        if row is not None:
            row.update(info)
