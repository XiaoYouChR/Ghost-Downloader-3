from __future__ import annotations

import json

from qfluentwidgets import ConfigSerializer, ConfigValidator

DEFAULT_WEB_TRACKER_SOURCE = "https://cf.trackerslist.com/best.txt"


class SourceCacheValidator(ConfigValidator):
    def validate(self, value) -> bool:
        if not isinstance(value, dict):
            return False
        return all(
            isinstance(url, str) and isinstance(trackers, list)
            and all(isinstance(t, str) for t in trackers)
            for url, trackers in value.items()
        )

    def correct(self, value) -> dict:
        return value if self.validate(value) else {}


class SourceCacheSerializer(ConfigSerializer):
    def serialize(self, value: dict[str, list[str]]) -> str:
        return json.dumps(value, ensure_ascii=False)

    def deserialize(self, value: str) -> dict[str, list[str]]:
        try:
            result = json.loads(value)
        except (ValueError, TypeError):
            return {}
        if not isinstance(result, dict):
            return {}
        return {
            url: list(trackers)
            for url, trackers in result.items()
            if isinstance(url, str) and isinstance(trackers, list)
        }
