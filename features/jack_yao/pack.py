from __future__ import annotations

import json
from base64 import b64decode
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    IconWidget,
    IndeterminateProgressRing,
    MessageBoxBase,
    OptionsConfigItem,
    OptionsValidator,
    ComboBoxSettingCard,
    PrimaryPushButton,
    PushButton,
    PixmapLabel,
    SettingCardGroup,
    SimpleCardWidget,
    TitleLabel,
    ToolTipFilter,
    TransparentToolButton,
)

from app.client import buildClient
from app.config.cfg import cfg
from app.models.pack import FeaturePack, PackPage

from app.view.components.scroll_area import ScrollArea

CATALOG_API = "https://xineko-my.sharepoint.com/personal/os_store_xineko_onmicrosoft_com/_layouts/52/download.aspx?share=IQCK7kKU1-8oSqWDNNPss2xeAbmG3v4cItTXNqW2NG9Hzwc"
CONTENT_MARGIN = 16


async def fetchCatalog() -> list[dict]:
    client = buildClient()
    try:
        response = await client.get(CATALOG_API)
        response.raise_for_status()
        return json.loads(await response.text())["OS"]
    finally:
        client.close()


class CatalogPage(PackPage, ScrollArea):
    icon = FluentIcon.CLOUD_DOWNLOAD
    title = QCoreApplication.translate("CatalogPage", "资源下载")

    def __init__(self, pack, parent=None):
        super().__init__(parent)
        self._pack = pack
        self.setObjectName("CatalogPage")
        self._cards: list[CatalogCard] = []

        self._scrollWidget = QWidget()
        self._layout = QVBoxLayout(self._scrollWidget)
        self._loadingWidget = LoadingWidget(self._scrollWidget)

        self._initWidget()
        self._initLayout()
        self._bind()
        self._loadCatalog()

    def _initWidget(self):
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def _initLayout(self):
        self._layout.setSpacing(8)
        self._layout.setContentsMargins(CONTENT_MARGIN, CONTENT_MARGIN, CONTENT_MARGIN, CONTENT_MARGIN)
        self._layout.addWidget(self._loadingWidget, 1, Qt.AlignmentFlag.AlignCenter)

        self.setWidget(self._scrollWidget)
        self.setWidgetResizable(True)
        self.enableTransparentBackground()

    def _bind(self):
        self._loadingWidget.retryRequested.connect(self._loadCatalog)

    def _loadCatalog(self):
        self._loadingWidget.setLoading()
        self._pack.submit(
            fetchCatalog(),
            done=self._onCatalogLoaded, failed=self._onCatalogFailed,
            owner=self,
        )

    def _onCatalogLoaded(self, items: list[dict]):
        for card in self._cards:
            self._layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        self._layout.removeWidget(self._loadingWidget)
        self._loadingWidget.setParent(None)
        self._loadingWidget.deleteLater()

        for item in items:
            card = CatalogCard(item, self._scrollWidget)
            card.downloadRequested.connect(self._onDownloadRequested)
            self._layout.addWidget(card)
            self._cards.append(card)

        self._layout.addStretch(1)

    def _onCatalogFailed(self, error: str):
        self._loadingWidget.setError(self.tr("加载失败，请检查网络后重试\n") + str(error))

    def _onDownloadRequested(self, items: list[dict]):
        CatalogDownloadDialog(self._pack, self.window(), items).exec()


class LoadingWidget(QWidget):
    retryRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ring = IndeterminateProgressRing(self)
        self._ring.setFixedSize(48, 48)
        self._label = CaptionLabel(self.tr("正在加载..."), self)
        self._errorIcon = IconWidget(FluentIcon.CANCEL, self)
        self._errorIcon.setFixedSize(48, 48)
        self._errorIcon.hide()
        self._retryButton = PushButton(self.tr("重试"), self)
        self._retryButton.hide()

        self._label.setTextColor(QColor(96, 96, 96), QColor(206, 206, 206))
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)

        self._retryButton.clicked.connect(self.retryRequested)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._ring, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._errorIcon, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._retryButton, 0, Qt.AlignmentFlag.AlignHCenter)

    def setLoading(self):
        self._ring.show()
        self._errorIcon.hide()
        self._label.setText(self.tr("正在加载..."))
        self._retryButton.hide()
        self.show()

    def setError(self, text: str):
        self._ring.hide()
        self._errorIcon.show()
        self._label.setText(text)
        self._retryButton.show()


