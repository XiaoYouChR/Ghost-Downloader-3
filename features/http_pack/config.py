from typing import TYPE_CHECKING, Iterable, Any

from PySide6.QtCore import Qt
from qfluentwidgets import RangeConfigItem, RangeValidator, ConfigItem, BoolValidator, RangeSettingCard, FluentIcon, \
    SwitchSettingCard, Slider, BodyLabel

from app.bases.models import PackConfig
from app.view.components.card_widgets import ParseSettingCard

if TYPE_CHECKING:
    from app.view.pages.setting_page import SettingPage, QWidget


class PreBlockNumCard(ParseSettingCard):
    def initCustomWidget(self):
        self.slider = Slider(Qt.Orientation.Horizontal, self)
        self.valueLabel = BodyLabel(self)
        self.slider.setMinimumWidth(268)

        self.slider.setSingleStep(1)
        self.slider.setRange(*httpConfig.preBlockNum.range)
        self.slider.setValue(httpConfig.preBlockNum.value)
        self.valueLabel.setNum(httpConfig.preBlockNum.value)

        self.hBoxLayout.addWidget(self.valueLabel)
        self.hBoxLayout.addSpacing(6)
        self.hBoxLayout.addWidget(self.slider)
        self.hBoxLayout.addSpacing(16)

        self.slider.valueChanged.connect(self._onValueChanged)

    def _onValueChanged(self, value: int):
        self.valueLabel.setNum(value)
        self.valueLabel.adjustSize()
        self.slider.setValue(value)
        self.payloadChanged.emit()

    @property
    def payload(self) -> dict[str, Any]:
        return {
            "preBlockNum": self.slider.value(),
        }

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

    def getDialogCards(self, parent: "QWidget") -> Iterable["ParseSettingCard"]:
        preBlockNumCard = PreBlockNumCard(FluentIcon.CLOUD, self.tr("预分配线程数"), parent)
        return [preBlockNumCard]

httpConfig = HttpConfig()
