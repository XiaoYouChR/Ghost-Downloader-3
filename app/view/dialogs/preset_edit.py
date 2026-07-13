from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import (
    BodyLabel, DropDownPushButton, FluentIcon, LineEdit,
    MessageBoxBase, SubtitleLabel, TeachingTip, TeachingTipTailPosition,
    TransparentToolButton,
)

from app.view.components.editors import TokenLineEdit


class PresetEditDialog(MessageBoxBase):

    def __init__(self, parent=None, *, preset: dict | None = None):
        super().__init__(parent)
        self._preset = preset
        self._profileValue = preset.get("clientProfile", "") if preset else ""

        self.titleLabel = SubtitleLabel(
            self.tr("编辑身份预设") if preset else self.tr("添加身份预设"), self
        )
        self.nameEdit = LineEdit(self)
        self.hostsEdit = TokenLineEdit(self)
        self.hostsHelpButton = TransparentToolButton(FluentIcon.QUESTION, self)
        self.hostsRow = QHBoxLayout()
        self.profileButton = DropDownPushButton(self)
        self.uaEdit = LineEdit(self)

        self._initWidget()
        self._initLayout()
        self._bind()
        self._populate()

    def _initWidget(self) -> None:
        self.widget.setMinimumWidth(480)
        self.yesButton.setText(self.tr("确定"))
        self.cancelButton.setText(self.tr("取消"))
        self.nameEdit.setPlaceholderText(self.tr("预设名称"))
        self.uaEdit.setPlaceholderText(self.tr("留空则跟随 TLS 指纹自动生成"))
        self.uaEdit.setClearButtonEnabled(True)

        from app.view.components.option_cards import buildProfileMenu
        self.profileButton.setMenu(
            buildProfileMenu(self, self._onProfilePick, includeAuto=False))

    def _initLayout(self) -> None:
        self.hostsRow.setContentsMargins(0, 0, 0, 0)
        self.hostsRow.setSpacing(4)
        self.hostsRow.addWidget(BodyLabel(self.tr("匹配 Host"), self))
        self.hostsRow.addWidget(self.hostsHelpButton)
        self.hostsRow.addStretch(1)

        self.viewLayout.setSpacing(8)
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(BodyLabel(self.tr("名称"), self))
        self.viewLayout.addWidget(self.nameEdit)
        self.viewLayout.addLayout(self.hostsRow)
        self.viewLayout.addWidget(self.hostsEdit)
        self.viewLayout.addWidget(BodyLabel(self.tr("TLS 指纹"), self))
        self.viewLayout.addWidget(self.profileButton)
        self.viewLayout.addWidget(BodyLabel(self.tr("User-Agent"), self))
        self.viewLayout.addWidget(self.uaEdit)

    def _bind(self) -> None:
        self.hostsHelpButton.clicked.connect(self._onHostsHelpClicked)

    def _populate(self) -> None:
        self._refreshProfileLabel()
        if self._preset is None:
            return
        self.nameEdit.setText(self._preset.get("name", ""))
        self.hostsEdit.setTokens(self._preset.get("hosts", []))
        self.uaEdit.setText(self._preset.get("userAgent", ""))

    def _onHostsHelpClicked(self) -> None:
        TeachingTip.create(
            self.hostsHelpButton,
            self.tr("Host 匹配规则"),
            self.tr(
                "输入域名后按回车添加，支持两种格式：\n\n"
                "精确匹配: pcs.baidu.com\n"
                "通配符: *.pcs.baidu.com（匹配所有子域名）"
            ),
            tailPosition=TeachingTipTailPosition.BOTTOM,
            isClosable=True,
            duration=-1,
            parent=self,
        )

    def _onProfilePick(self, value: str) -> None:
        self._profileValue = value
        self._refreshProfileLabel()

    def _refreshProfileLabel(self) -> None:
        from app.view.components.option_cards import toProfileLabel
        if self._profileValue:
            self.profileButton.setText(toProfileLabel(self._profileValue))
        else:
            self.profileButton.setText(self.tr("跟随全局默认"))

    def preset(self) -> dict:
        result = {
            "name": self.nameEdit.text().strip() or self.tr("未命名预设"),
            "clientProfile": self._profileValue,
            "userAgent": self.uaEdit.text().strip(),
            "hosts": self.hostsEdit.tokens(),
            "isEnabled": True,
        }
        if self._preset is not None:
            result["isEnabled"] = self._preset.get("isEnabled", True)
        return result
