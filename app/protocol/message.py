from dataclasses import dataclass, field


@dataclass
class Command:
    """gui 让 engine 做事的消息。name 是动作名，data 是参数。"""

    name: str
    data: dict = field(default_factory=dict)


@dataclass
class Event:
    """engine 告诉 gui 发生了什么的消息。"""

    name: str
    data: dict = field(default_factory=dict)
