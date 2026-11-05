from app.config.cfg import ConfigItem, BoolValidator
from app.models.pack import PackConfig


class WrappedLinkConfig(PackConfig):
    associateUriSchemes = ConfigItem("WrappedLink", "AssociateUriSchemes", False, BoolValidator())


wrappedLinkConfig = WrappedLinkConfig()
