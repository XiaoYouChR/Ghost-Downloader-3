from dataclasses import dataclass, field

from orjson import dumps, loads


@dataclass
class Command:
    """gui 让 engine 做事的消息。name 是动作名，data 是参数。"""

    name: str
    data: dict = field(default_factory=dict)

    def toBytes(self) -> bytes:
        return dumps({"name": self.name, "data": self.data})

    @classmethod
    def fromBytes(cls, raw: bytes) -> "Command":
        obj = loads(raw)
        return cls(obj["name"], obj.get("data", {}))


@dataclass
class Event:
    """engine 告诉 gui 发生了什么的消息。"""

    name: str
    data: dict = field(default_factory=dict)

    def toBytes(self) -> bytes:
        return dumps({"name": self.name, "data": self.data})

    @classmethod
    def fromBytes(cls, raw: bytes) -> "Event":
        obj = loads(raw)
        return cls(obj["name"], obj.get("data", {}))
