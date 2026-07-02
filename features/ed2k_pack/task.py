from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from loguru import logger

from app.models.task import Task, TaskError, TaskStep, TaskStatus
from app.services.speed_meter import speedMeter


@dataclass(kw_only=True, eq=False)
class ED2kTask(Task):
    packId: str = "ed2k"
    fileHash: str = ""

    def reset(self) -> TaskStatus:
        self.fileHash = ""
        return super().reset()

    def deleteFiles(self):
        if self.fileHash:
            from app.services.coroutine_runner import coroutineRunner
            from .session import ed2kSession
            try:
                coroutineRunner.submit(ed2kSession.client().remove(self.fileHash, deleteFile=True))
            except Exception:
                pass
        super().deleteFiles()


@dataclass(kw_only=True)
class ED2kTaskStep(TaskStep):
    async def run(self) -> None:
        from .python_ed2k import TransferState
        from .python_ed2k.errors import ErrorCode, Error
        from .session import ed2kSession

        task: ED2kTask = self.task

        await ed2kSession.open()
        client = ed2kSession.client()

        if task.fileHash:
            await client.resume(task.fileHash)
        else:
            try:
                transfer = await client.addLink(task.url, task.outputFolder)
            except Error as e:
                if e.code != ErrorCode.TRANSFER_EXISTS:
                    raise TaskError("ED2k error: {detail}", detail=str(e)) from e
                _, _, linkHash = parseEd2kLink(task.url)
                await client.remove(linkHash, deleteFile=False)
                transfer = await client.addLink(task.url, task.outputFolder)
            task.fileHash = transfer.hash
            task.name = transfer.name or task.name

        try:
            async for snapshot in client.snapshots():
                for t in snapshot.transfers:
                    if t.hash != task.fileHash:
                        continue
                    self.receivedBytes = t.received
                    self.speed = t.downloadRate
                    speedMeter.addSpeed(t.downloadRate)
                    if t.size > 0:
                        task.fileSize = t.size
                        self.progress = min(99.9, t.received / t.size * 100)
                    if t.state == TransferState.FINISHED:
                        self.setStatus(TaskStatus.COMPLETED)
                        await client.pause(task.fileHash)
                        return
                    break
        except asyncio.CancelledError:
            if task.fileHash:
                try:
                    await ed2kSession.client().pause(task.fileHash)
                except Exception as e:
                    logger.opt(exception=e).warning("暂停 eD2k 传输失败")
            raise


@dataclass(kw_only=True)
class ED2kInstallStep(TaskStep):
    canPause = False
    binaryPath: str = ""

    async def run(self) -> None:
        path = Path(self.binaryPath)
        if not path.is_file():
            raise TaskError("Binary not found: {name}", name="goed2kd")
        if sys.platform != "win32":
            path.chmod(path.stat().st_mode | 0o755)
        self.setStatus(TaskStatus.COMPLETED)


def parseEd2kLink(link: str) -> tuple[str, int, str]:
    link = link.strip()
    if not link.lower().startswith("ed2k://"):
        raise ValueError("不是有效的 eD2k 链接")
    parts = link.strip("/").split("|")
    if len(parts) < 5 or parts[1].lower() != "file":
        raise ValueError("不支持的 eD2k 链接格式")
    name = unquote(parts[2])
    try:
        size = int(parts[3])
    except ValueError:
        size = 0
    fileHash = parts[4] if len(parts) > 4 else ""
    return name, size, fileHash
