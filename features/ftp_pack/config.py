from app.models.pack import PackConfig
from qfluentwidgets import ConfigItem, BoolValidator


class FtpConfig(PackConfig):
    associateUriSchemes = ConfigItem("FTP", "AssociateUriSchemes", False, BoolValidator())


ftpConfig = FtpConfig()
