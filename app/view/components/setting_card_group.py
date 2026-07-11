from __future__ import annotations

from PySide6.QtCore import (
    QByteArray, QEasingCurve, QEvent, QObject,
    QPropertyAnimation, QSize, Qt, Signal,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    CardWidget, FluentIcon, FluentIconBase, FluentStyleSheet, SettingCard,
    StrongBodyLabel, TransparentToolButton, isDarkTheme,
)
from qfluentwidgets.components.settings.expand_setting_card import (
    ExpandBorderWidget, ExpandSettingCard, GroupSeparator,
)

from app.config.cfg import cfg

QWIDGETSIZE_MAX = (1 << 24) - 1


class LabelElideFilter(QObject):
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.Paint or not isinstance(obj, QLabel):
            return False
        metrics = obj.fontMetrics()
        rect = obj.contentsRect()
        text = "\n".join(
            metrics.elidedText(line, Qt.TextElideMode.ElideRight, rect.width())
            for line in obj.text().splitlines() or [""]
        )
        with QPainter(obj) as painter:
            painter.setFont(obj.font())
            painter.setPen(obj.palette().color(obj.foregroundRole()))
            painter.drawText(rect, obj.alignment(), text)
        return True


class CardPaintFilter(QObject):
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        return event.type() == QEvent.Type.Paint


class CollapsibleSettingCardGroup(CardWidget):
    orderChanged = Signal()

    def __init__(self, icon: FluentIconBase, title: str, key: str, parent=None):
        super().__init__(parent)
        self.setObjectName(key)

        self.titleLabel = StrongBodyLabel(title, self)
        self.moveUpButton = TransparentToolButton(FluentIcon.UP, self)
        self.moveDownButton = TransparentToolButton(FluentIcon.DOWN, self)
        self.expandButton = TransparentToolButton(FluentIcon.CHEVRON_DOWN_MED, self)
        self.cardContainer = QWidget(self)
        self._cardPaintFilter = CardPaintFilter(self)
        self._labelElideFilter = LabelElideFilter(self)
        self._collapseAnim = QPropertyAnimation(self.cardContainer, QByteArray(b"maximumHeight"), self)

        self.headerLayout = QHBoxLayout()
        self.cardLayout = QVBoxLayout(self.cardContainer)
        self.vBoxLayout = QVBoxLayout(self)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        for btn in (self.moveUpButton, self.moveDownButton, self.expandButton):
            btn.setFixedSize(26, 26)
            btn.setIconSize(QSize(12, 12))
        self.moveUpButton.setVisible(False)
        self.moveDownButton.setVisible(False)
        self.titleLabel.setFixedHeight(26)

        self._collapseAnim.setDuration(200)
        self._collapseAnim.setEasingCurve(QEasingCurve.Type.OutCubic)

        FluentStyleSheet.SETTING_CARD_GROUP.apply(self)

        self._collapsed = self.objectName() not in cfg.expandedSettingGroups.value
        self.cardContainer.setMaximumHeight(0 if self._collapsed else QWIDGETSIZE_MAX)
        self.expandButton.setIcon(FluentIcon.CHEVRON_RIGHT_MED if self._collapsed else FluentIcon.CHEVRON_DOWN_MED)

    def _initLayout(self) -> None:
        self.headerLayout.setContentsMargins(16, 4, 8, 4)
        self.headerLayout.setSpacing(4)
        self.headerLayout.addWidget(self.titleLabel)
        self.headerLayout.addStretch(1)
        self.headerLayout.addWidget(self.moveUpButton)
        self.headerLayout.addWidget(self.moveDownButton)
        self.headerLayout.addWidget(self.expandButton)

        self.cardLayout.setContentsMargins(0, 0, 0, 0)
        self.cardLayout.setSpacing(0)

        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setSpacing(0)
        self.vBoxLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.vBoxLayout.addLayout(self.headerLayout)
        self.vBoxLayout.addWidget(self.cardContainer)

    def _bind(self) -> None:
        self.expandButton.clicked.connect(self._onExpandClicked)
        self.moveUpButton.clicked.connect(lambda: self._reorder(-1))
        self.moveDownButton.clicked.connect(lambda: self._reorder(1))
        self._collapseAnim.finished.connect(self._onCollapseFinished)

    def addSettingCard(self, card: SettingCard) -> None:
        self.cardLayout.addWidget(card)
        targets: list[QWidget] = [card]
        if isinstance(card, ExpandSettingCard):
            targets += card.findChildren(SettingCard)
            targets += card.findChildren(ExpandBorderWidget)
            targets += card.findChildren(GroupSeparator)
        for w in targets:
            w.installEventFilter(self._cardPaintFilter)
            if isinstance(w, SettingCard):
                for label in (w.titleLabel, w.contentLabel):
                    label.setWordWrap(False)
                    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                    w.vBoxLayout.setAlignment(label, Qt.AlignmentFlag.AlignVCenter)
                    label.installEventFilter(self._labelElideFilter)
                w.hBoxLayout.setStretchFactor(w.vBoxLayout, 1 << 16)

    def addSettingCards(self, cards: list[SettingCard]) -> None:
        for card in cards:
            self.addSettingCard(card)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < self.cardContainer.geometry().top():
            self._onExpandClicked()
        super().mousePressEvent(event)

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self.moveUpButton.setVisible(True)
        self.moveDownButton.setVisible(True)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self.moveUpButton.setVisible(False)
        self.moveDownButton.setVisible(False)

    def _normalBackgroundColor(self):
        return QColor(255, 255, 255, 13 if isDarkTheme() else 170)

    def _onExpandClicked(self) -> None:
        self._setCollapsed(not self._collapsed)
        key = self.objectName()
        items = list(cfg.expandedSettingGroups.value)
        if not self._collapsed and key not in items:
            items.append(key)
        elif self._collapsed and key in items:
            items.remove(key)
        cfg.set(cfg.expandedSettingGroups, items)

    def _setCollapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.expandButton.setIcon(FluentIcon.CHEVRON_RIGHT_MED if collapsed else FluentIcon.CHEVRON_DOWN_MED)
        self._collapseAnim.stop()
        self._collapseAnim.setStartValue(self.cardContainer.height())
        self._collapseAnim.setEndValue(0 if collapsed else self.cardContainer.sizeHint().height())
        self._collapseAnim.start()

    def _onCollapseFinished(self) -> None:
        if not self._collapsed:
            self.cardContainer.setMaximumHeight(QWIDGETSIZE_MAX)

    def _reorder(self, offset: int) -> None:
        siblings = self._siblings()
        target = siblings[siblings.index(self) + offset]
        layout = self.parentWidget().layout()
        layout.insertWidget(layout.indexOf(target), self)
        self._saveOrder()
        for s in self._siblings():
            s.updateArrows()
        self.orderChanged.emit()

    def _siblings(self) -> list[CollapsibleSettingCardGroup]:
        layout = self.parentWidget().layout()
        return [
            layout.itemAt(i).widget() for i in range(layout.count())
            if isinstance(layout.itemAt(i).widget(), CollapsibleSettingCardGroup)
        ]

    def updateArrows(self) -> None:
        siblings = self._siblings()
        idx = siblings.index(self)
        self.moveUpButton.setEnabled(idx > 0)
        self.moveDownButton.setEnabled(idx < len(siblings) - 1)

    def _saveOrder(self) -> None:
        currentKeys = [s.objectName() for s in self._siblings()]
        stored = list(cfg.settingGroupOrder.value)
        stale = [k for k in stored if k not in currentKeys]
        cfg.set(cfg.settingGroupOrder, currentKeys + stale)
