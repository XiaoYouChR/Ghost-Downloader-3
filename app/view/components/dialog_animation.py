from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QRect, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QRegion
from PySide6.QtWidgets import QDialog, QWidget
from qfluentwidgets.common.animation import FluentAnimation
from qfluentwidgets.components.dialog_box.mask_dialog_base import MaskDialogBase

FADE_IN_DURATION = 200
FADE_OUT_DURATION = 100
SLIDE_DURATION = 300
FADE_IN_CURVE = QEasingCurve(QEasingCurve.Type.InSine)
SLIDE_IN_CURVE = FluentAnimation.createBezierCurve(0, 0, 0, 1)
SLIDE_OUT_CURVE = FluentAnimation.createBezierCurve(0.8, 0, 0.78, 1)


def showEvent(dialog: MaskDialogBase, e) -> None:
    QDialog.showEvent(dialog, e)
    AnimationLayer(dialog, isClosing=False)


def done(dialog: MaskDialogBase, code: int) -> None:
    if any(layer.isClosing for layer in dialog.findChildren(AnimationLayer, options=Qt.FindChildOption.FindDirectChildrenOnly)):
        return
    layer = AnimationLayer(dialog, isClosing=True)
    layer.finished.connect(lambda: QDialog.done(dialog, code))


def toSlideOffset(dialog: MaskDialogBase) -> QPoint:
    panel = dialog.widget.geometry()
    return {
        Qt.Edge.LeftEdge: QPoint(-panel.right() - 1, 0),
        Qt.Edge.RightEdge: QPoint(dialog.width() - panel.left(), 0),
        Qt.Edge.TopEdge: QPoint(0, -panel.bottom() - 1),
        Qt.Edge.BottomEdge: QPoint(0, dialog.height() - panel.top()),
    }.get(dialog.slideEdge, QPoint())


