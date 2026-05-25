from typing import TYPE_CHECKING, Final

from PySide6.QtCore import (
    QByteArray,
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    QRect,
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
        lines = obj.text().splitlines() or [""]
        lineHeight = metrics.lineSpacing()
        top = rect.y() + max(0, (rect.height() - lineHeight * len(lines)) // 2)

        with QPainter(obj) as painter:
            painter.setFont(obj.font())
            painter.setPen(obj.palette().color(obj.foregroundRole()))
            for i, line in enumerate(lines):
                text = metrics.elidedText(line, Qt.TextElideMode.ElideRight, rect.width())
                painter.drawText(
                    QRect(rect.x(), top + i * lineHeight, rect.width(), lineHeight),
                    obj.alignment(),
                    text,
                )
        return True


def _prepareSettingCard(card: SettingCard, labelFilter: QObject) -> None:
    for name in ("titleLabel", "contentLabel"):
        label = getattr(card, name, None)
        if isinstance(label, QLabel):
            label.setWordWrap(False)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            card.vBoxLayout.setAlignment(label, Qt.AlignmentFlag.AlignVCenter)
            label.installEventFilter(labelFilter)

    for i in range(card.hBoxLayout.count()):
        card.hBoxLayout.setStretch(i, 0)
        if card.hBoxLayout.itemAt(i).layout() is card.vBoxLayout:
            card.hBoxLayout.setStretch(i, 1)


class _CardPaintSuppressor(QObject):
    """吞掉 watched widget 的 paintEvent。

    子控件（icon/label/switch）有自己的 paintEvent 不受影响，结果是
    widget 自身背景消失但子内容照常显示。配合外层 group 的 paintEvent
    画整体卡片背景，把 qfluentwidgets SettingCard 的圆角背景"压平"。
    """

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        return event.type() == QEvent.Type.Paint


class CollapsibleSettingCardGroup(QWidget):
    orderChanged = Signal()  # sibling 顺序变化

    def __init__(self, title: str, key: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(key)

        # instant widget
        self.titleLabel = StrongBodyLabel(title, self)
        self.moveUpButton = TransparentToolButton(FluentIcon.UP, self)
        self.moveDownButton = TransparentToolButton(FluentIcon.DOWN, self)
        self.expandButton = TransparentToolButton(FluentIcon.CHEVRON_DOWN_MED, self)
        self.cardContainer = QWidget(self)
        self._cardPaintSuppressor = _CardPaintSuppressor(self)
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
        # WA_Hover 基于"光标是否在 widget 几何内（含子孙）"判定，
        # 子控件抢不抢事件都不影响 HoverEnter/HoverLeave 的派发
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
        card.installEventFilter(self._cardPaintSuppressor)
        if isinstance(card, SettingCard):
            _prepareSettingCard(card, self._labelElideFilter)
        # ExpandSettingCard 内部有 HeaderSettingCard / ExpandBorderWidget /
        # GroupSeparator 各自画背景或分隔线，吞掉 QScrollArea 自己的 paintEvent 不够
        if isinstance(card, ExpandSettingCard):
            for sub in card.findChildren(QWidget):
                if isinstance(sub, (SettingCard, ExpandBorderWidget, GroupSeparator)):
                    sub.installEventFilter(self._cardPaintSuppressor)
                    if isinstance(sub, SettingCard):
                        _prepareSettingCard(sub, self._labelElideFilter)

    def addSettingCards(self, cards: list[QWidget]) -> None:
        for card in cards:
            self.addSettingCard(card)

    def updateArrows(self) -> None:
        siblings = self._children()
        idx = siblings.index(self)
        self.moveUpButton.setEnabled(idx > 0)
        self.moveDownButton.setEnabled(idx < len(siblings) - 1)

    def mousePressEvent(self, event: "QMouseEvent") -> None:
        # 子按钮 accept 事件不冒泡所以不会误触
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
        # 展开动画结束后解除 maxHeight 上限，让 cardContainer 能跟随子卡片自由生长
        if not self._collapsed:
            self.cardContainer.setMaximumHeight(_QWIDGETSIZE_MAX)

    def _move(self, delta: int) -> None:
        siblings = self._children()
        target = siblings[siblings.index(self) + delta]

        # insertWidget 对同 layout 已有子项语义是"移动到该索引"，邻居被挤一格正好换位
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
        # 保留 stored 中的 stale key——它们对应尚未加载（如未启用的 feature pack）
        # 的 group，下次启动时仍要恢复顺序，移除会丢失这部分信息
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
