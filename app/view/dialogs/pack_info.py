from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon, InfoBadge, InfoBar, InfoBarPosition,
    MessageBoxBase, PushButton, SubtitleLabel, SwitchButton,
    TransparentToolButton,
)
from qfluentwidgets.components.widgets.info_badge import InfoLevel

from app.config.cfg import cfg
from app.config.paths import IS_COMPILED
from app.view.components.scroll_area import ScrollArea

if TYPE_CHECKING:
    from app.models.pack import FeaturePack
    from app.services.update_service import UpdateService

PACK_ROW_HEIGHT = 36
PACK_LIST_WIDTH = 440
MAX_VISIBLE_PACK_ROWS = 6


class PackRow(QWidget):
    def __init__(self, pack: FeaturePack, onRetry, parent=None):
        super().__init__(parent)
        self._onRetry = onRetry
        self._initWidget(pack)
        self._initLayout()
        self._bind()

    def _initWidget(self, pack: FeaturePack) -> None:
        self.setFixedHeight(PACK_ROW_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        displayName = type(pack).__name__
        self.nameLabel = BodyLabel(displayName, self)
        self.nameLabel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.nameLabel.setToolTip(displayName)
        self.versionLabel = CaptionLabel(f"v{pack.manifest.version}", self)
        self.badge = InfoBadge.success("✓", self)
        self.updateButton = TransparentToolButton(FluentIcon.DOWNLOAD, self)
        self.updateButton.setFixedSize(24, 24)
        self.updateButton.setIconSize(self.updateButton.size() / 2)
        self.updateButton.hide()

    def _initLayout(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.nameLabel)
        layout.addWidget(self.versionLabel)
        layout.addWidget(self.badge)
        layout.addWidget(self.updateButton)

    def _bind(self) -> None:
        self.updateButton.clicked.connect(self._onRetry)

    def update(self, info) -> None:
        from app.services.update_service import UpdateState

        if info.state == UpdateState.AVAILABLE:
            self.badge.setText("↑")
            self.badge.setLevel(InfoLevel.WARNING)
            self.updateButton.setIcon(FluentIcon.DOWNLOAD)
            self.updateButton.setToolTip(self.tr("更新"))
            self.updateButton.show()
        elif info.state == UpdateState.DOWNLOADING:
            self.badge.setText("↓")
            self.badge.setLevel(InfoLevel.INFOAMTION)
            self.updateButton.hide()
        elif info.state == UpdateState.READY:
            self.badge.setText("✓")
            self.badge.setLevel(InfoLevel.INFOAMTION)
            self.updateButton.hide()
        elif info.state == UpdateState.FAILED:
            self.badge.setText("✗")
            self.badge.setLevel(InfoLevel.ERROR)
            self.updateButton.setIcon(FluentIcon.SYNC)
            self.updateButton.setToolTip(self.tr("重试"))
            self.updateButton.show()


class PackInfoDialog(MessageBoxBase):
    def __init__(self, packs: list[FeaturePack], updateService: UpdateService, parent=None):
        super().__init__(parent)
        self._updateService = updateService
        self._rows: dict[str, PackRow] = {}
        self._isRefreshingPacks = False
        self._initWidget(packs)
        self._initLayout()
        self._bind()

    def _initWidget(self, packs: list[FeaturePack]) -> None:
        self.titleLabel = SubtitleLabel(self.tr("功能包"), self)
        self.autoUpdateLabel = BodyLabel(self.tr("自动更新功能包"), self)
        self.autoUpdateSwitch = SwitchButton(self)
        self.autoUpdateSwitch.setOnText("")
        self.autoUpdateSwitch.setOffText("")
        self.autoUpdateSwitch.setChecked(cfg.shouldAutoUpdatePacks.value)
        checkButtonText = (
            self.tr("更新功能包")
            if IS_COMPILED and cfg.shouldAutoUpdatePacks.value
            else self.tr("检查功能包更新")
        )
        self.checkButton = PushButton(FluentIcon.SYNC, checkButtonText, self)
        self.packListArea = ScrollArea(self.widget)
        self.packListWidget = QWidget(self.packListArea)
        self.packListLayout = QVBoxLayout(self.packListWidget)
        self.widget.setMinimumWidth(480)
        self.yesButton.setText(self.tr("关闭"))
        self.cancelButton.hide()

        for pack in packs:
            if pack.manifest is None:
                continue
            manifestName = pack.manifest.name
            row = PackRow(
                pack,
                lambda n=manifestName: self._updateService.download(n),
                self.packListWidget,
            )
            self._rows[manifestName] = row

        visibleRows = min(max(len(self._rows), 1), MAX_VISIBLE_PACK_ROWS)
        self.packListArea.setFixedWidth(PACK_LIST_WIDTH)
        self.packListArea.setFixedHeight(visibleRows * PACK_ROW_HEIGHT)
        self.packListWidget.setMinimumHeight(len(self._rows) * PACK_ROW_HEIGHT)
        self.packListArea.setWidget(self.packListWidget)
        self.packListArea.setWidgetResizable(True)
        self.packListArea.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.packListArea.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.packListArea.enableTransparentBackground()

    def _initLayout(self) -> None:
        titleLayout = QHBoxLayout()
        titleLayout.addWidget(self.titleLabel)
        titleLayout.addStretch(1)
        titleLayout.addWidget(self.checkButton)
        self.viewLayout.addLayout(titleLayout)
        self.viewLayout.addSpacing(8)

        autoUpdateLayout = QHBoxLayout()
        autoUpdateLayout.setContentsMargins(4, 0, 4, 0)
        autoUpdateLayout.addWidget(self.autoUpdateLabel)
        autoUpdateLayout.addStretch(1)
        autoUpdateLayout.addWidget(self.autoUpdateSwitch)
        self.viewLayout.addLayout(autoUpdateLayout)
        self.viewLayout.addSpacing(8)

        self.packListLayout.setContentsMargins(0, 0, 0, 0)
        self.packListLayout.setSpacing(0)
        for row in self._rows.values():
            self.packListLayout.addWidget(row)
        self.packListLayout.addStretch(1)
        self.viewLayout.addWidget(self.packListArea)

    def _bind(self) -> None:
        self._updateService.changed.connect(self._onUpdateChanged)
        self._updateService.packsRefreshed.connect(self._onPacksRefreshed)
        self.autoUpdateSwitch.checkedChanged.connect(self._onAutoUpdateChanged)
        self.checkButton.clicked.connect(self._onCheckClicked)

    def _onAutoUpdateChanged(self, enabled: bool) -> None:
        cfg.set(cfg.shouldAutoUpdatePacks, enabled)
        self.checkButton.setText(
            self.tr("更新功能包")
            if IS_COMPILED and enabled
            else self.tr("检查功能包更新")
        )

    def _onCheckClicked(self) -> None:
        if self._isRefreshingPacks:
            return
        self._isRefreshingPacks = True
        self.checkButton.setEnabled(False)
        InfoBar.info(
            self.tr("检查功能包更新"),
            self.tr("正在检查功能包更新..."),
            duration=1500,
            position=InfoBarPosition.BOTTOM_RIGHT,
            parent=self.window(),
        )
        self._updateService.refresh(
            shouldRefreshApp=False,
            shouldRefreshPacks=True,
        )

    def _onPacksRefreshed(self, availableCount: int, hasError: bool) -> None:
        if not self._isRefreshingPacks:
            return
        self._isRefreshingPacks = False
        self.checkButton.setEnabled(True)

        if hasError:
            InfoBar.error(
                self.tr("检查功能包更新失败"),
                self.tr("无法获取最新功能包版本信息"),
                duration=3000,
                position=InfoBarPosition.BOTTOM_RIGHT,
                parent=self.window(),
            )
            return
        if availableCount == 0:
            InfoBar.success(
                self.tr("所有功能包已是最新版本"),
                "",
                duration=3000,
                position=InfoBarPosition.BOTTOM_RIGHT,
                parent=self.window(),
            )
            return

        if IS_COMPILED and cfg.shouldAutoUpdatePacks.value:
            content = self.tr("检测到 {0} 个可用更新，正在下载").format(availableCount)
        else:
            content = self.tr("检测到 {0} 个可用更新，可点击对应功能包更新").format(availableCount)
        InfoBar.success(
            self.tr("发现功能包更新"),
            content,
            duration=4000,
            position=InfoBarPosition.BOTTOM_RIGHT,
            parent=self.window(),
        )

    def _onUpdateChanged(self, info) -> None:
        row = self._rows.get(info.targetId)
        if row is not None:
            row.update(info)
