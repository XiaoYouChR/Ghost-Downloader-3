import os
import sys

from app.common.config import VERSION, YEAR, AUTHOR

if sys.platform == "win32":
    args = [
        'nuitka',
        '--standalone',  # Following all imports is the default for standalone mode and need not be specified.
        '--windows-console-mode=disable',
        '--plugin-enable=pyside6' ,
        '--assume-yes-for-downloads',
        '--msvc=latest',              # Use MSVC
        # '--mingw64',                    # Use MinGW
        # '--show-memory' ,
        # '--show-progress' ,
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
        # '--show-memory',
        # '--show-progress',
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
        # '--show-memory',
        # '--show-progress',
        '--linux-icon=resources/logo.png',
        '--output-dir=dist',
        'Ghost-Downloader-3.py',
    ]


os.system(' '.join(args))
