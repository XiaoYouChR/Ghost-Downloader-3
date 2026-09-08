from __future__ import annotations

from app.config.cfg import BoolValidator, ConfigItem, OptionsConfigItem, OptionsValidator
from app.models.pack import PackConfig

QUALITY_VALUES = [16, 32, 64, 80, 112, 116, 120, 125, 126, 127, 128]
QUALITY_LABELS = [
    "240P", "360P", "480P", "720P", "720P60", "1080P",
    "1080P+", "1080P60", "4K", "HDR", "杜比视界",
]


class BilibiliConfig(PackConfig):
    userCookie = ConfigItem("Bilibili", "UserCookie", "")
    defaultQuality = OptionsConfigItem(
        "Bilibili", "DefaultQuality", 80, OptionsValidator(QUALITY_VALUES),
    )
    alternativeQuality = OptionsConfigItem(
        "Bilibili", "AlternativeQuality", "max", OptionsValidator(["max", "min"]),
    )
    shouldIncludeHdr = ConfigItem("Bilibili", "ParseHDR", False, BoolValidator())
    shouldIncludeDolby = ConfigItem("Bilibili", "ParseDolby", False, BoolValidator())

    def settingGroups(self, parent):
        from qfluentwidgets import ComboBoxSettingCard, FluentIcon, SwitchSettingCard
        from app.view.components.setting_card_group import CollapsibleSettingCardGroup
        from .setting_cards import BilibiliLoginSettingCard

        group = CollapsibleSettingCardGroup(self.tr("Bilibili 下载"), "bilibili", parent)
        group.addSettingCards([
            BilibiliLoginSettingCard(self._account, group),
            ComboBoxSettingCard(self.defaultQuality, FluentIcon.VIDEO, self.tr("默认画质"),
                                self.tr("选择偏好的视频画质"),
                                texts=QUALITY_LABELS, parent=group),
            ComboBoxSettingCard(self.alternativeQuality, FluentIcon.SPEED_HIGH, self.tr("画质不可用时"),
                                self.tr("当选择的画质不可用时的替代策略"),
                                texts=[self.tr("选择最高画质"), self.tr("选择最低画质")],
                                parent=group),
            SwitchSettingCard(FluentIcon.PALETTE, self.tr("HDR"),
                              self.tr("请求 HDR 视频流（需要大会员）"),
                              self.shouldIncludeHdr, group),
            SwitchSettingCard(FluentIcon.HEADPHONE, self.tr("杜比全景声/视界"),
                              self.tr("请求杜比全景声和杜比视界（需要大会员）"),
                              self.shouldIncludeDolby, group),
        ])
        return [group]


bilibiliConfig = BilibiliConfig()
