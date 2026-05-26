from typing import TYPE_CHECKING, Final

from PySide6.QtCore import (
    QByteArray,
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    FluentIcon,
    SettingCard,
    StrongBodyLabel,
    TransparentToolButton,
    isDarkTheme,
    FluentStyleSheet,
)
from qfluentwidgets.components.settings.expand_setting_card import (
    ExpandBorderWidget,
    ExpandSettingCard,
    GroupSeparator,
)

from app.supports.config import cfg

if TYPE_CHECKING:
    from PySide6.QtGui import QMouseEvent, QPaintEvent

_QWIDGETSIZE_MAX: Final[int] = (1 << 24) - 1
_BUTTON_SIZE: Final[QSize] = QSize(26, 26)
_ICON_SIZE: Final[QSize] = QSize(12, 12)
_BORDER_RADIUS: Final[int] = 5


class _LabelElideFilter(QObject):
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.Paint or not isinstance(obj, QLabel):
            return False
        metrics = obj.fontMetrics()
        rect = obj.contentsRect()
        # elidedText 是单行的
        text = "\n".join(
            metrics.elidedText(line, Qt.TextElideMode.ElideRight, rect.width())
            for line in obj.text().splitlines() or [""]
        )
        with QPainter(obj) as painter:
            painter.setFont(obj.font())
            painter.setPen(obj.palette().color(obj.foregroundRole()))
            painter.drawText(rect, obj.alignment(), text)
        return True


class _CardPaintFilter(QObject):
    """压平 qfluentwidgets SettingCard 自带的圆角背景"""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        return event.type() == QEvent.Type.Paint


