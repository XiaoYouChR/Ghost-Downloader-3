from typing import TYPE_CHECKING, Iterable

from qfluentwidgets import RangeConfigItem, RangeValidator, ConfigItem, BoolValidator, SettingCard, SettingCardGroup, \
    RangeSettingCard, FluentIcon, SwitchSettingCard
from app.bases.models import PackConfig

if TYPE_CHECKING:
    from app.view.pages.setting_page import SettingPage, QWidget

class HttpConfig(PackConfig):
    preBlockNum = RangeConfigItem("Http", "PreBlockNum", 8, RangeValidator(1, 256))
    autoSpeedUp = ConfigItem("Http", "AutoSpeedUp", True, BoolValidator())
    maxReassignSize = RangeConfigItem(
        "Http", "MaxReassignSize", 3, RangeValidator(1, 100)
    )

    def loadSettingCards(self, settingPage: "SettingPage"):
        self.preBlockNumCard = RangeSettingCard(
            self.preBlockNum,
            FluentIcon.CLOUD,
            self.tr("预分配线程数"),
            self.tr(
                "线程越多，下载越快。线程数大于 64 时，有触发反爬导致文件损坏的风险"
            ),
            settingPage.generalDownloadGroup,
        )
        self.autoSpeedUpCard = SwitchSettingCard(
            FluentIcon.SPEED_HIGH,
            self.tr("自动提速"),
            self.tr("AI 实时检测各线程效率并自动增加线程数以提高下载速度"),
            self.autoSpeedUp,
            settingPage.generalDownloadGroup,
        )
        self.maxReassignSizeCard = RangeSettingCard(
            self.maxReassignSize,
            FluentIcon.LIBRARY,
            self.tr("最大重新分配大小 (MB)"),
            self.tr(
                "每线程剩余量大于此值时, 有线程完成或自动提速条件满足会触发重新分配"
            ),
            settingPage.generalDownloadGroup,
        )
        settingPage.generalDownloadGroup.addSettingCard(self.preBlockNumCard)
        settingPage.generalDownloadGroup.addSettingCard(self.autoSpeedUpCard)
        settingPage.generalDownloadGroup.addSettingCard(self.maxReassignSizeCard)

    def getDialogCards(self, parent: "QWidget") -> Iterable["SettingCard"]:
        # TODO 还得将 SettingHeaderCardWidget 中的控件 Base 化以获取统一的 Payload
        preBlockNumCard = RangeSettingCard(
            self.preBlockNum,
            FluentIcon.CLOUD,
            self.tr("预分配线程数"),
            self.tr(
                "线程越多，下载越快。线程数大于 64 时，有触发反爬导致文件损坏的风险"
            ),
            parent,
        )
        return [preBlockNumCard]

httpConfig = HttpConfig()
