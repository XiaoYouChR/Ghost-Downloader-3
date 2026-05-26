from orjson import dumps, loads
from qfluentwidgets import ConfigSerializer, ConfigValidator


DEFAULT_WEB_TRACKER_SOURCE = "https://cf.trackerslist.com/best.txt"


class SourceCacheValidator(ConfigValidator):
    def validate(self, value) -> bool:
        if not isinstance(value, dict):
            return False
        for url, trackers in value.items():
            if not isinstance(url, str) or not isinstance(trackers, list):
                return False
            if not all(isinstance(tracker, str) for tracker in trackers):
                return False
        return True

    def correct(self, value) -> dict:
        return value if self.validate(value) else {}


class SourceCacheSerializer(ConfigSerializer):
    def serialize(self, value: dict[str, list[str]]) -> str:
        return dumps(value).decode("utf-8")

    def deserialize(self, value: str) -> dict[str, list[str]]:
        try:
            result = loads(value)
        except (ValueError, TypeError):
            return {}
        if not isinstance(result, dict):
            return {}
        return {
            url: list(trackers)
            for url, trackers in result.items()
            if isinstance(url, str) and isinstance(trackers, list)
        }
