from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel, FluentIcon, IconWidget, InfoBar, InfoBarPosition,
    PushButton, StrongBodyLabel, SubtitleLabel, SwitchButton,
    ToolButton, ToolTipFilter,
)

from app.config.cfg import cfg
from app.site_rules import defaultSiteRules
from app.view.components.scroll_area import ScrollArea
from app.view.components.setting_card_group import CollapsibleSettingCard


ACTION_LABELS = {
    "standard": "标准下载",
    "single_connection": "限制连接数",
    "pixeldrain_api": "API PixelDrain",
    "uupdump_post": "UUP dump 表单",
    "prefer_latest_hls": "最新 HLS",
}


def _tr(text: str) -> str:
    return QCoreApplication.translate("SiteRulesPage", text)


class SiteRuleRow(QWidget):
    def __init__(self, rule: dict, onToggle, onEdit, onRemove, parent=None):
        super().__init__(parent)
        self.icon = IconWidget(FluentIcon.GLOBE, self)
        self.name = StrongBodyLabel(str(rule.get("name", "")), self)
        hosts = ", ".join(rule.get("hosts") or [])
        action = _tr(ACTION_LABELS.get(rule.get("action"), str(rule.get("action", ""))))
        self.summary = BodyLabel(f"{hosts}  •  {action}", self)
        self.enabled = SwitchButton(self)
        self.edit = ToolButton(FluentIcon.EDIT, self)
        self.remove = ToolButton(FluentIcon.DELETE, self)

        self.icon.setFixedSize(18, 18)
        self.enabled.setChecked(bool(rule.get("enabled", True)))
        self.edit.setToolTip(_tr("编辑"))
        self.remove.setToolTip(_tr("删除"))
        self.edit.installEventFilter(ToolTipFilter(self.edit))
        self.remove.installEventFilter(ToolTipFilter(self.remove))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(48, 10, 24, 10)
        layout.setSpacing(12)
        layout.addWidget(self.icon)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self.name)
        text.addWidget(self.summary)
        layout.addLayout(text, 1)
        layout.addWidget(self.enabled)
        layout.addWidget(self.edit)
        layout.addWidget(self.remove)

        ruleId = str(rule.get("id", ""))
        self.enabled.checkedChanged.connect(lambda checked: onToggle(ruleId, checked))
        self.edit.clicked.connect(lambda: onEdit(ruleId))
        self.remove.clicked.connect(lambda: onRemove(ruleId))


class SiteRulesPage(ScrollArea):
    def __init__(self, browserService, parent=None):
        super().__init__(parent)
        self._browserService = browserService
        self._rows: list[SiteRuleRow] = []
        self.container = QWidget(self)
        self.layout = QVBoxLayout(self.container)
        self.title = SubtitleLabel(self.tr("站点规则"), self.container)
        self.description = BodyLabel(
            self.tr("按域名自动调整连接数、下载地址和媒体选择。"),
            self.container,
        )
        self.rulesCard = CollapsibleSettingCard(
            FluentIcon.DEVELOPER_TOOLS,
            self.tr("智能规则"),
            self.tr("更改将应用到 Ghost Downloader 和已连接的浏览器扩展。"),
            self.container,
        )
        self.buttonRow = QWidget(self.rulesCard.view)
        self.buttonLayout = QHBoxLayout(self.buttonRow)
        self.resetButton = PushButton(FluentIcon.SYNC, self.tr("恢复默认值"), self.buttonRow)
        self.addButton = PushButton(FluentIcon.ADD, self.tr("添加规则"), self.buttonRow)

        self._initWidget()
        self._initLayout()
        self._bind()
        self._reload()

    def _initWidget(self) -> None:
        self.setWidget(self.container)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.enableTransparentBackground()
        self.setProperty("isStackedTransparent", False)

    def _initLayout(self) -> None:
        self.layout.setContentsMargins(36, 28, 36, 36)
        self.layout.setSpacing(8)
        self.layout.addWidget(self.title)
        self.layout.addWidget(self.description)
        self.layout.addSpacing(12)
        self.layout.addWidget(self.rulesCard)
        self.layout.addStretch(1)
        self.rulesCard.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.rulesCard.viewLayout.setSpacing(0)
        self.buttonLayout.setContentsMargins(48, 10, 24, 10)
        self.buttonLayout.addStretch(1)
        self.buttonLayout.addWidget(self.resetButton)
        self.buttonLayout.addWidget(self.addButton)

    def _bind(self) -> None:
        self.addButton.clicked.connect(self._add)
        self.resetButton.clicked.connect(self._reset)

    def _rules(self) -> list[dict]:
        return [dict(rule) for rule in cfg.siteRules.value]

    def _save(self, rules: list[dict]) -> None:
        cfg.set(cfg.siteRules, rules)
        self._browserService.broadcastSiteRules()
        self._reload()

    def _reload(self) -> None:
        for row in self._rows:
            self.rulesCard.viewLayout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()
        self.rulesCard.viewLayout.removeWidget(self.buttonRow)
        for rule in self._rules():
            row = SiteRuleRow(rule, self._toggle, self._edit, self._remove, self.rulesCard.view)
            self.rulesCard.viewLayout.addWidget(row)
            self._rows.append(row)
        self.rulesCard.viewLayout.addWidget(self.buttonRow)
        self.rulesCard.card.setContent(self.tr("已配置 {count} 条规则").format(count=len(self._rows)))

    def _toggle(self, ruleId: str, enabled: bool) -> None:
        rules = self._rules()
        for rule in rules:
            if rule.get("id") == ruleId:
                rule["enabled"] = enabled
        cfg.set(cfg.siteRules, rules)
        self._browserService.broadcastSiteRules()

    def _add(self) -> None:
        from app.view.dialogs.site_rule_edit import SiteRuleEditDialog
        dialog = SiteRuleEditDialog(self.window())
        if dialog.exec():
            self._save([*self._rules(), dialog.rule()])

    def _edit(self, ruleId: str) -> None:
        rules = self._rules()
        current = next((rule for rule in rules if rule.get("id") == ruleId), None)
        if current is None:
            return
        from app.view.dialogs.site_rule_edit import SiteRuleEditDialog
        dialog = SiteRuleEditDialog(self.window(), rule=current)
        if dialog.exec():
            self._save([dialog.rule() if rule.get("id") == ruleId else rule for rule in rules])

    def _remove(self, ruleId: str) -> None:
        self._save([rule for rule in self._rules() if rule.get("id") != ruleId])

    def _reset(self) -> None:
        self._save(defaultSiteRules())
        InfoBar.success(
            title=self.tr("规则已恢复"),
            content=self.tr("已恢复 PixelDrain、UUP dump 和 HDSex 默认规则。"),
            position=InfoBarPosition.TOP_RIGHT,
            parent=self.window(),
        )
