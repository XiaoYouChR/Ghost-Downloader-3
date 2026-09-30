from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from app.models.task import Task, TaskFile, TaskStatus, TaskStep
from app.services.task_service import NameConflictChoice, TaskStore


@dataclass(kw_only=True)
class ProductStep(TaskStep):
    stepIndex: int = 0

    @property
    def outputPath(self) -> str:
        return self.task.outputPath

    content: bytes = b"product"

    async def run(self, reportSpeed, waitForSpeedLimit):
        Path(self.outputPath).write_bytes(self.content)


@dataclass(kw_only=True)
class SideFileStep(TaskStep):
    stepIndex: int = 1
    suffix: str = "en.srt"

    @property
    def outputPath(self) -> str:
        return str(self.task.outputFolder / f"{Path(self.task.name).stem}.{self.suffix}")

    async def run(self, reportSpeed, waitForSpeedLimit):
        Path(self.outputPath).write_bytes(b"subtitle")


def makeTask(folder: Path, name: str = "a.zip", steps: list[TaskStep] | None = None) -> Task:
    return Task(
        name=name, url="http://test", packId="test",
        outputFolder=folder, steps=steps or [ProductStep()],
    )


def holdNames(task: Task, choice: NameConflictChoice = NameConflictChoice.KEEP_BOTH):
    return TaskStore(deleteRecoverably=lambda path: False).add(task, choice)


def test_adding_holds_name_with_empty_file(tmp_path: Path):
    task = makeTask(tmp_path)

    holdNames(task)

    assert (tmp_path / "a.zip").read_bytes() == b""


def test_adding_holds_folder_for_task_with_several_files(tmp_path: Path):
    task = makeTask(tmp_path, name="repo")
    task.files = [TaskFile(index=0, relativePath="weights.bin"), TaskFile(index=1, relativePath="config.json")]

    holdNames(task)

    assert (tmp_path / "repo").is_dir()
    assert list((tmp_path / "repo").iterdir()) == []


def test_single_selectable_file_is_saved_as_the_task_itself(tmp_path: Path):
    task = makeTask(tmp_path, name="a.iso")
    task.files = [TaskFile(index=0, relativePath="dir/a.iso")]

    holdNames(task)

    assert (tmp_path / "a.iso").read_bytes() == b""
    assert task.toFilePath(0) == tmp_path / "a.iso"


def test_adding_holds_side_files_with_product(tmp_path: Path):
    task = makeTask(tmp_path, name="a.mp4", steps=[ProductStep(), SideFileStep()])

    holdNames(task)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.en.srt", "a.mp4"]


def test_adding_creates_nothing_when_a_side_file_is_taken(tmp_path: Path):
    (tmp_path / "a.en.srt").write_bytes(b"mine")
    task = makeTask(tmp_path, name="a.mp4", steps=[ProductStep(), SideFileStep()])

    assert holdNames(task, NameConflictChoice.ASK) is None
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.en.srt"]
    assert (tmp_path / "a.en.srt").read_bytes() == b"mine"


async def noSpeed(_):
    pass


async def noLimit():
    pass


async def runTask(task: Task) -> None:
    task.setStatus(TaskStatus.RUNNING)
    await task.run(noSpeed, noLimit)


async def test_run_writes_product_onto_placeholder(tmp_path: Path):
    task = makeTask(tmp_path)
    holdNames(task)

    await runTask(task)

    assert (tmp_path / "a.zip").read_bytes() == b"product"
    assert task.status == TaskStatus.COMPLETED
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.zip"]


async def test_run_keeps_empty_product(tmp_path: Path):
    task = makeTask(tmp_path, steps=[ProductStep(content=b"")])
    holdNames(task)

    await runTask(task)

    assert (tmp_path / "a.zip").read_bytes() == b""


@dataclass(kw_only=True)
class IntermediateStep(TaskStep):
    stepIndex: int = 0

    @property
    def outputPath(self) -> str:
        return str(self.task.partPath / "a.video.mp4")

    async def run(self, reportSpeed, waitForSpeedLimit):
        Path(self.outputPath).write_bytes(b"video")


@dataclass(kw_only=True)
class MergeStep(ProductStep):
    stepIndex: int = 1

    async def run(self, reportSpeed, waitForSpeedLimit):
        video = self.task.partPath / "a.video.mp4"
        Path(self.outputPath).write_bytes(video.read_bytes() + b"+audio")


async def test_run_keeps_intermediate_files_beside_product_until_done(tmp_path: Path):
    task = makeTask(tmp_path, name="a.mp4", steps=[IntermediateStep(), MergeStep()])
    holdNames(task)

    await runTask(task)

    assert task.partPath == tmp_path / "a.mp4.ghd"
    assert (tmp_path / "a.mp4").read_bytes() == b"video+audio"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.mp4"]


@dataclass(kw_only=True)
class ResumingIntermediateStep(IntermediateStep):
    async def run(self, reportSpeed, waitForSpeedLimit):
        path = Path(self.outputPath)
        path.write_bytes(path.read_bytes() + b"+rest")
        Path(f"{path}.ghd").unlink()


