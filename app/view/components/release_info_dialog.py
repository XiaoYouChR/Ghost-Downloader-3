from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QHBoxLayout, QPlainTextEdit, QSizePolicy
from qfluentwidgets import CaptionLabel, FluentIcon, MessageBoxBase, PrimaryToolButton, SubtitleLabel, ToolButton

from app.supports.config import AUTHOR_URL
from app.supports.utils import getLocalTimeFromGithubApiTime, toReadableSize
from app.view.components.editors import AutoSizingEdit
from app.view.components.tree_view import AutoSizingTreeView

RELEASE_NOTES_COLUMNS = 76
RELEASE_NOTES_VISIBLE_LINES = 16
ASSET_VISIBLE_ROWS = 6


class ReleaseInfoDialog(MessageBoxBase):
    def __init__(self, releaseData: dict[str, Any], parent=None, deleteOnClose: bool = True) -> None:
        super().__init__(parent)
        self._releaseData = releaseData

        # instant widget
        self.versionLabel = SubtitleLabel(self)
        self.dateLabel = CaptionLabel(self)
        self.prereleaseLabel = CaptionLabel(self.tr("⚠️ 预发布版本"), self)
        self.detailButton = PrimaryToolButton(FluentIcon.LINK, self)
        self.sponsorButton = ToolButton(FluentIcon.HEART, self)
        self.descriptionEdit = AutoSizingEdit(self, 5, RELEASE_NOTES_VISIBLE_LINES)
        self.assetTreeView = AutoSizingTreeView(self, 1, ASSET_VISIBLE_ROWS)
        self.assetModel = QStandardItemModel(self.assetTreeView)

        # instant layout
        self.titleLayout = QHBoxLayout()

        self._deleteOnClose = deleteOnClose

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.setDraggable(True)
        self.setObjectName("ReleaseInfoDialog")

        if self._deleteOnClose:
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self._initReleaseHeader()
        self._initReleaseNotes()
        self._initAssetTree()

    def _initReleaseHeader(self) -> None:
        versionName = self._releaseData.get("name") or self.tr("Release")
        self.versionLabel.setText(versionName)
        self.versionLabel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        publishedAt = self._releaseData.get("published_at", "")
        if publishedAt:
            publishDate = getLocalTimeFromGithubApiTime(publishedAt)
        else:
            publishDate = self.tr("Unknown")
        self.dateLabel.setText(self.tr("发布时间: ") + publishDate)

        self.prereleaseLabel.setVisible(self._releaseData.get("prerelease", False))
        self.detailButton.setVisible(bool(self._releaseData.get("html_url", "")))
        self.detailButton.setToolTip(self.tr("打开发布页"))
        self.sponsorButton.setToolTip(self.tr("赞助作者"))
        
    def _preprocess_markdown_alerts(self, text: str) -> str:
        """兼容GitHub Alerts语法转换，为Qt支持的格式"""
        if not text:
            return text
            
        # 字符串末尾写两个空格是为了强制换行
        alerts = {
            "[!NOTE]": "**ℹ️ 提示 (NOTE)**  ",
            "[!TIP]": "**💡 技巧 (TIP)**  ",
            "[!IMPORTANT]": "**✨ 重要 (IMPORTANT)**  ",
            "[!WARNING]": "**⚠️ 警告 (WARNING)**  ",
            "[!CAUTION]": "**🚨 危险 (CAUTION)**  "
        }
        
        # 遍历替换
        for gh_tag, qt_tag in alerts.items():
            text = text.replace(gh_tag, qt_tag)
            
        return text

    def _initReleaseNotes(self) -> None:
        description = self._releaseData.get("body") or self.tr("暂无更新说明")
        
        # 应用 Markdown Alert 预处理
        description = self._preprocess_markdown_alerts(description)
        
        textWidth = self.fontMetrics().averageCharWidth() * RELEASE_NOTES_COLUMNS

        self.descriptionEdit.setObjectName("descriptionEdit")
        self.descriptionEdit.setMinimumWidth(textWidth)
        self.descriptionEdit.setReadOnly(True)
        
        # 判断基类控件是否支持 setMarkdown
        if hasattr(self.descriptionEdit, "setMarkdown"):
            self.descriptionEdit.setMarkdown(description)
        else:
            # 降级处理
            self.descriptionEdit.setPlainText(description)
            
        if hasattr(self.descriptionEdit, "setLineWrapMode"):
            self.descriptionEdit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)

    def _initAssetTree(self) -> None:
        self.assetTreeView.setObjectName("assetTreeView")
        self.assetTreeView.setBorderVisible(True)
        self.assetTreeView.setBorderRadius(8)
        self.assetTreeView.setWordWrap(False)
        self.assetTreeView.setRootIsDecorated(False)
        self.assetTreeView.setUniformRowHeights(True)
        self.assetTreeView.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.assetTreeView.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.assetTreeView.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self.assetModel.setHorizontalHeaderLabels([
            self.tr("文件名"),
            self.tr("文件大小"),
            self.tr("下载次数"),
        ])
        self.assetTreeView.setModel(self.assetModel)
        self.assetTreeView.header().setStretchLastSection(False)
        self.assetTreeView.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.assetTreeView.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.assetTreeView.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        assets = self._releaseData.get("assets", [])
        for asset in assets:
            self._appendAsset(asset)

        self.assetTreeView.setVisible(bool(assets))

    def _appendAsset(self, asset: dict[str, Any]) -> None:
        nameItem = QStandardItem(asset["name"])
        nameItem.setData(asset, Qt.ItemDataRole.UserRole)
        sizeItem = QStandardItem(toReadableSize(asset["size"]))
        downloadCountItem = QStandardItem(str(asset["download_count"]))

        for item in (nameItem, sizeItem, downloadCountItem):
            item.setEditable(False)

        self.assetModel.appendRow([nameItem, sizeItem, downloadCountItem])

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
        self.viewLayout.addWidget(self.assetTreeView)

    def _bind(self) -> None:
        self.detailButton.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(self._releaseData.get("html_url", "")))
        )
        self.sponsorButton.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(AUTHOR_URL)))

    def selectedAsset(self) -> dict[str, Any] | None:
        index = self.assetTreeView.currentIndex()
        if not index.isValid():
            return None

        item = self.assetModel.itemFromIndex(index.siblingAtColumn(0))
        if item is None:
            return None

        asset = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(asset, dict):
            return None
        return asset

    def validate(self) -> bool:
        return self.selectedAsset() is not None