from __future__ import annotations

from app.config.cfg import BoolValidator, ConfigItem
from app.models.pack import PackConfig


class ArxivConfig(PackConfig):
    isEnabled = ConfigItem("Arxiv", "Enabled", True, BoolValidator())
    shouldDownloadSource = ConfigItem("Arxiv", "DownloadSource", False, BoolValidator())
    shouldDownloadBibtex = ConfigItem("Arxiv", "DownloadBibtex", False, BoolValidator())

    def settingGroups(self, parent: QWidget) -> list[CollapsibleSettingCardGroup]:
        from qfluentwidgets import FluentIcon, SwitchSettingCard
        from app.view.components.setting_card_group import CollapsibleSettingCardGroup

        group = CollapsibleSettingCardGroup(self.tr("arXiv 下载"), "arxiv", parent)
        group.addSettingCards([
            SwitchSettingCard(
                FluentIcon.LINK, self.tr("解析 arXiv 链接"),
                self.tr("将论文页、PDF 链接和论文编号下载为以标题命名的 PDF，关闭后按普通链接下载"),
                self.isEnabled, group,
            ),
            SwitchSettingCard(
                FluentIcon.CODE, self.tr("默认下载 TeX 源码"),
                self.tr("新任务默认勾选源码包，可在添加任务时逐个修改"),
                self.shouldDownloadSource, group,
            ),
            SwitchSettingCard(
                FluentIcon.LIBRARY, self.tr("默认下载 BibTeX"),
                self.tr("新任务默认勾选 .bib 引用文件，可在添加任务时逐个修改"),
                self.shouldDownloadBibtex, group,
            ),
        ])
        return [group]


arxivConfig = ArxivConfig()
