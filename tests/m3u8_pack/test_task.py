from __future__ import annotations

from pathlib import Path

from app.models.task import TaskStatus
from features.m3u8_pack.task import M3U8Task, M3U8TaskStep


def buildTask(name: str = "test.mp4", *, isLive: bool = False) -> M3U8Task:
    task = M3U8Task(name=name, url="http://test", fileSize=1, outputFolder=Path("."), isLive=isLive)
    task.addStep(M3U8TaskStep(stepIndex=1))
    return task


def test_set_name_replaces_manifest_suffix():
    vod = buildTask()
    vod.setName("clip.m3u8")
    assert vod.name == "clip.mp4"

    vod.setName("clip.MPD")
    assert vod.name == "clip.mp4"

    live = buildTask("live.ts", isLive=True)
    live.setName("channel.m3u8")
    assert live.name == "channel.ts"


def test_set_name_keeps_non_manifest_suffix():
    task = buildTask()
    task.setName("clip.mkv")
    assert task.name == "clip.mkv"

    task.setName("clip")
    assert task.name == "clip"


def test_load_running_live_completes_with_output(tmp_path: Path):
    target = tmp_path / "live.ts"
    target.write_bytes(b"")
    part = tmp_path / "live.ts.ghd"
    part.mkdir()

    probe = M3U8Task(name="live.ts", url="http://test", fileSize=1, outputFolder=tmp_path, isLive=True)
    probeStep = M3U8TaskStep(stepIndex=1)
    probe.addStep(probeStep)
    saveName = next(a.removeprefix("--save-name=") for a in probeStep.buildCommand("http://test") if a.startswith("--save-name="))
    (part / f"{saveName}.ts").write_bytes(b"recorded-stream")

    step = M3U8TaskStep(stepIndex=1, status=TaskStatus.RUNNING)
    task = M3U8Task(
        name="live.ts",
        url="http://test",
        fileSize=1,
        outputFolder=tmp_path,
        isLive=True,
        status=TaskStatus.RUNNING,
        steps=[step],
    )

    assert task.status == TaskStatus.COMPLETED
    assert target.read_bytes() == b"recorded-stream"
