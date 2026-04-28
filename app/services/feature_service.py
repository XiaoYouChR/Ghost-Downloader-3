"""Application Feature Pack service entry point."""

from app.feature_pack.api import DefaultFeatureService


class HostFeatureService(DefaultFeatureService):
    """Concrete host service exposed as the application singleton."""


featureService = HostFeatureService()


__all__ = ["HostFeatureService", "featureService"]