class CollapsibleSettingCardGroup(QWidget):
    orderChanged = Signal()

    def __init__(self, title: str, key: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(key)

        # instant widget
        self.titleLabel = StrongBodyLabel(title, self)
        self.moveUpButton = TransparentToolButton(FluentIcon.UP, self)
        self.moveDownButton = TransparentToolButton(FluentIcon.DOWN, self)
        self.expandButton = TransparentToolButton(FluentIcon.CHEVRON_DOWN_MED, self)
        self.cardContainer = QWidget(self)
        self._cardPaintFilter = _CardPaintFilter(self)
        self._labelElideFilter = _LabelElideFilter(self)
        self._collapseAnim = QPropertyAnimation(
            self.cardContainer, QByteArray(b"maximumHeight"), self
        )

        # instant layout
        self.headerLayout = QHBoxLayout()
        self.cardLayout = QVBoxLayout(self.cardContainer)
        self.vBoxLayout = QVBoxLayout(self)

        # init
        self._initWidget()
        self._initLayout()

        # bind
        self._bind()

    def _initWidget(self) -> None:
        for btn in (self.moveUpButton, self.moveDownButton, self.expandButton):
            btn.setFixedSize(_BUTTON_SIZE)
            btn.setIconSize(_ICON_SIZE)
        self.moveUpButton.setVisible(False)
        self.moveDownButton.setVisible(False)

        self._collapseAnim.setDuration(200)
        self._collapseAnim.setEasingCurve(QEasingCurve.Type.OutCubic)

        FluentStyleSheet.SETTING_CARD_GROUP.apply(self)
        # WA_Hover 派发不被子控件 accept 截断
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        self._setCollapsed(
            self.objectName() in cfg.collapsedSettingGroups.value,
            animated=False,
        )

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
        self.vBoxLayout.addWidget(self.cardContainer, 1)

    def _bind(self) -> None:
        self.expandButton.clicked.connect(self._onExpandButtonClicked)
        self.moveUpButton.clicked.connect(lambda: self._move(-1))
        self.moveDownButton.clicked.connect(lambda: self._move(1))
        self._collapseAnim.finished.connect(self._onCollapseAnimFinished)

    def addSettingCard(self, card: QWidget) -> None:
        self.cardLayout.addWidget(card)
        # ExpandSettingCard 内部子控件也自绘背景
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
                # 压住 SettingCard 自带的 addStretch
                w.hBoxLayout.setStretchFactor(w.vBoxLayout, 1 << 16)

    def addSettingCards(self, cards: list[QWidget]) -> None:
        for card in cards:
            self.addSettingCard(card)

    def updateArrows(self) -> None:
        siblings = self._children()
        idx = siblings.index(self)
        self.moveUpButton.setEnabled(idx > 0)
        self.moveDownButton.setEnabled(idx < len(siblings) - 1)

    def mousePressEvent(self, event: "QMouseEvent") -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and event.position().y() < self.cardContainer.geometry().top()
        ):
            self._onExpandButtonClicked()
        super().mousePressEvent(event)

    def _onExpandButtonClicked(self) -> None:
        self._setCollapsed(not self._collapsed)
        key = self.objectName()
        items = list(cfg.collapsedSettingGroups.value)
        if self._collapsed and key not in items:
            items.append(key)
        elif not self._collapsed and key in items:
            items.remove(key)
        cfg.set(cfg.collapsedSettingGroups, items)

    def _setCollapsed(self, collapsed: bool, animated: bool = True) -> None:
        self._collapsed = collapsed
        self.expandButton.setIcon(
            FluentIcon.CHEVRON_RIGHT_MED if collapsed else FluentIcon.CHEVRON_DOWN_MED
        )

        if not animated:
            self.cardContainer.setMaximumHeight(0 if collapsed else _QWIDGETSIZE_MAX)
            return

        self._collapseAnim.stop()
        self._collapseAnim.setStartValue(self.cardContainer.height())
        self._collapseAnim.setEndValue(
            0 if collapsed else self.cardContainer.sizeHint().height()
        )
        self._collapseAnim.start()

    def _onCollapseAnimFinished(self) -> None:
        # 不解除上限 cardContainer 后续不会跟随子卡生长
        if not self._collapsed:
            self.cardContainer.setMaximumHeight(_QWIDGETSIZE_MAX)

    def _move(self, delta: int) -> None:
        siblings = self._children()
        target = siblings[siblings.index(self) + delta]

        # insertWidget 对已存在子项是"移动"语义
        layout = self.parentWidget().layout()
        layout.insertWidget(layout.indexOf(target), self)

        self._saveOrder()
        for s in self._children():
            s.updateArrows()
        self.orderChanged.emit()

    def _children(self) -> list["CollapsibleSettingCardGroup"]:
        layout = self.parentWidget().layout()
        result: list[CollapsibleSettingCardGroup] = []
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if isinstance(w, CollapsibleSettingCardGroup):
                result.append(w)
        return result

    def _saveOrder(self) -> None:
        # stale key 对应未加载的 group（如未启用的 feature pack），留着下次恢复
        currentKeys = [s.objectName() for s in self._children()]
        stored = list(cfg.settingGroupOrder.value)
        stale = [k for k in stored if k not in currentKeys]
        cfg.set(cfg.settingGroupOrder, currentKeys + stale)

    def event(self, event: QEvent) -> bool:
        et = event.type()
        if et == QEvent.Type.HoverEnter:
            self.moveUpButton.setVisible(True)
            self.moveDownButton.setVisible(True)
        elif et == QEvent.Type.HoverLeave:
            self.moveUpButton.setVisible(False)
            self.moveDownButton.setVisible(False)
        return super().event(event)

    def paintEvent(self, event: "QPaintEvent") -> None:
        super().paintEvent(event)
        with QPainter(self) as painter:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            isDark = isDarkTheme()
            bg = QColor(255, 255, 255, 13) if isDark else QColor(255, 255, 255, 200)
            border = QColor(0, 0, 0, 96) if isDark else QColor(0, 0, 0, 24)

            painter.setBrush(bg)
            painter.setPen(border)
            painter.drawRoundedRect(
                QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                _BORDER_RADIUS,
                _BORDER_RADIUS,
            )
