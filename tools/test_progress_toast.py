"""Standalone visual test for ProgressToast. Run from project root:
    .venv/bin/python3 tools/test_progress_toast.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget

from app.services.update_service import UpdateInfo, UpdateState
from app.view.components.progress_toast import ProgressToast


def main():
    app = QApplication(sys.argv)
    window = QWidget()
    window.setFixedSize(800, 500)
    window.setWindowTitle("ProgressToast Test")
    window.show()

    toast = ProgressToast(onRetry=lambda: print("retry clicked"), parent=window)

    progress = [0.0]

    def tick():
        progress[0] += 5
        if progress[0] > 100:
            progress[0] = 100
        info = UpdateInfo(
            targetId="app", label="Ghost Downloader v4.3.0",
            currentVersion="4.2.6", latestVersion="4.3.0",
            state=UpdateState.DOWNLOADING, progress=progress[0],
        )
        toast.setInfo(info)
        if progress[0] < 100:
            QTimer.singleShot(200, tick)
        else:
            QTimer.singleShot(1000, showReady)

    def showReady():
        info = UpdateInfo(
            targetId="app", label="Ghost Downloader v4.3.0",
            currentVersion="4.2.6", latestVersion="4.3.0",
            state=UpdateState.READY,
        )
        toast.setInfo(info)
        QTimer.singleShot(7000, showFailed)

    def showFailed():
        nonlocal toast
        toast.deleteLater()
        toast = ProgressToast(onRetry=lambda: print("retry clicked"), parent=window)
        info = UpdateInfo(
            targetId="app", label="Ghost Downloader v4.3.0",
            currentVersion="4.2.6", latestVersion="4.3.0",
            state=UpdateState.FAILED, error="网络连接超时",
        )
        toast.setInfo(info)

    QTimer.singleShot(500, tick)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
