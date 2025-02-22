import os
import sys

from app.common.config import VERSION, YEAR, AUTHOR

if 'nuitka' in sys.argv:
    if sys.platform == "win32":
        args = [
            'nuitka',
            '--standalone',
            '--windows-console-mode=disable',
            '--plugin-enable=pyside6' ,
            '--assume-yes-for-downloads',
            # '--msvc=latest',              # Use MSVC
            '--mingw64',                    # Use MinGW
            '--show-memory' ,
            '--show-progress' ,
            '--windows-icon-from-ico=resources/logo.ico',
            '--company-name=XiaoYouChR',
            '--product-name="Ghost Downloader"',
            f'--file-version={VERSION}',
            f'--product-version={VERSION}',
            '--file-description="Ghost Downloader"',
            f'--copyright="Copyright(C) {YEAR} {AUTHOR}"',
            '--output-dir=dist',
            'Ghost-Downloader-3.py',
        ]
    elif sys.platform == "darwin":
        args = [
            'python3 -m nuitka',
            '--standalone',
            '--plugin-enable=pyside6',
            '--show-memory',
            '--show-progress',
            "--macos-create-app-bundle",
            "--assume-yes-for-download",
            "--macos-app-mode=gui",
            f"--macos-app-version={VERSION}",
            "--macos-app-icon=resources/logo.icns",
            f'--copyright="Copyright(C) {YEAR} {AUTHOR}"',
            '--output-dir=dist',
            'Ghost-Downloader-3.py',
        ]
    else:
        args = [
            'nuitka',
            '--standalone',
            '--plugin-enable=pyside6',
            '--include-qt-plugins=platforms',
            '--assume-yes-for-downloads',
            '--show-memory',
            '--show-progress',
            '--linux-icon=resources/logo.ico',
            '--output-dir=dist',
            'Ghost-Downloader-3.py',
        ]
# PyInstaller Deploy支持
elif 'pyinstaller' in sys.argv:
    if sys.platform == "win32":
        args = [
            'pyinstaller',
            '--distpath', './dist/pyinstaller',
            '--noconfirm',
            '--clean',
            '--onefile',
            '--windowed',
            '--icon', 'resources/logo.ico',
            '--version-file', 'version.txt',
            'Ghost-Downloader-3.py',
        ]
    elif sys.platform == "darwin":
        args = [
            'pyinstaller',
            '--distpath', './dist/pyinstaller',
            '--noconfirm',
            '--clean',
            '--onefile',
            '--windowed',
            '--icon', 'resources/logo.icns',
            '--version-file', 'version.txt',
            'Ghost-Downloader-3.py',
        ]
    else:
        args = [
            'pyinstaller',
            '--distpath', './dist/pyinstaller',
            '--noconfirm',
            '--clean',
            '--onefile',
            '--windowed',
            '--icon', 'resources/logo.ico',
            '--version-file', 'version.txt',
            'Ghost-Downloader-3.py',

        ]
else:
    raise Exception("Unknown deploy mode.")

os.system(' '.join(args))
