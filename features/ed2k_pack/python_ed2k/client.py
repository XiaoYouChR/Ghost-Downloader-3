import asyncio
import json
from collections import deque
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any

from .errors import EngineExited, Error, ErrorCode, ProtocolError
from .models import Settings, Snapshot, Transfer, TransferState


RPC_VERSION = 1
STREAM_LIMIT = 4 * 1024 * 1024


class Client:
    def __init__(self, executable: Path, dataDir: Path) -> None:
        self._executable = executable
        self._dataDir = dataDir
        self._loop: asyncio.AbstractEventLoop | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._writeLock: asyncio.Lock | None = None
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._nextId = 1
        self._stderr: deque[str] = deque(maxlen=20)
        self._closing = False
        self._stopped = True
        self._latest: Snapshot | None = None
        self._snapshotVersion = 0
        self._snapshotCondition = asyncio.Condition()
        self._exitError: Error | None = None

    async def start(self, settings: Settings = Settings()) -> Snapshot:
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise Error(ErrorCode.INVALID_REQUEST, "Client is bound to another event loop")
        if self._process is not None and self._process.returncode is None:
            raise Error(ErrorCode.INVALID_REQUEST, "Client is already running")

        self._writeLock = asyncio.Lock()
        self._stderr.clear()
        self._closing = False
        self._latest = None
        self._exitError = None
        try:
            process = await asyncio.create_subprocess_exec(
                self._executable,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=STREAM_LIMIT,
            )
        except OSError as error:
            raise Error(ErrorCode.INVALID_REQUEST, f"cannot start goed2kd: {error}") from error
        self._process = process
        self._stopped = False
        for coroutine in (
            self._readStdout(process),
            self._readStderr(process),
            self._watchProcess(process),
        ):
            task = asyncio.create_task(coroutine)
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        try:
            current = _toSnapshot(
                await self._request(
                    "start",
                    {
                        "dataDir": str(self._dataDir),
                        "settings": _toSettings(settings),
                    },
                )
            )
        except Exception:
            await self.terminate()
            raise
        await self._publish(current)
        return current

    async def snapshot(self) -> Snapshot:
        current = _toSnapshot(await self._request("snapshot"))
        await self._publish(current)
        return current

    async def snapshots(self) -> AsyncIterator[Snapshot]:
        version = -1
        while True:
            async with self._snapshotCondition:
                await self._snapshotCondition.wait_for(
                    lambda: self._snapshotVersion != version
                    or self._exitError is not None
                    or self._stopped
                )
                if self._exitError is not None:
                    raise self._exitError
                if self._stopped and self._snapshotVersion == version:
                    return
                current = self._latest
                version = self._snapshotVersion
            if current is not None:
                yield current

    async def addLink(self, link: str, outputDir: Path) -> Transfer:
        return _toTransfer(
            await self._request("addLink", {"link": link, "outputDir": str(outputDir)})
        )

    async def pause(self, hash: str) -> Transfer:
        return _toTransfer(await self._request("pause", {"hash": hash}))

    async def resume(self, hash: str) -> Transfer:
        return _toTransfer(await self._request("resume", {"hash": hash}))

    async def remove(self, hash: str, deleteFile: bool = False) -> None:
        await self._request("remove", {"hash": hash, "deleteFile": deleteFile})

    async def close(self) -> None:
        process = self._process
        if process is None or process.returncode is not None:
            return
        self._closing = True
        await self._request("close")
        await process.wait()
        await self._setStopped(process)
        if self._process is process:
            self._process = None

    async def terminate(self) -> None:
        if self._loop is not None and self._loop is not asyncio.get_running_loop():
            raise Error(ErrorCode.INVALID_REQUEST, "Client is bound to another event loop")
        process = self._process
        if process is None or process.returncode is not None:
            return
        self._closing = True
        try:
            process.kill()
        except ProcessLookupError:
            pass
        await process.wait()
        await self._setStopped(process)
        if self._process is process:
            self._process = None

    async def _request(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        if self._loop is not asyncio.get_running_loop():
            raise Error(ErrorCode.INVALID_REQUEST, "Client is bound to another event loop")
        process = self._process
        if process is None or process.returncode is not None or process.stdin is None:
            if self._exitError is not None:
                raise self._exitError
            raise Error(ErrorCode.NOT_RUNNING, "Client is not running")
        if self._writeLock is None:
            raise Error(ErrorCode.NOT_RUNNING, "Client is not running")

        requestId = self._nextId
        self._nextId += 1
        future = asyncio.get_running_loop().create_future()
        self._pending[requestId] = future
        request = {
            "version": RPC_VERSION,
            "id": requestId,
            "method": method,
            "params": params or {},
        }
        try:
            try:
                async with self._writeLock:
                    process.stdin.write(
                        json.dumps(request, separators=(",", ":")).encode() + b"\n"
                    )
                    await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError) as error:
                returnCode = process.returncode if process.returncode is not None else -1
                raise EngineExited(returnCode, tuple(self._stderr)) from error
            return await future
        finally:
            self._pending.pop(requestId, None)

    async def _readStdout(self, process: asyncio.subprocess.Process) -> None:
        if process.stdout is None:
            return
        while line := await process.stdout.readline():
            try:
                response = json.loads(line)
                if response.get("version") != RPC_VERSION:
                    raise ProtocolError("goed2kd returned an unsupported RPC version")
                if response.get("method") == "snapshot" and "id" not in response:
                    await self._publish(_toSnapshot(response["params"]))
                    continue
                requestId = response["id"]
                future = self._pending.get(requestId)
                if future is None or future.done():
                    continue
                if failure := response.get("error"):
                    code = ErrorCode(failure["code"])
                    future.set_exception(Error(code, failure["message"]))
                else:
                    future.set_result(response.get("result"))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, ProtocolError) as error:
                protocolError = (
                    error
                    if isinstance(error, ProtocolError)
                    else ProtocolError(f"invalid goed2kd response: {error}")
                )
                if self._process is process:
                    self._exitError = protocolError
                    self._failPending(protocolError)
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                return

    async def _readStderr(self, process: asyncio.subprocess.Process) -> None:
        if process.stderr is None:
            return
        while line := await process.stderr.readline():
            if self._process is process:
                self._stderr.append(line.decode(errors="replace").rstrip())

    async def _watchProcess(self, process: asyncio.subprocess.Process) -> None:
        returnCode = await process.wait()
        await self._setStopped(process, EngineExited(returnCode, tuple(self._stderr)))

    async def _setStopped(
        self, process: asyncio.subprocess.Process, error: EngineExited | None = None
    ) -> None:
        if self._process is not process:
            return
        if error is not None:
            self._failPending(error)
            if not self._closing and self._exitError is None:
                self._exitError = error
        self._stopped = True
        async with self._snapshotCondition:
            self._snapshotCondition.notify_all()

    def _failPending(self, error: Error) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)

    async def _publish(self, snapshot: Snapshot) -> None:
        async with self._snapshotCondition:
            self._latest = snapshot
            self._snapshotVersion += 1
            self._snapshotCondition.notify_all()


def _toSnapshot(value: Any) -> Snapshot:
    try:
        return Snapshot(transfers=tuple(_toTransfer(transfer) for transfer in value["transfers"]))
    except (KeyError, TypeError, ValueError) as error:
        raise ProtocolError(f"invalid snapshot: {error}") from error


def _toSettings(settings: Settings) -> dict[str, Any]:
    return {
        "servers": settings.servers,
        "serverMetSource": settings.serverMetSource or "",
        "dhtNodes": settings.dhtNodes,
        "nodesDatSource": settings.nodesDatSource or "",
        "listenPort": settings.listenPort,
        "udpPort": settings.udpPort,
        "enableDht": settings.enableDht,
        "enableUpnp": settings.enableUpnp,
        "reconnectToServer": settings.reconnectToServer,
    }


def _toTransfer(value: Any) -> Transfer:
    try:
        return Transfer(
            hash=value["hash"],
            name=value["name"],
            path=Path(value["path"]),
            size=value["size"],
            state=TransferState(value["state"]),
            done=value["done"],
            received=value["received"],
            downloadRate=value["downloadRate"],
            uploadRate=value["uploadRate"],
            peers=value["peers"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ProtocolError(f"invalid transfer: {error}") from error
