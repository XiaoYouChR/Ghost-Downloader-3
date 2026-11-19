from __future__ import annotations

from PySide6.QtCore import (
    QByteArray, QEasingCurve, QEvent, QItemSelectionModel, QObject,
    QPropertyAnimation, QSize, Qt, Signal,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLayout,
    QListWidgetItem, QSizePolicy, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    CardWidget, FluentIcon, FluentStyleSheet, ListWidget, SettingCard,
    StrongBodyLabel, TransparentToolButton, isDarkTheme,
)
from qfluentwidgets.components.settings.expand_setting_card import (
    ExpandBorderWidget, ExpandButton, GroupSeparator, HeaderSettingCard,
)

from app.config.cfg import cfg
from app.view.components.scroll_area import PAGE_MARGIN, ScrollArea

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


class CollapsibleSettingCard(QWidget):

    def __init__(self, icon, title: str, content: str | None = None, parent=None):
        super().__init__(parent)
        self.isExpand = False

        self.card = HeaderSettingCard(icon, title, content, self)
        self.view = QWidget(self)
        self.borderWidget = ExpandBorderWidget(self)

        self._expandAnim = QPropertyAnimation(self.view, QByteArray(b"maximumHeight"), self)
        self._expandAnim.setDuration(200)
        self._expandAnim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.vBoxLayout = QVBoxLayout(self)
        self.viewLayout = QVBoxLayout(self.view)

        self.view.setMaximumHeight(0)
        self.view.setObjectName("view")
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setSpacing(0)
        self.vBoxLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.vBoxLayout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.vBoxLayout.addWidget(self.card)
        self.vBoxLayout.addWidget(self.view)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.viewLayout.setSpacing(0)

        self.card.expandButton.clicked.connect(self._onExpandClicked)
        self._expandAnim.finished.connect(self._onExpandFinished)

        FluentStyleSheet.EXPAND_SETTING_CARD.apply(self.card)
        FluentStyleSheet.EXPAND_SETTING_CARD.apply(self)

    def addWidget(self, widget: QWidget) -> None:
        self.card.addWidget(widget)

    def addGroupWidget(self, widget: QWidget) -> None:
        if self.viewLayout.count() >= 1:
            self.viewLayout.addWidget(GroupSeparator(self.view))
        widget.setParent(self.view)
        self.viewLayout.addWidget(widget)

    def setExpand(self, isExpand: bool) -> None:
        if self.isExpand == isExpand:
            return
        self.isExpand = isExpand
        self.setProperty("isExpand", isExpand)
        self.setStyle(QApplication.style())
        self.card.expandButton.setExpand(isExpand)
        self._expandAnim.stop()
        self._expandAnim.setStartValue(self.view.height())
        self._expandAnim.setEndValue(0 if not isExpand else self.view.sizeHint().height())
        self._expandAnim.start()

    def _onExpandClicked(self) -> None:
        self.setExpand(not self.isExpand)

    def _onExpandFinished(self) -> None:
        if self.isExpand:
            self.view.setMaximumHeight(QWIDGETSIZE_MAX)



def isSearchMatch(card: SettingCard | CollapsibleSettingCard, text: str) -> bool:
    if isinstance(card, CollapsibleSettingCard):
        card = card.card
    return text in card.titleLabel.text().lower() or text in card.contentLabel.text().lower()


class CollapsibleSettingCardGroup(CardWidget):
    orderChanged = Signal()

    def __init__(self, title: str, key: str, parent=None):
        super().__init__(parent)
        self.setObjectName(key)

        self.titleLabel = StrongBodyLabel(title, self)
        self.moveUpButton = TransparentToolButton(FluentIcon.UP, self)
        self.moveDownButton = TransparentToolButton(FluentIcon.DOWN, self)
        self.expandButton = ExpandButton(self)
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
        for btn in (self.moveUpButton, self.moveDownButton):
            btn.setFixedSize(30, 30)
            btn.setIconSize(QSize(10, 10))
        self.moveUpButton.setVisible(False)
        self.moveDownButton.setVisible(False)
        self.titleLabel.setFixedHeight(26)

        self._collapseAnim.setDuration(200)
        self._collapseAnim.setEasingCurve(QEasingCurve.Type.OutCubic)

        FluentStyleSheet.SETTING_CARD_GROUP.apply(self)

        self._collapsed = self.objectName() not in cfg.expandedSettingGroups.value
        self.cardContainer.setMaximumHeight(0 if self._collapsed else QWIDGETSIZE_MAX)
        self.expandButton.setAngle(0 if self._collapsed else 180)

    def _initLayout(self) -> None:
        self.headerLayout.setContentsMargins(16, 10, 8, 10)
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
        self.vBoxLayout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
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
        if isinstance(card, CollapsibleSettingCard):
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

    def setSearchText(self, text: str) -> None:
        text = text.strip().lower()
        hasMatch = False
        for i in range(self.cardLayout.count()):
            card = self.cardLayout.itemAt(i).widget()
            if card is None:
                continue
            isMatch = not text or isSearchMatch(card, text)
            card.setVisible(isMatch)
            hasMatch = hasMatch or isMatch
        self.setVisible(hasMatch or not text)
        isExpand = (bool(text) and hasMatch) or self.objectName() in cfg.expandedSettingGroups.value
        self._setCollapsed(not isExpand)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < self.cardContainer.geometry().top():
            self._onExpandClicked()
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.cardContainer.height() > 0:
            with QPainter(self) as painter:
                painter.fillRect(1, self.cardContainer.y() - 1, self.width() - 2, 1, QColor(0, 0, 0, 96 if isDarkTheme() else 24))

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

    @property
    def isCollapsed(self) -> bool:
        return self._collapsed

    def setCollapsed(self, isCollapsed: bool, *, animate: bool = True) -> None:
        if isCollapsed == self._collapsed:
            return
        self._setCollapsed(isCollapsed, animate=animate)
        key = self.objectName()
        items = list(cfg.expandedSettingGroups.value)
        if not isCollapsed and key not in items:
            items.append(key)
        elif isCollapsed and key in items:
            items.remove(key)
        cfg.set(cfg.expandedSettingGroups, items)

    def _onExpandClicked(self) -> None:
        self.setCollapsed(not self._collapsed)

    def _setCollapsed(self, collapsed: bool, *, animate: bool = True) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.expandButton.setExpand(not collapsed)
        self._collapseAnim.stop()
        if not animate:
            self.cardContainer.setMaximumHeight(0 if collapsed else QWIDGETSIZE_MAX)
            return
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
        return groupsIn(self.parentWidget().layout())

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


