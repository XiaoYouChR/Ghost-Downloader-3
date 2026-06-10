from PySide6.QtCore import QStandardPaths

from app.engine.config import Setting

# 引擎权威配置的 schema：键 / 默认值 / 校验。默认值对齐旧 cfg，迁移时从 cfg 现值播种。
# 复杂项（categoryRules/userAgents/geometry 等带自定义序列化）暂不进，按需逐步补。
_THEME_MODES = {"Light", "Dark", "System"}

GLOBAL_SETTINGS = [
    Setting("downloadFolder", QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)),
    Setting("maxTaskNum", 3, validate=lambda v: 1 <= v <= 10),
    Setting("enableSpeedLimitation", False),
    Setting("speedLimitation", 4194304, validate=lambda v: 1024 <= v <= 104857600),
    Setting("SSLVerify", False),
    Setting("proxyServer", "Auto"),
    Setting("preBlockNum", 8, validate=lambda v: 1 <= v <= 256),
    Setting("autoSpeedUp", True),
    Setting("maxReassignSize", 3, validate=lambda v: 1 <= v <= 100),
    Setting("customThemeMode", "System", validate=lambda v: v in _THEME_MODES),
    Setting("checkUpdateAtStartUp", True),
    Setting("autoRun", False),
    Setting("enableClipboardListener", True),
]
