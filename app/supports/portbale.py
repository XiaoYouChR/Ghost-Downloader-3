import os
from PySide6.QtCore import QStandardPaths
    
appLocalDataLocation = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
dataPath = f"{appLocalDataLocation}/GhostDownloader"

if os.path.exists("./data"):
    dataPath = "./data"