class AnimationLayer(QWidget):

    def __init__(self, dialog: MaskDialogBase, isClosing: bool):
        super().__init__(dialog)
        self.isClosing = isClosing
        self._dialog = dialog
        if dialog.slideEdge is not None:
            duration = SLIDE_DURATION
        else:
            duration = FADE_OUT_DURATION if isClosing else FADE_IN_DURATION
        self._animation = QVariantAnimation(self, startValue=0.0, endValue=float(duration), duration=duration)
        self._panel = QPixmap()
        self._isRenderingPanel = False
        self.finished = self._animation.finished
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setGeometry(dialog.rect())
        # 先停掉上一段动画，免得它被截进新图
        for layer in dialog.findChildren(AnimationLayer, options=Qt.FindChildOption.FindDirectChildrenOnly):
            if layer is not self:
                layer._animation.stop()
        self._backdrop = self._buildBackdrop()
        self._animation.valueChanged.connect(self.update)
        # Nuitka 编译后会永久持有连到信号上的绑定方法，用 lambda 这一层和截图才能释放
        self._animation.stateChanged.connect(lambda state: self._onAnimationStateChanged(state))
        # 对话框声明不透明，Qt 就不再重画底下的页面
        dialog.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        # 关闭时当场截图，窗口最小化时也能关掉
        if isClosing:
            self._run()
        self.show()
        # polish 会清掉这个属性，所以在 show 之后设置
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.raise_()

    def _run(self) -> None:
        self._maskColor = self._buildMaskColor()
        self._panelOrigin, self._panel = self._buildPanel()
        # 关掉阴影效果，面板就不会每帧重新模糊
        self._setPanelEffectEnabled(False)
        self._animation.start()

    def _toFrame(self, ms: float) -> tuple[float, float, QPoint]:
        # 返回 (遮罩透明度, 面板透明度, 面板偏移)
        offset = toSlideOffset(self._dialog)
        if not self.isClosing:
            opacity = FADE_IN_CURVE.valueForProgress(min(ms / FADE_IN_DURATION, 1))
            return opacity, opacity, offset * (1 - SLIDE_IN_CURVE.valueForProgress(ms / SLIDE_DURATION))
        if self._dialog.slideEdge is None:
            opacity = 1 - ms / FADE_OUT_DURATION
            return opacity, opacity, offset
        progress = ms / SLIDE_DURATION
        return 1 - progress, 1.0, offset * SLIDE_OUT_CURVE.valueForProgress(progress)

    def _onAnimationStateChanged(self, state: QVariantAnimation.State) -> None:
        if state == QVariantAnimation.State.Stopped:
            self._dialog.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
            self._setPanelEffectEnabled(True)
            self.hide()
            self.deleteLater()

    def _setPanelEffectEnabled(self, isEnabled: bool) -> None:
        effect = self._dialog.widget.graphicsEffect()
        if effect is not None:
            effect.setEnabled(isEnabled)

    def _buildBackdrop(self) -> QPixmap:
        window = self._dialog.window()
        image = window.backingStore().paintDevice()
        # 打开时对话框还没画过，后备缓冲里就是底下的画面，直接复制最快
        if not self.isClosing and isinstance(image, QImage):
            ratio = window.devicePixelRatioF()
            pixmap = QPixmap.fromImage(image.copy(QRect(self._dialog.mapTo(window, QPoint(0, 0)) * ratio, self.size() * ratio)))
            pixmap.setDevicePixelRatio(ratio)
            return pixmap
        parent = self._dialog.parentWidget()
        pixmap = self._buildPixmap(self.size())
        origin = -self._dialog.pos()
        parent.render(pixmap, origin, QRegion(), QWidget.RenderFlag(0))
        siblings = [child for child in parent.children() if isinstance(child, QWidget)]
        # 不画盖在对话框上面的兄弟控件，如 InfoBar
        for child in siblings[:siblings.index(self._dialog)]:
            if child.isVisible() and not child.isWindow():
                child.render(pixmap, origin + child.pos(), QRegion(), QWidget.RenderFlag.DrawChildren)
        return pixmap

    def _buildMaskColor(self) -> QColor:
        pixmap = QPixmap(1, 1)
        pixmap.fill(Qt.GlobalColor.transparent)
        # 不画窗口背景，否则半透明底色会叠两层
        self._dialog.windowMask.render(pixmap, QPoint(), QRegion(0, 0, 1, 1), QWidget.RenderFlag(0))
        return pixmap.toImage().pixelColor(0, 0)

    def _buildPanel(self) -> tuple[QPoint, QPixmap]:
        panel = self._dialog.widget
        mask = self._dialog.windowMask
        effect = panel.graphicsEffect()
        bounds = effect.boundingRectFor(panel.rect()).toAlignedRect() if effect else panel.rect()
        pixmap = self._buildPixmap(bounds.size())
        # 从对话框渲染才画得出阴影，渲染期间撤掉遮罩底色和这一层的不透明声明
        self._isRenderingPanel = True
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        mask.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self._dialog.render(pixmap, QPoint(), QRegion(bounds.translated(panel.pos())), QWidget.RenderFlag.DrawChildren)
        mask.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self._isRenderingPanel = False
        return bounds.topLeft(), pixmap

    def _buildPixmap(self, size) -> QPixmap:
        ratio = self.devicePixelRatioF()
        pixmap = QPixmap(size * ratio)
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        return pixmap

    def paintEvent(self, e) -> None:
        # 截面板时也会渲染到这一层
        if self._isRenderingPanel:
            return
        # 打开时等第一次绘制再截图，这时布局已排好
        if self._panel.isNull():
            self._run()
        maskOpacity, panelOpacity, panelOffset = self._toFrame(self._animation.currentValue())
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawPixmap(0, 0, self._backdrop)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        # 遮罩是纯色，直接填色最快
        maskColor = QColor(self._maskColor)
        maskColor.setAlphaF(maskColor.alphaF() * maskOpacity)
        painter.fillRect(self._dialog.windowMask.geometry(), maskColor)
        painter.setOpacity(panelOpacity)
        painter.drawPixmap(self._dialog.widget.pos() + panelOffset + self._panelOrigin, self._panel)
