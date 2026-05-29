from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    FluentIcon,
    InfoBar,
    LineEdit,
    MessageBoxBase,
    TransparentToolButton, SubtitleLabel, PrimaryPushButton,
)

from app.view.components.editors import AutoSizingEdit
from .schema import DEFAULT_WEB_TRACKER_SOURCE
from .service import webTrackerService
from ..trackers import parseTrackerText, toTrackers


class WebTrackerSourceCard(QWidget):
    removed = Signal(object)

    def __init__(self, url: str = "", cachedCount: int | None = None, parent=None):
        super().__init__(parent)
        # instant widget
        self.urlEdit = LineEdit(self)
        self.statusLabel = BodyLabel(self)
        self.deleteButton = TransparentToolButton(FluentIcon.CLOSE, self)
        # instant layout
        self.hBoxLayout = QHBoxLayout(self)

        self._initWidget(url, cachedCount)
        self._initLayout()
        self._bind()

    def url(self) -> str:
        return toTrackers(self.urlEdit.text())

    def setCachedCount(self, count: int | None) -> None:
        if count is None:
            self.statusLabel.setText(self.tr("未拉取"))
        else:
            self.statusLabel.setText(self.tr("{0} 条").format(count))

    def _initWidget(self, url: str, cachedCount: int | None) -> None:
        self.urlEdit.setText(url)
        self.urlEdit.setPlaceholderText(DEFAULT_WEB_TRACKER_SOURCE)
        self.setCachedCount(cachedCount)

    def _initLayout(self) -> None:
        self.hBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.hBoxLayout.setSpacing(8)
        self.hBoxLayout.addWidget(self.urlEdit, 1)
        self.hBoxLayout.addWidget(self.statusLabel)
        self.hBoxLayout.addWidget(self.deleteButton)

    def _bind(self) -> None:
        self.urlEdit.editingFinished.connect(self._onUrlEditingFinished)
        self.deleteButton.clicked.connect(self._onDeleteClicked)

    def _onUrlEditingFinished(self) -> None:
        normalized = self.url()
        self.setCachedCount(webTrackerService.cachedCount(normalized) if normalized else None)

    def _onDeleteClicked(self) -> None:
        self.removed.emit(self)


class WebTrackerDialog(MessageBoxBase):

    def __init__(self, parent=None):
        super().__init__(parent)
        # instant widget
        self.sourceHeaderLabel = SubtitleLabel(self.tr("Tracker 源"), self.widget)
        self.addSourceButton = PrimaryPushButton(FluentIcon.ADD, "添加", self.widget)
        self.sourceContainer = QWidget(self.widget)
        self.customLabel = SubtitleLabel(self.tr("自定义 Tracker"), self.widget)
        self.customEdit = AutoSizingEdit(self.widget)
        # instant layout
        self.sourceHeaderLayout = QHBoxLayout()
        self.sourceLayout = QVBoxLayout(self.sourceContainer)
        self._sourceRows: list[WebTrackerSourceCard] = []

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.widget.setMinimumWidth(720)
        self.yesButton.setText(self.tr("保存并刷新"))
        self.cancelButton.setText(self.tr("取消"))
        self.customEdit.setPlaceholderText("每行一个 tracker URL,不会被源刷新覆盖")
        self.customEdit.setPlainText("\n".join(webTrackerService.customTrackers()))
        for url in webTrackerService.sourceUrls():
            self._addSourceRow(url)

    def _initLayout(self) -> None:
        self.sourceHeaderLayout.setContentsMargins(0, 0, 0, 0)
        self.sourceHeaderLayout.addWidget(self.sourceHeaderLabel)
        self.sourceHeaderLayout.addStretch(1)
        self.sourceHeaderLayout.addWidget(self.addSourceButton)

        self.sourceLayout.setContentsMargins(0, 0, 0, 0)
        self.sourceLayout.setSpacing(8)

        self.viewLayout.addLayout(self.sourceHeaderLayout)
        self.viewLayout.addWidget(self.sourceContainer)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.customLabel)
        self.viewLayout.addWidget(self.customEdit)

    def _bind(self) -> None:
        self.addSourceButton.clicked.connect(self._onAddSourceClicked)

    def validate(self) -> bool:
        urls: list[str] = []
        for row in self._sourceRows:
            normalized = row.url()
            if not normalized:
                InfoBar.error(
                    self.tr("源地址无效"),
                    self.tr("请输入有效的 HTTP/HTTPS 地址"),
                    parent=self,
                )
                row.urlEdit.setFocus()
                return False
            urls.append(normalized)

        uniqueUrls = list(dict.fromkeys(urls))
        webTrackerService.setSourceUrls(uniqueUrls)
        webTrackerService.setCustomTrackers(parseTrackerText(self.customEdit.toPlainText()))
        return True

    def _addSourceRow(self, url: str = "") -> None:
        cachedCount = webTrackerService.cachedCount(url) if url else None
        row = WebTrackerSourceCard(url, cachedCount, self.sourceContainer)
        row.removed.connect(self._onSourceRemoved)
        self.sourceLayout.addWidget(row)
        self._sourceRows.append(row)

    def _onAddSourceClicked(self) -> None:
        self._addSourceRow()

    def _onSourceRemoved(self, row: WebTrackerSourceCard) -> None:
        self._sourceRows.remove(row)
        self.sourceLayout.removeWidget(row)
        row.deleteLater()
