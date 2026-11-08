from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel, CaptionLabel, InfoBar, InfoBarIcon, InfoBarPosition, MessageBoxBase,
    SubtitleLabel, ToolTipFilter,
)

from app.i18n import toLocalizedError
from app.services.update_service import UpdateState
from app.view.components.scroll_area import ScrollArea

if TYPE_CHECKING:
    from app.models.pack import FeaturePack
    from app.services.update_service import UpdateInfo, UpdateService

SECONDARY_COLORS = (QColor(96, 96, 96), QColor(206, 206, 206))
STATE_COLORS = {
    UpdateState.DOWNLOADING: ("#0067C0", "#60CDFF"),
    UpdateState.READY: ("#0F7B0F", "#6CCB5F"),
    UpdateState.FAILED: ("#C42B1C", "#FF99A4"),
}


class PackRow(QWidget):
    def __init__(self, pack: FeaturePack, parent=None):
        super().__init__(parent)
        self._initWidget(pack)
        self._initLayout()

    def _initWidget(self, pack: FeaturePack) -> None:
        className = type(pack).__name__
        title = QCoreApplication.translate(className, pack.capturedLinks) if pack.capturedLinks else className
        self.titleLabel = BodyLabel(title, self)
        self.titleLabel.setWordWrap(True)
        self.nameLabel = CaptionLabel(className, self)
        self.nameLabel.setTextColor(*SECONDARY_COLORS)
        self.nameLabel.setVisible(bool(pack.capturedLinks))
        self.stateLabel = CaptionLabel(self)
        self.stateLabel.installEventFilter(ToolTipFilter(self.stateLabel))
        self.stateLabel.hide()
        self.versionLabel = CaptionLabel(f"v{pack.manifest.version}", self)
        self.versionLabel.setTextColor(*SECONDARY_COLORS)

    def _initLayout(self) -> None:
        textLayout = QVBoxLayout()
        textLayout.setSpacing(0)
        textLayout.addWidget(self.titleLabel)
        textLayout.addWidget(self.nameLabel)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(12)
        layout.addLayout(textLayout, 1)
        layout.addWidget(self.stateLabel)
        layout.addWidget(self.versionLabel)

    def setInfo(self, info: UpdateInfo) -> None:
        texts = {
            UpdateState.DOWNLOADING: self.tr("更新中…"),
            UpdateState.READY: self.tr("重启后生效"),
            UpdateState.FAILED: self.tr("更新失败"),
        }
        text = texts.get(info.state)
        self.stateLabel.setVisible(text is not None)
        if text is None:
            return
        self.stateLabel.setText(text)
        self.stateLabel.setTextColor(*STATE_COLORS[info.state])
        self.stateLabel.setToolTip(toLocalizedError(info.error) if info.state == UpdateState.FAILED else "")


class PackList(ScrollArea):
    def sizeHint(self) -> QSize:
        return self.widget().sizeHint()


class PackInfoDialog(MessageBoxBase):
    def __init__(self, packs: list[FeaturePack], updateService: UpdateService, parent=None):
        super().__init__(parent)
        self._updateService = updateService
        self._rows: dict[str, PackRow] = {}
        self._initWidget(packs)
        self._initLayout()
        self._bind()
        for packId in self._rows:
            info = updateService.infoById(packId)
            if info is not None:
                self._onUpdateChanged(info)

    def _initWidget(self, packs: list[FeaturePack]) -> None:
        self.widget.setMinimumWidth(400)
        self.yesButton.setText(self.tr("关闭"))
        self.cancelButton.hide()

        self.titleLabel = SubtitleLabel(self.tr("功能包"), self)
        self.readyBar = InfoBar(InfoBarIcon.SUCCESS, self.tr("功能包已更新"), self.tr("重启软件后生效"),
                                Qt.Orientation.Horizontal,
                                isClosable=False, duration=-1, position=InfoBarPosition.NONE, parent=self.widget)
        self.readyBar.setGraphicsEffect(None)
        self.readyBar.textLayout.setStretchFactor(self.readyBar.titleLabel, 0)
        self.readyBar.hide()

        self.scrollArea = PackList(self.widget)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scrollWidget = QWidget()

        self.packRows: list[PackRow] = []
        self.helperRows: list[PackRow] = []
        for pack in packs:
            row = PackRow(pack, self.scrollWidget)
            self._rows[pack.manifest.name] = row
            (self.packRows if pack.capturedLinks else self.helperRows).append(row)

        self.helperLabel = CaptionLabel(self.tr("辅助组件"), self.scrollWidget)
        self.helperLabel.setTextColor(*SECONDARY_COLORS)
        self.helperLabel.setVisible(bool(self.helperRows))

    def _initLayout(self) -> None:
        scrollLayout = QVBoxLayout(self.scrollWidget)
        scrollLayout.setContentsMargins(0, 0, 16, 0)
        scrollLayout.setSpacing(0)
        for row in self.packRows:
            scrollLayout.addWidget(row)
        scrollLayout.addSpacing(16)
        scrollLayout.addWidget(self.helperLabel)
        for row in self.helperRows:
            scrollLayout.addWidget(row)
        self.scrollArea.setWidget(self.scrollWidget)
        self.scrollArea.enableTransparentBackground()

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.readyBar)
        self.viewLayout.addWidget(self.scrollArea)

    def _bind(self) -> None:
        self._updateService.changed.connect(self._onUpdateChanged, owner=self)

    def _onUpdateChanged(self, info: UpdateInfo) -> None:
        row = self._rows.get(info.targetId)
        if row is None:
            return
        row.setInfo(info)
        if info.state == UpdateState.READY:
            self.readyBar.show()
