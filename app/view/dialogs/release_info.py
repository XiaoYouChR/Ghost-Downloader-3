from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QEasingCurve, QItemSelectionModel, QParallelAnimationGroup,
    QPropertyAnimation, Qt, QUrl,
)
from PySide6.QtGui import QColor, QDesktopServices, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QGraphicsOpacityEffect,
    QHeaderView, QHBoxLayout, QSizePolicy, QWidget,
)
from qfluentwidgets import (
    CaptionLabel, FluentIcon, MessageBoxBase,
    PrimaryToolButton, SubtitleLabel, ToolButton, ToolTipFilter,
)

from app.config.constants import AUTHOR_URL
from app.format import toReadableSize
from app.update import bestAsset
from app.view.components.markdown_viewer import MarkdownViewer
from app.view.components.tree_view import AutoSizingTreeView

if TYPE_CHECKING:
    from app.update import Release, ReleaseAsset


class ReleaseInfoDialog(MessageBoxBase):
    def __init__(self, release: Release, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._release = release

        self.versionLabel = SubtitleLabel(release.version, self)
        self.dateLabel = CaptionLabel(release.publishedAt[:10] if release.publishedAt else "", self)
        self.prereleaseLabel = CaptionLabel(self.tr("⚠️ 预发布版本"), self)
        self.detailButton = PrimaryToolButton(FluentIcon.LINK, self)
        self.sponsorButton = ToolButton(FluentIcon.HEART, self)
        self.descriptionEdit = MarkdownViewer(self, minimumVisibleLines=5, maximumVisibleLines=16)
        self.assetView = AutoSizingTreeView(self, minimumVisibleRows=1, maximumVisibleRows=6)
        self.assetModel = QStandardItemModel(self.assetView)
        self.titleLayout = QHBoxLayout()

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.setShadowEffect(60, (0, 10), QColor(0, 0, 0, 50))
        self.setMaskColor(QColor(0, 0, 0, 76))
        self.widget.setMinimumWidth(min(580, self.width() - 48))
        self.yesButton.setText(self.tr("下载"))
        self.versionLabel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.prereleaseLabel.setVisible(self._release.prerelease)
        self.detailButton.setToolTip(self.tr("打开发布页"))
        self.detailButton.installEventFilter(ToolTipFilter(self.detailButton))
        self.sponsorButton.setToolTip(self.tr("赞助作者"))
        self.sponsorButton.installEventFilter(ToolTipFilter(self.sponsorButton))

        self.descriptionEdit.setMarkdown(self._release.body or self.tr("暂无更新说明"))

        self.assetView.setRootIsDecorated(False)
        self.assetView.setUniformRowHeights(True)
        self.assetView.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.assetView.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.assetView.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self.assetModel.setHorizontalHeaderLabels([self.tr("文件名"), self.tr("大小"), self.tr("下载次数")])
        self.assetView.setModel(self.assetModel)
        self.assetView.header().setStretchLastSection(True)
        self.assetView.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.assetView.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

        best = bestAsset(self._release)
        bestRow = -1

        for i, asset in enumerate(self._release.assets):
            row = [
                QStandardItem(asset.name),
                QStandardItem(toReadableSize(asset.size)),
                QStandardItem(str(asset.downloadCount)),
            ]
            row[0].setData(asset, Qt.ItemDataRole.UserRole)
            for item in row:
                item.setEditable(False)
            self.assetModel.appendRow(row)
            if best is not None and asset.name == best.name:
                bestRow = i

        self.assetView.setVisible(bool(self._release.assets))
        if bestRow >= 0:
            index = self.assetModel.index(bestRow, 0)
            self.assetView.setCurrentIndex(index)
            sm = self.assetView.selectionModel()
            if sm is not None:
                sm.select(index, QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows)

        if self._release.assets:
            needed = sum(self.assetView.sizeHintForColumn(i) for i in range(self.assetModel.columnCount()))
            self.widget.setMinimumWidth(max(self.widget.minimumWidth(), needed + 48 + 20))

    def _initLayout(self) -> None:
        self.titleLayout.setContentsMargins(0, 0, 0, 0)
        self.titleLayout.setSpacing(6)
        self.titleLayout.addWidget(self.versionLabel)
        self.titleLayout.addWidget(self.dateLabel)
        self.titleLayout.addWidget(self.prereleaseLabel)
        self.titleLayout.addStretch(1)
        self.titleLayout.addWidget(self.detailButton)
        self.titleLayout.addWidget(self.sponsorButton)

        self.viewLayout.addLayout(self.titleLayout)
        self.viewLayout.addSpacing(12)
        self.viewLayout.addWidget(self.descriptionEdit)
        self.viewLayout.addWidget(self.assetView)

    def _bind(self) -> None:
        self.detailButton.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self._release.pageUrl)))
        self.sponsorButton.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(AUTHOR_URL)))

    def selectedAsset(self) -> ReleaseAsset | None:
        index = self.assetView.currentIndex()
        if not index.isValid():
            return None
        item = self.assetModel.itemFromIndex(index.siblingAtColumn(0))
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def validate(self) -> bool:
        return self.selectedAsset() is not None

    def _createOpacityAnimation(
        self, widget: QWidget, start: float, end: float, duration: int, curve: QEasingCurve.Type
    ) -> QPropertyAnimation:
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        ani = QPropertyAnimation(effect, b"opacity", self)
        ani.setStartValue(start)
        ani.setEndValue(end)
        ani.setDuration(duration)
        ani.setEasingCurve(curve)
        return ani

    def showEvent(self, e) -> None:
        parent = self.parent()
        if parent is not None:
            widthLimit = parent.width() - 24
            if 0 < widthLimit < self.widget.width():
                self.widget.setFixedWidth(widthLimit)

        QDialog.showEvent(self, e)

        self._showGroup = QParallelAnimationGroup(self)
        self._showGroup.addAnimation(
            self._createOpacityAnimation(self.windowMask, 0, 1, 200, QEasingCurve.Type.OutQuad)
        )
        self._showGroup.addAnimation(
            self._createOpacityAnimation(self.widget, 0, 1, 200, QEasingCurve.Type.OutQuad)
        )

        def _onShowFinished():
            self.windowMask.setGraphicsEffect(None)
            self.setShadowEffect(60, (0, 10), QColor(0, 0, 0, 50))

        self._showGroup.finished.connect(_onShowFinished)
        self._showGroup.start()

    def done(self, code: int) -> None:
        self.windowMask.setGraphicsEffect(None)
        self.widget.setGraphicsEffect(None)

        self._doneGroup = QParallelAnimationGroup(self)
        self._doneGroup.addAnimation(
            self._createOpacityAnimation(self.windowMask, 1, 0, 120, QEasingCurve.Type.InQuad)
        )
        self._doneGroup.addAnimation(
            self._createOpacityAnimation(self.widget, 1, 0, 120, QEasingCurve.Type.InQuad)
        )
        self._doneGroup.finished.connect(lambda: self._onDone(code))
        self._doneGroup.start()
