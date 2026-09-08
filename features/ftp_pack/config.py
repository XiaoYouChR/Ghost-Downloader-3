from app.config.cfg import ConfigItem, BoolValidator
from app.models.pack import PackConfig


class FtpConfig(PackConfig):
    associateUriSchemes = ConfigItem("FTP", "AssociateUriSchemes", False, BoolValidator())


ftpConfig = FtpConfig()
