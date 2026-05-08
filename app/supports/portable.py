import os
import sys
from PySide6.QtCore import QStandardPaths

# default system path
appDataDir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
sysDataPath = os.path.join(appDataDir, "GhostDownloader")

# default portable path
if getattr(sys, 'frozen', False):
    baseDir = os.path.dirname(sys.executable)
else:
    baseDir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

portablePath = os.path.join(baseDir, "data")

# judge portable
if os.path.exists(portablePath):
    dataPath = portablePath
else:
    dataPath = sysDataPath