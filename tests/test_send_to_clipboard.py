from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication

from app.platform.desktop import sendToClipboard


def test_send_to_clipboard_puts_file_url(qapp, tmp_path):
    file = tmp_path / "文件.zip"
    file.write_bytes(b"content")

    sendToClipboard(file)

    assert QApplication.clipboard().mimeData().urls() == [QUrl.fromLocalFile(str(file))]


def test_send_to_clipboard_puts_folder_url(qapp, tmp_path):
    folder = tmp_path / "成品"
    folder.mkdir()

    sendToClipboard(folder)

    assert QApplication.clipboard().mimeData().urls() == [QUrl.fromLocalFile(str(folder))]