async def test_run_resumes_paused_intermediate_step(tmp_path: Path):
    task = makeTask(tmp_path, name="a.mp4", steps=[ResumingIntermediateStep(), MergeStep()])
    holdNames(task)
    video = task.partPath / "a.video.mp4"
    video.parent.mkdir()
    video.write_bytes(b"half")
    Path(f"{video}.ghd").write_bytes(b"offsets")

    await runTask(task)

    assert (tmp_path / "a.mp4").read_bytes() == b"half+rest+audio"


async def test_deleteFiles_empties_products_but_keeps_placeholders(tmp_path: Path):
    (tmp_path / "a.nfo").write_bytes(b"mine")
    task = makeTask(tmp_path, name="a.mp4", steps=[ProductStep(), SideFileStep()])
    holdNames(task)
    await runTask(task)

    task.deleteFiles()

    assert (tmp_path / "a.mp4").read_bytes() == b""
    assert (tmp_path / "a.en.srt").read_bytes() == b""
    assert (tmp_path / "a.nfo").read_bytes() == b"mine"


def test_deleteFiles_deletes_part_paths_of_unfinished_task(tmp_path: Path):
    task = makeTask(tmp_path, name="a.mp4", steps=[ProductStep(), SideFileStep()])
    holdNames(task)
    (tmp_path / "a.mp4").write_bytes(b"half")
    (tmp_path / "a.mp4.ghd").write_bytes(b"offsets")

    task.deleteFiles()

    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.en.srt", "a.mp4"]
    assert (tmp_path / "a.mp4").read_bytes() == b""


def test_deletePlaceholders_releases_names_of_unfinished_task(tmp_path: Path):
    task = makeTask(tmp_path, name="a.mp4", steps=[IntermediateStep(), MergeStep(), SideFileStep()])
    holdNames(task)
    task.partPath.mkdir()
    (task.partPath / "a.video.mp4").write_bytes(b"half")
    (tmp_path / "a.en.srt").write_bytes(b"half")
    (tmp_path / "a.en.srt.ghd").write_bytes(b"offsets")

    task.deletePlaceholders()

    assert list(tmp_path.iterdir()) == []


async def test_deletePlaceholders_keeps_completed_products(tmp_path: Path):
    task = makeTask(tmp_path)
    holdNames(task)
    await runTask(task)

    task.deletePlaceholders()

    assert (tmp_path / "a.zip").read_bytes() == b"product"


@dataclass(kw_only=True)
class FileStep(TaskStep):
    isBroken: bool = False

    @property
    def outputPath(self) -> str:
        return str(self.task.toFilePath(self.fileIndex))

    async def run(self, reportSpeed, waitForSpeedLimit):
        if self.isBroken:
            Path(self.outputPath).write_bytes(b"half")
            raise OSError("server gone")
        Path(self.outputPath).write_bytes(b"file")


def makeFolderTask(folder: Path) -> Task:
    task = makeTask(folder, name="playlist", steps=[
        FileStep(stepIndex=0, fileIndex=0),
        FileStep(stepIndex=1, fileIndex=1, isBroken=True),
    ])
    task.files = [
        TaskFile(index=0, relativePath="sub/first.mp4"),
        TaskFile(index=1, relativePath="second.mp4"),
    ]
    return task


async def test_run_shows_each_finished_file_of_folder_task(tmp_path: Path):
    task = makeFolderTask(tmp_path)
    holdNames(task)

    with pytest.raises(OSError):
        await runTask(task)

    assert (tmp_path / "playlist" / "sub" / "first.mp4").read_bytes() == b"file"


async def test_deletePlaceholders_keeps_finished_files_of_unfinished_folder_task(tmp_path: Path):
    task = makeFolderTask(tmp_path)
    holdNames(task)
    with pytest.raises(OSError):
        await runTask(task)

    task.deletePlaceholders()

    assert (tmp_path / "playlist" / "sub" / "first.mp4").read_bytes() == b"file"
    assert not (tmp_path / "playlist" / "second.mp4").exists()


def test_side_file_follows_stem_of_its_product(tmp_path: Path):
    task = makeTask(tmp_path, name="playlist")
    task.files = [TaskFile(index=0, relativePath="v1.2 intro.mp4"), TaskFile(index=1, relativePath="b.mp4")]

    assert task.toSidePath(0, "en.vtt") == tmp_path / "playlist" / "v1.2 intro.en.vtt"
    assert task.toSidePath(None, "jpg") == tmp_path / "playlist.jpg"


def test_side_file_of_folder_keeps_whole_folder_name(tmp_path: Path):
    task = makeTask(tmp_path, name="Ubuntu 22.04")
    task.files = [TaskFile(index=0, relativePath="a.iso"), TaskFile(index=1, relativePath="b.iso")]

    assert task.toSidePath(None, "torrent") == tmp_path / "Ubuntu 22.04.torrent"


def test_task_without_output_file_holds_nothing(tmp_path: Path):
    task = makeTask(tmp_path, name="goed2kd 安装")
    task.hasOutputFile = False

    holdNames(task)

    assert task.placeholderPaths == []
    assert list(tmp_path.iterdir()) == []