def groupsIn(layout: QLayout) -> list[CollapsibleSettingCardGroup]:
    return [
        w for i in range(layout.count())
        if isinstance(w := layout.itemAt(i).widget(), CollapsibleSettingCardGroup)
    ]


def restoreGroupOrder(layout: QVBoxLayout, tailKey: str = "about") -> None:
    groups = groupsIn(layout)
    keyToWidget = {g.objectName(): g for g in groups}
    order = [k for k in cfg.settingGroupOrder.value if k in keyToWidget]
    rest = [k for k in keyToWidget if k not in order]
    if tailKey in rest:
        rest.remove(tailKey)
        rest.append(tailKey)
    order += rest
    for idx, key in enumerate(order):
        layout.insertWidget(idx, keyToWidget[key])
    for g in groups:
        g.updateArrows()


NAV_WIDTH = 164


class SettingGroupNav(ListWidget):

    def __init__(self, targetArea: ScrollArea, parent: QWidget | None = None):
        super().__init__(parent)
        self._targetArea = targetArea
        self._partnerBar = targetArea.verticalScrollBar()
        self._connected: set[CollapsibleSettingCardGroup] = set()
        self._jumpGroup: CollapsibleSettingCardGroup | None = None

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.setFixedWidth(NAV_WIDTH)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def _initLayout(self) -> None:
        # ListWidget 样式自带左右 4px 内边距，delegate 上下各留 2px 边距
        self.setViewportMargins(PAGE_MARGIN - 4, PAGE_MARGIN - 2, 0, PAGE_MARGIN - 2)

    def _bind(self) -> None:
        self.itemClicked.connect(self._onItemClicked)
        self._partnerBar.valueChanged.connect(self._refreshActive)
        self._partnerBar.rangeChanged.connect(self._refreshActive)

    def refresh(self) -> None:
        groups = groupsIn(self._targetArea.widget().layout())
        if [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())] != groups:
            self._rebuild(groups)
        for i in range(self.count()):
            item = self.item(i)
            item.setHidden(item.data(Qt.ItemDataRole.UserRole).isHidden())
        if self._jumpGroup is not None and self._jumpGroup.isHidden():
            self._jumpGroup = None
        self._refreshActive()

    def _rebuild(self, groups: list[CollapsibleSettingCardGroup]) -> None:
        itemWidth = NAV_WIDTH - PAGE_MARGIN - 4
        avail = itemWidth - 22
        self.clear()
        for group in groups:
            if group not in self._connected:
                self._connected.add(group)
                group.orderChanged.connect(self.refresh)
            text = group.titleLabel.text()
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, group)
            item.setSizeHint(QSize(itemWidth, 32))
            if self.fontMetrics().horizontalAdvance(text) > avail:
                item.setToolTip(text)
            self.addItem(item)

    def _selectRow(self, row: int) -> None:
        if row != self.currentRow() or not self.selectionModel().isSelected(self.model().index(row, 0)):
            self.setCurrentRow(row, QItemSelectionModel.SelectionFlag.ClearAndSelect)

    def _onItemClicked(self, item: QListWidgetItem) -> None:
        group: CollapsibleSettingCardGroup = item.data(Qt.ItemDataRole.UserRole)
        group.setCollapsed(False, animate=False)
        self._targetArea.widget().adjustSize()
        self._jumpGroup = group
        self._selectRow(self.row(item))
        self._targetArea.scrollTo(group.y() - PAGE_MARGIN)

    def _scrollValueOf(self, group: CollapsibleSettingCardGroup) -> int:
        return max(0, min(self._partnerBar.maximum(), group.y() - PAGE_MARGIN))

    def _refreshActive(self, *_) -> None:
        if self._jumpGroup is not None and self._targetArea.scrollTarget() != self._scrollValueOf(self._jumpGroup):
            self._jumpGroup = None
        visible = [
            (i, g) for i in range(self.count())
            if not (g := self.item(i).data(Qt.ItemDataRole.UserRole)).isHidden()
        ]
        if not visible:
            if self.selectionModel().hasSelection():
                self.clearSelection()
            return
        if self._jumpGroup is not None:
            for row, g in visible:
                if g is self._jumpGroup:
                    self._selectRow(row)
                    return
        anchorY = self._partnerBar.value() + PAGE_MARGIN + 24
        chosenRow = visible[0][0]
        if self._partnerBar.value() > 0:
            for row, g in visible:
                if g.y() <= anchorY:
                    chosenRow = row
                else:
                    break
        self._selectRow(chosenRow)
