"""在桌面上预览移动端 UI，用于开发调试。

用法: uv run python android/preview.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.platform.android as _android
_android.nativeLibraryDir = lambda: ""
_android.isStorageGranted = lambda: True
_android.requestStoragePermission = lambda: None
_android.sharedText = lambda: None
_android.clearShare = lambda: None
_android.isSystemDark = lambda: False

import app.platform.android_notification as _notif
_notif.isNotificationEnabled = lambda: True
_notif.requestNotificationPermission = lambda: None


if __name__ == "__main__":
    from main import setupEnvironment
    from app.platform.application import SingletonApplication
    from app.startup import loadEngine, loadPacks, startEngine, stopEngine

    setupEnvironment()
    app = SingletonApplication(sys.argv, "gd3-mobile-preview")

    from app.view.mobile import setupAndroid
    setupAndroid()

    loadEngine(app)
    loadPacks()

    from app.view.mobile.window import MobileMainWindow
    from app.view.mobile.device import setupTouchScrolling
    window = MobileMainWindow()
    window.resize(400, 800)
    window.show()
    setupTouchScrolling(window)

    startEngine()
    app.aboutToQuit.connect(stopEngine)
    sys.exit(app.exec())
