from collections.abc import Callable

from app.protocol.message import Command, Event


class MemoryLink:
    """gui 和 engine 之间的连线。同进程直送；以后换 socket 只改这一个类。"""

    def __init__(self) -> None:
        self._engine: Callable[[Command], None] | None = None
        self._gui: Callable[[Event], None] | None = None

    def connect(self, engine: Callable[[Command], None], gui: Callable[[Event], None]) -> None:
        self._engine = engine
        self._gui = gui

    def toEngine(self, command: Command) -> None:
        self._engine(command)

    def toGui(self, event: Event) -> None:
        self._gui(event)
