from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QHBoxLayout, QSizePolicy
from qfluentwidgets import (
    CaptionLabel, FluentIcon, MessageBoxBase,
    PrimaryToolButton, SubtitleLabel, ToolButton, ToolTipFilter,
)

from app.config.constants import AUTHOR_URL
from app.format import toReadableSize
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
        self.assetView.header().setStretchLastSection(False)
        self.assetView.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.assetView.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.assetView.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        for asset in self._release.assets:
            row = [
                QStandardItem(asset.name),
                QStandardItem(toReadableSize(asset.size)),
                QStandardItem(str(asset.downloadCount)),
            ]
            row[0].setData(asset, Qt.ItemDataRole.UserRole)
            for item in row:
                item.setEditable(False)
            self.assetModel.appendRow(row)

        self.assetView.setVisible(bool(self._release.assets))

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
