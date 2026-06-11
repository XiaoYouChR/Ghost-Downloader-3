from io import BytesIO
from urllib.parse import unquote

import qrcode
from qrcode.image.pure import PyPNGImage
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

# 哔哩哔哩扫码登录的二维码图：QML 用 image://biliqr/<encodeURIComponent(loginUrl)>，把 B站登录 url 渲成二维码。
# 用 PyPNGImage（纯 Python，不依赖 Pillow，同原版）。纯 gui 端桌面动作。扫码登录是用户接受的 gui↔bili 耦合。


class BiliQrProvider(QQuickImageProvider):
    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)

    def requestImage(self, id, size, requestedSize):
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=2, box_size=10)
        qr.add_data(unquote(id))
        qr.make(fit=True)
        buffer = BytesIO()
        qr.make_image(image_factory=PyPNGImage).save(buffer)
        image = QImage()
        image.loadFromData(buffer.getvalue(), "PNG")
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image
