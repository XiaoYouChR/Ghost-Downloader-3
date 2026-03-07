from qfluentwidgets import MessageBoxBase, SubtitleLabel, PlainTextEdit, ConfigValidator, OptionsConfigItem, \
    OptionsValidator, BoolValidator, ConfigItem, SettingCardGroup, ComboBoxSettingCard, FluentIcon, SwitchSettingCard, \
    PushSettingCard

from app.bases.models import PackConfig
from app.supports.config import cfg


class EditCookieDialog(MessageBoxBase):
    def __init__(self, parent=None, initialCookie=None):
        super().__init__(parent=parent)
        self.setClosableOnMaskClicked(True)

        self.widget.setFixedSize(400, 500)

        self.titleLabel = SubtitleLabel(self.tr("编辑 Cookie"), self.widget)
        self.viewLayout.addWidget(self.titleLabel)

        self.cookieTextEdit = PlainTextEdit(self.widget)
        self.cookieTextEdit.setPlaceholderText(self.tr('请在此输入用户 Cookie.'))
        self.cookieTextEdit.setPlainText(initialCookie)
        self.viewLayout.addWidget(self.cookieTextEdit)


class CookieValidator(ConfigValidator):
    def validate(self, value) -> bool:
        if type(value) == str:
            return True
        return False

    def correct(self, value) -> str:
        return value if self.validate(value) else ""


class BilibiliConfig(PackConfig):
    defaultQuality = OptionsConfigItem("Download", "DefaultQuality", 16,
                                       OptionsValidator([127, 120, 116, 112, 80, 74, 64, 32, 16]))
    alternativeQuality = OptionsConfigItem("Download", "AlternativeQuality", "max", OptionsValidator(["max", "min"]))
    parseHDR = ConfigItem("Download", "ParseHDR", False, BoolValidator())
    parseDolby = ConfigItem("Download", "ParseDolby", False, BoolValidator())
    userCookie = ConfigItem("Download", "UserCookie", "", CookieValidator())

    def loadSettingCards(self, settingPage: "SettingPage"):
        self.parseBilibiliGroup = SettingCardGroup("哔哩哔哩视频下载", settingPage.container)

        self.defaultQualityCard = ComboBoxSettingCard(
            self.defaultQuality,
            FluentIcon.VIDEO,
            "默认清晰度",
            "下载视频时默认的清晰度",
            ["8K", "4K", "1080P60", "1080P+", "1080P", "720P60", "720P", "480P", "360P"],
            self.parseBilibiliGroup
        )

        self.alternativeQualityCard = ComboBoxSettingCard(
            self.alternativeQuality,
            FluentIcon.VIDEO,
            "备选清晰度",
            "下载视频时备选的清晰度",
            ["可以下载的最高画质", "可以下载的最低画质"],
            self.parseBilibiliGroup
        )

        self.parseHDRCard = SwitchSettingCard(
            FluentIcon.VIDEO,
            "HDR",
            "下载 HDR 视频",
            self.parseHDR,
            self.parseBilibiliGroup
        )

        self.parseDolbyCard = SwitchSettingCard(
            FluentIcon.VIDEO,
            "杜比视界",
            "下载杜比视界视频",
            self.parseDolby,
            self.parseBilibiliGroup
        )

        self.userCookieCard = PushSettingCard(
            "设置用户 Cookie",
            FluentIcon.BROOM,
            "用户 Cookie",
            "用于下载高清视频时获取下载链接",
            self.parseBilibiliGroup
        )
        self.userCookieCard.clicked.connect(self._onUserCookieCardClicked)

        self.parseBilibiliGroup.addSettingCard(self.defaultQualityCard)
        self.parseBilibiliGroup.addSettingCard(self.alternativeQualityCard)
        self.parseBilibiliGroup.addSettingCard(self.parseHDRCard)
        self.parseBilibiliGroup.addSettingCard(self.parseDolbyCard)
        self.parseBilibiliGroup.addSettingCard(self.userCookieCard)

        settingPage.vBoxLayout.addWidget(self.parseBilibiliGroup)

    def _onUserCookieCardClicked(self):
        dialog = EditCookieDialog(self.parseBilibiliGroup.window(), self.userCookie.value)
        if dialog.exec():
            cookie = dialog.cookieTextEdit.toPlainText()
            cfg.set(self.userCookie, cookie)
            dialog.deleteLater()

bilibiliConfig = BilibiliConfig()
