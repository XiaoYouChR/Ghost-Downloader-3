from app.bases.models import Task
from app.services.task_service import taskService


class Store:
    """任务持久化边界，包 taskService（Memory.log）。
    单独成模块让 engine.py 不直接拖 taskService；测试注入 fake 替掉文件 I/O。"""

    def load(self) -> list[Task]:
        taskService.load()
        return list(taskService.tasks.values())

    def add(self, task: Task) -> None:
        taskService.add(task)

    def remove(self, task: Task) -> None:
        taskService.remove(task)
