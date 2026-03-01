from dataclasses import field, dataclass

from app.bases.interfaces import Worker
from app.bases.models import Task, TaskStage
from app.supports.config import DEFAULT_HEADERS


class HttpTaskStage(TaskStage):
    ...

@dataclass
class HttpTask(Task):

    url: str
    fileSize: int
    headers: dict = field(default_factory=DEFAULT_HEADERS.copy)

class HttpWorker(Worker):
    ...
