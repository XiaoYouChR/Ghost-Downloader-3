from typing import Any, List, Dict

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QSizePolicy, QAbstractItemView, QHeaderView, QTableWidgetItem, QHBoxLayout
from qfluentwidgets import MessageBoxBase, SubtitleLabel, CaptionLabel, ToolButton, FluentIcon, TextEdit, \
    PrimaryToolButton, TableWidget

from app.supports.config import AUTHOR_URL
from app.supports.utils import getLocalTimeFromGithubApiTime, getReadableSize


class ReleaseInfoDialog(MessageBoxBase):
    def __init__(self, releaseData: dict[str, Any], parent=None, deleteOnClose=True):
        super().__init__(parent)
        self.releaseData = releaseData
        self.versionLabel = SubtitleLabel(self)
        self.dateLabel = CaptionLabel(self)
        self.prereleaseLabel = None
        self.detailButton = None
        self.sponsorButton = ToolButton(FluentIcon.HEART, self)
        # content components
        self.descriptionEdit = TextEdit(self)
        self.tableView = None

        if deleteOnClose:
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self.initWidget()
        self.initLayout()

    def initWidget(self):
        self.setDraggable(True)
        self.widget.setMinimumSize(620, 620)

        self._initTitleComponents()
        self._initContentComponents()
        self._initTableComponents()

    def _initTitleComponents(self):
        """初始化标题栏组件"""
        versionName = self.releaseData.get("name", "Release")
        self.versionLabel.setText(versionName)

        publishedAt = self.releaseData.get("published_at", "")
        if publishedAt:
            publishDate = getLocalTimeFromGithubApiTime(publishedAt)
        else:
            publishDate = "Unknown"
        self.dateLabel.setText(self.tr("发布时间: ") + publishDate)

        if self.releaseData.get("prerelease", False):
            self.prereleaseLabel = CaptionLabel(self.tr("⚠️ 预发布版本"), self)

        htmlUrl = self.releaseData.get("html_url", "")
        if htmlUrl:
            self.detailButton = PrimaryToolButton(FluentIcon.LINK, self)
            self.detailButton.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(htmlUrl)))

        self.sponsorButton.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(AUTHOR_URL)))

    def _initContentComponents(self):
        """初始化内容组件"""
        description = self.releaseData.get("body", "暂无更新说明")
        self.descriptionEdit.setObjectName(u"descriptionEdit")

        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.descriptionEdit.setSizePolicy(sizePolicy)

        self.descriptionEdit.setReadOnly(True)
        self.descriptionEdit.setMarkdown(description)

    def _initTableComponents(self):
        """初始化表格组件"""
        assets = self.releaseData.get("assets", [])
        if not assets:
            return

        self.tableView = TableWidget(self)
        self.tableView.setObjectName(u"tableView")
        self.tableView.setFixedHeight(150)

        tableSizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.tableView.setSizePolicy(tableSizePolicy)

        self.tableView.setBorderVisible(True)
        self.tableView.setBorderRadius(8)
        self.tableView.setWordWrap(False)
        self.tableView.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tableView.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tableView.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tableView.setColumnCount(3)
        self.tableView.verticalHeader().setVisible(False)
        self.tableView.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        # 填充表格数据
        self._populateTableData(assets)

        # 设置表头标签
        self.tableView.setHorizontalHeaderLabels([
            self.tr('文件名'),
            self.tr('文件大小'),
            self.tr('下载次数')
        ])

    def _populateTableData(self, assets: List[Dict[str, Any]]):
        """填充表格数据"""
        self.tableView.setRowCount(len(assets))

        for row, asset in enumerate(assets):
            nameItem = QTableWidgetItem(asset["name"])
            nameItem.setData(Qt.ItemDataRole.UserRole, asset)
            self.tableView.setItem(row, 0, nameItem)
            self.tableView.setItem(row, 1, QTableWidgetItem(getReadableSize(asset["size"])))
            self.tableView.setItem(row, 2, QTableWidgetItem(str(asset["download_count"])))

    def selectedAsset(self) -> dict[str, Any] | None:
        item = self.tableView.item(self.tableView.currentRow(), 0)
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def validate(self) -> bool:
        return self.selectedAsset() is not None

    def initLayout(self):
        """初始化布局"""
        titleLayout = QHBoxLayout()
        titleLayout.setContentsMargins(0, 0, 0, 0)
        titleLayout.setSpacing(6)
        titleLayout.addWidget(self.versionLabel)
        titleLayout.addWidget(self.dateLabel)
        if self.prereleaseLabel:
            titleLayout.addWidget(self.prereleaseLabel)
        titleLayout.addStretch()
        if self.detailButton:
            titleLayout.addWidget(self.detailButton)
        titleLayout.addWidget(self.sponsorButton)

        self.viewLayout.addLayout(titleLayout)
        self.viewLayout.addSpacing(12)
        self.viewLayout.addWidget(self.descriptionEdit)
        if self.tableView:
            self.viewLayout.addWidget(self.tableView)
