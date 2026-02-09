from datetime import datetime
from typing import Dict, Any, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QScrollArea, QWidget
from qfluentwidgets import (
    MessageBoxBase, SubtitleLabel, BodyLabel, CheckBox,
    PrimaryPushButton, PushButton, CaptionLabel, FluentIcon
)


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

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.titleLabel)
        layout.addSpacing(12)
        layout.addWidget(self.contentLabel)
        layout.addSpacing(10)
        layout.addWidget(self.deleteFileCheckBox)
        self.viewLayout.addLayout(layout)


class ReleaseInfoDialog(MessageBoxBase):
    """GitHub Release 信息对话框"""

    def __init__(self, release_data: Dict[str, Any], parent=None, deleteOnClose=True):
        super().__init__(parent)
        self.release_data = release_data

        if deleteOnClose:
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self.initWidget()

    def initWidget(self):
        self.widget.setMinimumWidth(500)
        self.widget.setMinimumHeight(400)

        # 主容器
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 标题区域
        title_layout = QVBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(6)

        # 版本标题
        version_label = SubtitleLabel(self.release_data.get("name", "Release"), self)
        title_layout.addWidget(version_label)

        # 发布时间
        published_at = self.release_data.get("published_at", "")
        if published_at:
            try:
                pub_date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                date_str = pub_date.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                date_str = published_at
        else:
            date_str = "Unknown"

        date_label = CaptionLabel(self.tr("发布时间: ") + date_str, self)
        title_layout.addWidget(date_label)

        # Tag 和预发布标签
        tag_layout = QHBoxLayout()
        tag_layout.setContentsMargins(0, 0, 0, 0)
        tag_layout.setSpacing(8)

        tag_name = self.release_data.get("tag_name", "")
        tag_label = CaptionLabel(f"Tag: {tag_name}", self)
        tag_layout.addWidget(tag_label)

        if self.release_data.get("prerelease", False):
            prerelease_label = CaptionLabel(self.tr("⚠️ 预发布版本"), self)
            tag_layout.addWidget(prerelease_label)

        tag_layout.addStretch()
        title_layout.addLayout(tag_layout)

        main_layout.addLayout(title_layout)
        main_layout.addSpacing(12)

        # 发布说明区域（可滚动）
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; }")

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(12)

        # 发布说明标题
        changelog_title = CaptionLabel(self.tr("版本更新说明"), self)
        scroll_layout.addWidget(changelog_title)

        # 发布说明内容
        body = self.release_data.get("body", "")
        if body:
            body_label = BodyLabel(body, self)
            body_label.setWordWrap(True)
            scroll_layout.addWidget(body_label)
        else:
            empty_label = BodyLabel(self.tr("暂无更新说明"), self)
            scroll_layout.addWidget(empty_label)

        # 资源列表
        assets = self.release_data.get("assets", [])
        if assets:
            scroll_layout.addSpacing(12)
            assets_title = CaptionLabel(self.tr("下载资源"), self)
            scroll_layout.addWidget(assets_title)

            for asset in assets:
                asset_name = asset.get("name", "Unknown")
                size_bytes = asset.get("size", 0)
                size_str = self._format_size(size_bytes)
                download_count = asset.get("download_count", 0)

                asset_label = BodyLabel(
                    f"📦 {asset_name}\n"
                    f"   大小: {size_str} | 下载: {download_count}次",
                    self
                )
                asset_label.setWordWrap(True)
                scroll_layout.addWidget(asset_label)

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_widget)

        main_layout.addWidget(scroll_area)
        main_layout.addSpacing(12)

        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)

        # 查看详情按钮
        html_url = self.release_data.get("html_url", "")
        if html_url:
            view_btn = PrimaryPushButton(
                FluentIcon.LINK, self.tr("查看详情"), self
            )
            view_btn.clicked.connect(lambda: QDesktopServices.openUrl(html_url))
            button_layout.addWidget(view_btn)

        # 关闭按钮
        close_btn = PushButton(self.tr("关闭"), self)
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)

        main_layout.addLayout(button_layout)
        self.viewLayout.addLayout(main_layout)

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"