class CatalogCard(SimpleCardWidget):
    downloadRequested = Signal(list)

    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self._catalogItems: list[dict] = item["List"]
        self._videoUrl: str = item["Video"]
        self.setFixedHeight(91)

        self._logoLabel = PixmapLabel(self)
        self._logoLabel.setFixedSize(71, 71)
        self._logoLabel.setScaledContents(True)
        pixmap = QPixmap()
        pixmap.loadFromData(b64decode(item["Icon"]))
        self._logoLabel.setPixmap(pixmap)
        self._logoLabel.setFixedSize(71, 71)

        self._titleLabel = TitleLabel(item["Name"], self)
        self._bodyLabel = BodyLabel(item["Intro"].replace(r"\n", "\n"), self)
        self._bodyLabel.setMaximumHeight(61)
        self._bodyLabel.setWordWrap(True)

        self._downloadButton = PrimaryPushButton(FluentIcon.DOWNLOAD, self.tr("下载"), self)
        self._downloadButton.setFixedWidth(100)
        self._videoButton = TransparentToolButton(FluentIcon.VIDEO, self)
        self._videoButton.installEventFilter(ToolTipFilter(self._videoButton))
        self._videoButton.setToolTip(self.tr("观看视频"))
        self._videoButton.setEnabled(bool(self._videoUrl))

        self._initLayout()
        self._bind()

    def _initLayout(self):
        textLayout = QVBoxLayout()
        textLayout.setSpacing(0)
        textLayout.addWidget(self._titleLabel)
        textLayout.addWidget(self._bodyLabel)

        mainLayout = QHBoxLayout(self)
        mainLayout.setSpacing(12)
        mainLayout.addWidget(self._logoLabel)
        mainLayout.addLayout(textLayout, 1)
        mainLayout.addWidget(self._downloadButton)
        mainLayout.addWidget(self._videoButton)

    def _bind(self):
        self._downloadButton.clicked.connect(self._onDownloadClicked)
        self._videoButton.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self._videoUrl)))

    def _onDownloadClicked(self):
        self.downloadRequested.emit(self._catalogItems)


class CatalogDownloadDialog(MessageBoxBase):
    def __init__(self, pack, parent=None, catalogItems: list[dict] | None = None):
        self._pack = pack
        from app.view.components.card_groups import OptionCardGroup
        from app.view.components.editors import AutoSizingEdit
        from app.view.components.option_cards import OutputFolderCard, SubworkerCountCard

        super().__init__(parent)
        self._items = catalogItems or []

        versions = [item["Version"] for item in self._items]
        versionItem = OptionsConfigItem("Material", "Version", versions[0], OptionsValidator(versions))

        self._versionGroup = SettingCardGroup(self.tr("选择版本"), self)
        self._versionCard = ComboBoxSettingCard(
            versionItem, FluentIcon.VIEW, self.tr("选择版本"), self.tr("选择你想下载的版本"),
            texts=versions, parent=self._versionGroup,
        )
        self._versionGroup.addSettingCard(self._versionCard)

        self._logGroup = SettingCardGroup(self.tr("更新日志"), self)
        self._logEdit = AutoSizingEdit(self._logGroup, minimumVisibleLines=3, maximumVisibleLines=8)
        self._logEdit.setReadOnly(True)
        self._logEdit.setPlainText(self._items[0]["Log"] if self._items else "")
        self._logGroup.addSettingCard(self._logEdit)

        self._optionGroup = OptionCardGroup(self)
        self._optionGroup.addCard(OutputFolderCard(self._optionGroup))
        self._optionGroup.addCard(SubworkerCountCard(self._optionGroup))

        self.yesButton.setText(self.tr("开始下载"))
        self.cancelButton.setText(self.tr("取消"))

        self.viewLayout.addWidget(self._versionGroup)
        self.viewLayout.addWidget(self._logGroup)
        self.viewLayout.addWidget(self._optionGroup)

        self.widget.setFixedWidth(700)

        self._versionCard.comboBox.currentIndexChanged.connect(
            lambda i: self._logEdit.setPlainText(self._items[i]["Log"] if i < len(self._items) else "")
        )
        self.yesButton.clicked.disconnect()
        self.yesButton.clicked.connect(self._onStartClicked)

    def _onStartClicked(self):
        from qfluentwidgets import InfoBar, InfoBarPosition
        from app.models.task import ResourceTaskOptions

        index = self._versionCard.comboBox.currentIndex()
        item = self._items[index]
        options = self._optionGroup.options()
        window = self.window()
        failedTitle = self.tr("下载失败")

        def onParsed(task):
            for step in task.steps:
                step.setOptions(options)
            self._pack.addTask(task)

        def onFailed(error):
            InfoBar.error(failedTitle, str(error), duration=-1,
                          position=InfoBarPosition.BOTTOM_RIGHT, parent=window)

        self._pack.submit(
            self._pack.parse(ResourceTaskOptions(
                url=item["Url"],
                outputFolder=options.get("outputFolder", Path(cfg.downloadFolder.value)),
            )),
            done=onParsed,
            failed=onFailed,
            owner=window,
        )
        self.accept()


class JackYaoPack(FeaturePack):
    packId = "jack_yao"

    def pages(self):
        return [CatalogPage]
