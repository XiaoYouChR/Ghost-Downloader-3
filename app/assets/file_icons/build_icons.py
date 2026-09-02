"""从 SVG 源重新生成各平台文件图标 (.png/.ico/.icns)。

图标按"预渲染并提交"策略管理: SVG 是唯一可编辑源, 改动后跑这个脚本重生成并提交产物。
    QT_QPA_PLATFORM=offscreen python3 app/assets/file_icons/build_icons.py
"""

import os
import struct
import subprocess
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QRectF
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

HERE = Path(__file__).resolve().parent
STEMS = ("torrent", "m3u8")
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
ICNS_SIZES = (16, 32, 64, 128, 256, 512, 1024)
ICNS_NAMES = {
    16: ("icon_16x16.png",), 32: ("icon_16x16@2x.png", "icon_32x32.png"),
    64: ("icon_32x32@2x.png",), 128: ("icon_128x128.png",),
    256: ("icon_128x128@2x.png", "icon_256x256.png"),
    512: ("icon_256x256@2x.png", "icon_512x512.png"), 1024: ("icon_512x512@2x.png",),
}


def renderPng(svgPath: Path, size: int) -> bytes:
    renderer = QSvgRenderer(str(svgPath))
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()

    storage = QByteArray()
    buffer = QBuffer(storage)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(storage)


def writeIco(pngBySize: dict[int, bytes], outPath: Path) -> None:
    sizes = sorted(pngBySize)
    header = struct.pack("<HHH", 0, 1, len(sizes))
    entries = b""
    blobs = b""
    offset = 6 + 16 * len(sizes)
    for size in sizes:
        data = pngBySize[size]
        edge = 0 if size >= 256 else size  # ICO 用 0 表示 256
        entries += struct.pack("<BBBBHHII", edge, edge, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        blobs += data
    outPath.write_bytes(header + entries + blobs)


def writeIcns(svgPath: Path, outPath: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "icon.iconset"
        iconset.mkdir()
        for size in ICNS_SIZES:
            data = renderPng(svgPath, size)
            for name in ICNS_NAMES[size]:
                (iconset / name).write_bytes(data)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(outPath)], check=True)


def main() -> None:
    QGuiApplication([])
    for stem in STEMS:
        svgPath = HERE / f"{stem}.svg"
        (HERE / f"{stem}.png").write_bytes(renderPng(svgPath, 256))
        writeIco({size: renderPng(svgPath, size) for size in ICO_SIZES}, HERE / f"{stem}.ico")
        writeIcns(svgPath, HERE / f"{stem}.icns")
        print(f"generated {stem}.png / {stem}.ico / {stem}.icns")


if __name__ == "__main__":
    main()
