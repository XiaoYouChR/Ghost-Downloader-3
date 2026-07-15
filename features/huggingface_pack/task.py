from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.models.task import Task, TaskFile, TaskStep
from app.platform.filesystem import deletePath

from features.http_pack.task import HttpTaskStep


@dataclass(kw_only=True)
class HuggingFaceFile(TaskFile):
    downloadUrl: str = ""


@dataclass(kw_only=True)
class HuggingFaceStep(HttpTaskStep):
    fileIndex: int = -1

    @property
    def outputPath(self) -> str:
        if self.fileIndex >= 0 and self.task.files:
            for file in self.task.files:
                if file.index == self.fileIndex:
                    return str(self.task.outputFolder / self.task.name / file.relativePath)
        return super().outputPath

    def deleteFiles(self) -> None:
        path = Path(self.outputPath)
        deletePath(path)
        deletePath(Path(f"{path}.ghd"))

    @classmethod
    def fromFile(cls, file: TaskFile, task: Task) -> TaskStep:
        from app.config.cfg import cfg
        hfFile: HuggingFaceFile = file
        return cls(
            stepIndex=file.index + 1,
            url=hfFile.downloadUrl,
            fileSize=file.size,
            headers=task.steps[0].headers if task.steps else {},
            subworkerCount=cfg.preBlockNum.value,
            canUseRangeRequests=file.size > 0,
            fileIndex=file.index,
        )


@dataclass(kw_only=True, eq=False)
class HuggingFaceTask(Task):
    packId: str = "huggingface"
    canEdit = True
    fileType = HuggingFaceFile
    repoId: str = ""
    repoType: str = "model"
    revision: str = "main"

    def __post_init__(self):
        super().__post_init__()
        # 旧存档中被取消勾选的文件没有 Step，按 files 补建
        if self.files:
            existing = {getattr(s, "fileIndex", None) for s in self.steps}
            for file in self.files:
                if file.index not in existing:
                    self.addStep(HuggingFaceStep.fromFile(file, self))

    @property
    def countSelected(self) -> int:
        return sum(1 for f in self.files if f.selected) if self.files else 0

    def deleteFiles(self) -> None:
        for step in self.steps:
            step.deleteFiles()
        if self.files:
            deletePath(Path(self.outputFolder / self.name))
