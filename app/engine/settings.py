from PySide6.QtCore import QStandardPaths

from app.engine.config import Config, Setting

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


def makeCfgBackedConfig() -> Config:
    """迁移共存期的引擎配置：从旧 cfg 播种现值 + 改动同步回 cfg（packs 仍读 cfg、cfg 负责落盘）。
    引擎本身只认这个注入的 Config、不碰 cfg；Android/phase2 时换成 Config 自管文件、彻底去掉 cfg。"""
    from app.supports.config import cfg

    config = Config(GLOBAL_SETTINGS)
    config.seed({setting.key: getattr(cfg, setting.key).value for setting in GLOBAL_SETTINGS})
    config.changed.connect(lambda key: setattr(getattr(cfg, key), "value", config.value(key)))
    return config
