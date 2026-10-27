from __future__ import annotations

from app.config.cfg import ConfigItem, OptionsConfigItem, OptionsValidator
from app.models.pack import PackConfig

QUALITY_VALUES = [16, 32, 64, 74, 80, 112, 116, 120, 125, 126, 127]
QUALITY_LABELS = [
    "360P", "480P", "720P", "720P60", "1080P", "1080P+",
    "1080P60", "4K", "HDR", "杜比视界", "8K",
]
AUDIO_QUALITY_VALUES = [30216, 30232, 30280, 30250, 30251]
AUDIO_QUALITY_LABELS = ["64K", "132K", "192K", "杜比全景声", "Hi-Res"]


class BilibiliConfig(PackConfig):
    userCookie = ConfigItem("Bilibili", "UserCookie", "")
    defaultQuality = OptionsConfigItem(
        "Bilibili", "DefaultQuality", 80, OptionsValidator(QUALITY_VALUES),
    )
    defaultAudioQuality = OptionsConfigItem(
        "Bilibili", "DefaultAudioQuality", 30280, OptionsValidator(AUDIO_QUALITY_VALUES),
    )
    alternativeQuality = OptionsConfigItem(
        "Bilibili", "AlternativeQuality", "max", OptionsValidator(["max", "min"]),
    )

    def settingGroups(self, parent):
        from qfluentwidgets import ComboBoxSettingCard, FluentIcon
        from app.view.components.setting_card_group import CollapsibleSettingCardGroup
        from .setting_cards import BilibiliLoginSettingCard

        group = CollapsibleSettingCardGroup(self.tr("Bilibili 下载"), "bilibili", parent)
        group.addSettingCards([
            BilibiliLoginSettingCard(self._account, group),
            ComboBoxSettingCard(self.defaultQuality, FluentIcon.VIDEO, self.tr("默认画质"),
                                self.tr("选择偏好的视频画质"),
                                texts=QUALITY_LABELS, parent=group),
            ComboBoxSettingCard(self.defaultAudioQuality, FluentIcon.MUSIC, self.tr("默认音质"),
                                self.tr("选择偏好的音质"),
                                texts=AUDIO_QUALITY_LABELS, parent=group),
            ComboBoxSettingCard(self.alternativeQuality, FluentIcon.SPEED_HIGH, self.tr("画质或音质不可用时"),
                                self.tr("当选择的画质或音质不可用时的替代策略"),
                                texts=[self.tr("选择最高"), self.tr("选择最低")],
                                parent=group),
        ])
        return [group]


bilibiliConfig = BilibiliConfig()
