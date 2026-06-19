def patchCollapsibleGroupTouch() -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget

    from app.view.components.setting_card_group import CollapsibleSettingCardGroup

    def mousePressEvent(self, event) -> None:
        self._headerPressed = (
            event.button() == Qt.MouseButton.LeftButton
            and event.position().y() < self.cardContainer.geometry().top()
        )
        QWidget.mousePressEvent(self, event)

    def mouseReleaseEvent(self, event) -> None:
        if getattr(self, "_headerPressed", False) and event.button() == Qt.MouseButton.LeftButton:
            self._onExpandButtonClicked()
        self._headerPressed = False
        QWidget.mouseReleaseEvent(self, event)

    CollapsibleSettingCardGroup.mousePressEvent = mousePressEvent
    CollapsibleSettingCardGroup.mouseReleaseEvent = mouseReleaseEvent

def setupTouchScrolling(window) -> None:
    from PySide6.QtCore import QEvent, QObject
    from PySide6.QtWidgets import QAbstractScrollArea, QScroller, QScrollerProperties, QWidget
    from qfluentwidgets.components.settings.expand_setting_card import ExpandSettingCard

    class ScrollClickGuard(QObject):
        def __init__(self, parent):
            super().__init__(parent)
            self._pressPosition = None

        def eventFilter(self, obj, event) -> bool:
            eventType = event.type()
            if eventType == QEvent.Type.MouseButtonPress:
                self._pressPosition = event.globalPosition().toPoint()
            elif eventType == QEvent.Type.MouseButtonRelease and self._pressPosition is not None:
                moved = (event.globalPosition().toPoint() - self._pressPosition).manhattanLength()
                self._pressPosition = None
                if moved > 12:
                    return True
            return False

    guard = ScrollClickGuard(window)
    for scrollArea in window.findChildren(QAbstractScrollArea):
        if isinstance(scrollArea, ExpandSettingCard):
            continue
        QScroller.grabGesture(scrollArea.viewport(), QScroller.ScrollerGestureType.TouchGesture)
        scroller = QScroller.scroller(scrollArea.viewport())
        properties = scroller.scrollerProperties()
        noOvershoot = QScrollerProperties.OvershootPolicy.OvershootAlwaysOff
        properties.setScrollMetric(QScrollerProperties.ScrollMetric.VerticalOvershootPolicy, noOvershoot)
        properties.setScrollMetric(QScrollerProperties.ScrollMetric.HorizontalOvershootPolicy, noOvershoot)
        scroller.setScrollerProperties(properties)
        for child in scrollArea.findChildren(QWidget):
            child.installEventFilter(guard)
