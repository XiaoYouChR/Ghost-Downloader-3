from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TaskDestination:
    categoryId: str
    targetFolder: str


def buildDestination(task, categories, defaultFolder: str, isEnabled: bool) -> TaskDestination:
    categoryId = task.category
    if isEnabled and categoryId is None:
        categoryId = categories.categoryOf(task)
    if not categories.categoryById(categoryId or ""):
        categoryId = ""
    folder = str(task.outputFolder)
    if isEnabled and categoryId and Path(folder) == Path(defaultFolder):
        folder = categories.folderOf(categoryId) or folder
    return TaskDestination(categoryId or "", folder)
