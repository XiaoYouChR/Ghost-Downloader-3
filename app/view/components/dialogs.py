from typing import Dict, Any, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QAbstractItemView, \
    QHeaderView, QTableWidgetItem
from qfluentwidgets import (
    MessageBoxBase, SubtitleLabel, BodyLabel, CheckBox,
    CaptionLabel, FluentIcon, TextEdit, TableWidget, PrimaryToolButton, ToolButton
)

from app.supports.config import AUTHOR_URL
from app.supports.utils import getLocalTimeFromGithubApiTime, getReadableSize


class DeleteTaskDialog(MessageBoxBase):

    def __init__(self, parent=None, showCheckBox=True, deleteOnClose=True):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(self.tr("删除任务"), self)
        self.contentLabel = BodyLabel(
            self.tr("确定要删除此任务吗？"), self)
        self.deleteFileCheckBox = CheckBox(self.tr("删除文件"), self)

        self.deleteFileCheckBox.setVisible(showCheckBox)

        if deleteOnClose:
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self.initWidget()

    def initWidget(self):
        self.deleteFileCheckBox.setChecked(True)
        self.widget.setMinimumWidth(330)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(12)
        self.viewLayout.addWidget(self.contentLabel)
        self.viewLayout.addSpacing(10)
        self.viewLayout.addWidget(self.deleteFileCheckBox)


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
            self.detailButton.clicked.connect(lambda: QDesktopServices.openUrl(htmlUrl))

        self.sponsorButton.clicked.connect(lambda: QDesktopServices.openUrl(AUTHOR_URL))

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
        tableViewInfos = []

        for asset in assets:
            tableViewInfos.append([
                asset["name"],
                getReadableSize(asset["size"]),
                str(asset["download_count"]),
                asset["browser_download_url"]
            ])

        self.tableView.setRowCount(len(assets))
        
        for row, rowData in enumerate(tableViewInfos):
            for col in range(3):
                item = QTableWidgetItem(rowData[col])
                # 在第一列存储下载链接
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, rowData[3])
                self.tableView.setItem(row, col, item)

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
