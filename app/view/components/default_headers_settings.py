from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import (
    FluentIcon,
    MessageBoxBase,
    PushButton,
    PushSettingCard,
    SubtitleLabel,
)

from app.supports.config import cfg, factoryHeaders
from app.view.components.editors import AutoSizingEdit, headersFromText, headersToText


class DefaultHeadersDialog(MessageBoxBase):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # instant widget
        self.titleLabel = SubtitleLabel(self.tr("默认请求标头"), self)
        self.headersEdit = AutoSizingEdit(self, minimumVisibleLines=6, maximumVisibleLines=16)
        self.resetButton = PushButton(FluentIcon.SYNC, self.tr("恢复默认"), self)

        # instant layout
        self.titleRowLayout = QHBoxLayout()

        self._initWidget()
        self._initLayout()
        self._bind()

        self.headersEdit.setPlainText(headersToText(cfg.defaultRequestHeaders.value))

    def _initWidget(self) -> None:
        self.widget.setMinimumWidth(560)
        self.yesButton.setText(self.tr("保存"))
        self.cancelButton.setText(self.tr("取消"))
        self.headersEdit.setPlaceholderText(self.tr("每行一个 Name: Value"))

    def _initLayout(self) -> None:
        self.viewLayout.setSpacing(8)
        self.titleRowLayout.addWidget(self.titleLabel)
        self.titleRowLayout.addStretch(1)
        self.titleRowLayout.addWidget(self.resetButton)
        self.viewLayout.addLayout(self.titleRowLayout)
        self.viewLayout.addWidget(self.headersEdit)

    def _bind(self) -> None:
        self.resetButton.clicked.connect(self._reset)

    def _reset(self) -> None:
        self.headersEdit.setPlainText(headersToText(factoryHeaders()))

    def headers(self) -> dict[str, str]:
        return headersFromText(self.headersEdit.toPlainText())


class DefaultHeadersSettingCard(PushSettingCard):
    def __init__(self, parent=None) -> None:
        super().__init__(
            self.tr("编辑"),
            FluentIcon.GLOBE,
            self.tr("默认请求标头"),
            self._summary(),
            parent,
        )
        self._bind()

    def _bind(self) -> None:
        self.clicked.connect(self._onEdit)
        cfg.defaultRequestHeaders.valueChanged.connect(lambda _: self.setContent(self._summary()))

    def _summary(self) -> str:
        return self.tr("已设置 {0} 个标头").format(len(cfg.defaultRequestHeaders.value))

    def _onEdit(self) -> None:
        dialog = DefaultHeadersDialog(self.window())
        if dialog.exec():
            cfg.set(cfg.defaultRequestHeaders, dialog.headers())
        dialog.deleteLater()
