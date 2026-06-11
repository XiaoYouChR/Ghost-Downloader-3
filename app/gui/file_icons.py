from PySide6.QtCore import QFileInfo
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtWidgets import QFileIconProvider


class FileIconProvider(QQuickImageProvider):
    """按文件名给真实 OS 类型图标，复刻原版的文件图标。
    QML 用 `image://fileicon/<文件名>`；id 是文件名（含扩展名），QFileIconProvider 按扩展名解析——
    预览（文件还没下载）也能出类型图标。纯 gui 端（QFileIconProvider 是桌面控件），headless/daemon 不涉及。"""

    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._provider = QFileIconProvider()

    def requestImage(self, id, size, requestedSize):
        edge = requestedSize.width() if requestedSize.width() > 0 else 48
        image = self._provider.icon(QFileInfo(id)).pixmap(edge, edge).toImage()
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image
