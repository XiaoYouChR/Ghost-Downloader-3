from __future__ import annotations

from uuid import uuid4

from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import BodyLabel, ComboBox, LineEdit, MessageBoxBase, SpinBox, SubtitleLabel, SwitchButton

from app.site_rules import normalizeHost
from app.view.components.token_line_edit import TokenLineEdit


ACTION_ITEMS = [
    ("standard", "标准下载"),
    ("single_connection", "限制连接数"),
    ("pixeldrain_api", "PixelDrain — 使用 API"),
    ("uupdump_post", "UUP dump — 提交表单"),
    ("prefer_latest_hls", "HLS — 优先选择最新媒体"),
]


class SiteRuleEditDialog(MessageBoxBase):
    def __init__(self, parent=None, *, rule: dict | None = None):
        super().__init__(parent)
        self._rule = dict(rule) if rule else None
        self.titleLabel = SubtitleLabel(self.tr("编辑规则") if rule else self.tr("添加规则"), self)
        self.nameEdit = LineEdit(self)
        self.hostsEdit = TokenLineEdit(self)
        self.actionCombo = ComboBox(self)
        self.connectionsSpin = SpinBox(self)
        self.enabledRow = QWidget(self)
        self.enabledLayout = QHBoxLayout(self.enabledRow)
        self.enabledSwitch = SwitchButton(self.enabledRow)

        self._initWidget()
        self._initLayout()
        self._populate()

    def _initWidget(self) -> None:
        self.widget.setMinimumWidth(540)
        self.yesButton.setText(self.tr("保存"))
        self.cancelButton.setText(self.tr("取消"))
        self.nameEdit.setPlaceholderText(self.tr("规则名称"))
        self.hostsEdit.setPlaceholderText(self.tr("输入域名并按 Enter"))
        self.connectionsSpin.setRange(1, 256)
        for value, text in ACTION_ITEMS:
            self.actionCombo.addItem(self.tr(text), userData=value)

    def _initLayout(self) -> None:
        self.enabledLayout.setContentsMargins(0, 0, 0, 0)
        self.enabledLayout.addWidget(BodyLabel(self.tr("启用规则"), self.enabledRow))
        self.enabledLayout.addStretch(1)
        self.enabledLayout.addWidget(self.enabledSwitch)

        self.viewLayout.setSpacing(8)
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(BodyLabel(self.tr("名称"), self))
        self.viewLayout.addWidget(self.nameEdit)
        self.viewLayout.addWidget(BodyLabel(self.tr("域名"), self))
        self.viewLayout.addWidget(self.hostsEdit)
        self.viewLayout.addWidget(BodyLabel(self.tr("行为"), self))
        self.viewLayout.addWidget(self.actionCombo)
        self.viewLayout.addWidget(BodyLabel(self.tr("最大连接数"), self))
        self.viewLayout.addWidget(self.connectionsSpin)
        self.viewLayout.addWidget(self.enabledRow)

    def _populate(self) -> None:
        rule = self._rule
        if rule is None:
            self.connectionsSpin.setValue(1)
            self.enabledSwitch.setChecked(True)
            return
        self.nameEdit.setText(str(rule.get("name", "")))
        self.hostsEdit.setTokens(list(rule.get("hosts") or []))
        self.connectionsSpin.setValue(int(rule.get("connections", 1)))
        self.enabledSwitch.setChecked(bool(rule.get("enabled", True)))
        index = self.actionCombo.findData(rule.get("action", "standard"))
        self.actionCombo.setCurrentIndex(max(index, 0))

    def validate(self) -> bool:
        return bool(self.nameEdit.text().strip() and self._hosts())

    def _hosts(self) -> list[str]:
        result: list[str] = []
        for token in self.hostsEdit.tokens():
            host = normalizeHost(token)
            if host and host not in result:
                result.append(host)
        return result

    def rule(self) -> dict:
        old = self._rule or {}
        return {
            "id": old.get("id") or f"custom_{uuid4().hex}",
            "name": self.nameEdit.text().strip(),
            "hosts": self._hosts(),
            "action": self.actionCombo.currentData() or "standard",
            "enabled": self.enabledSwitch.isChecked(),
            "connections": self.connectionsSpin.value(),
            "description": old.get("description", "Custom site rule."),
        }
