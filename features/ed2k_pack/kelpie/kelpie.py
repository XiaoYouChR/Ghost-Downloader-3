import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from dataclasses import dataclass, field
from itertools import count
from pathlib import Path
from typing import Any

from .errors import Error, ErrorCode
from .models import Link, Network, Progress, Settings, Source

PROTOCOL = 1
MIN_ENGINE_VERSION = (0, 2, 0)
CLOSE_TIMEOUT = 15
HANDSHAKE_TIMEOUT = 30
STREAM_LIMIT = 4 * 1024 * 1024
VERSION_PATTERN = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")

logger = logging.getLogger(__name__)


class Run:
    def __init__(self, id: int) -> None:
        self._id = id
        # Only the newest Progress: a slow consumer skips the stale ones.
        self._progress: Progress | None = None
        # Kept apart from _error, because a normal end has no error.
        self._isEnded = False
        self._error: BaseException | None = None
        # An Event, not a queue: repeated set() calls collapse into one wake-up.
        self._changed = asyncio.Event()

    async def __aiter__(self) -> AsyncIterator[Progress]:
        while True:
            await self._changed.wait()
            self._changed.clear()
            progress, self._progress = self._progress, None
            if progress is not None:
                yield progress
            if self._isEnded:
                if self._error is not None:
                    raise self._error
                return

    def _setProgress(self, progress: Progress) -> None:
        if self._isEnded:
            return
        self._progress = progress
        self._changed.set()

    def _setEnded(self, error: BaseException | None) -> None:
        if self._isEnded:
            return
        self._isEnded = True
        self._error = error
        self._changed.set()

    def _cancel(self) -> None:
        # Ended by someone other than its caller: a normal end would read as a
        # finished download, so the caller sees a cancellation instead.
        if not self._isEnded:
            self._progress = None
            self._setEnded(asyncio.CancelledError())


@dataclass
class EngineProcess:
    process: asyncio.subprocess.Process
    # The Runs this process still owes an `ended`, by run id because a stopped
    # download must not end the seed that follows it. Whoever pops a Run ends
    # it, and the `ended` that follows finds no route.
    routes: dict[int, Run] = field(default_factory=dict)


class Kelpie:
    def __init__(
        self,
        executable: Callable[[], Path],
        dataFolder: Path,
        settings: Callable[[], Settings],
        onNetwork: Callable[[Network | None], None] = lambda _: None,
    ) -> None:
        self._executable = executable
        self._dataFolder = dataFolder
        self._settings = settings
        self._onNetwork = onNetwork
        # None again once the process exits: only the next call starts another.
        self._engine: EngineProcess | None = None
        # Callers that arrive during a start wait for it instead of starting
        # a second Engine Process.
        self._starting: asyncio.Task[None] | None = None
        # By hash and across Engine Process restarts: a Transfer has one open
        # Run even while no Engine Process runs.
        self._runs: dict[str, Run] = {}
        # Never reused, so an id stays unique within every Engine Process.
        self._runIds = count(1)
        # The event loop keeps only weak references to tasks, and close() waits
        # for them.
        self._tasks: set[asyncio.Task[None]] = set()

    def runDownload(self, link: Link, file: Path) -> AbstractAsyncContextManager[Run]:
        return self._run("download", link, file)

    def runSeed(self, link: Link, file: Path) -> AbstractAsyncContextManager[Run]:
        return self._run("seed", link, file)

    def update(self) -> None:
        if self._engine is not None:
            send(self._engine.process, {"type": "update", **toMessageFields(self._settings())})

    def isActive(self, hash: str) -> bool:
        return hash in self._runs

    async def remove(self, hash: str) -> None:
        run = self._runs.get(hash)
        engine = self._engine
        if run is not None and engine is not None and engine.routes.pop(run._id, None) is not None:
            run._cancel()
        await self._start()
        if self._engine is not None:
            send(self._engine.process, {"type": "remove", "hash": hash})

    async def close(self) -> None:
        if self._starting is not None:
            with suppress(Error):
                await asyncio.shield(self._starting)
        engine = self._engine
        if engine is None:
            return
        self._engine = None
        for run in engine.routes.values():
            run._cancel()
        process = engine.process
        process.stdin.close()
        try:
            async with asyncio.timeout(CLOSE_TIMEOUT):
                await process.wait()
        except TimeoutError:
            process.kill()
            await process.wait()
        await asyncio.gather(*self._tasks)

    @asynccontextmanager
    async def _run(self, mode: str, link: Link, file: Path) -> AsyncIterator[Run]:
        if link.hash in self._runs:
            raise Error(ErrorCode.TRANSFER_BUSY, f"a Run is already open for {link.hash}")
        run = Run(next(self._runIds))
        self._runs[link.hash] = run
        try:
            try:
                await self._start()
            except Error as error:
                run._setEnded(error)
            else:
                if self._engine is None:
                    run._setEnded(Error(ErrorCode.ENGINE_EXITED, "Engine Process exited"))
                else:
                    self._engine.routes[run._id] = run
                    send(
                        self._engine.process,
                        {
                            "type": "run",
                            "run": run._id,
                            "mode": mode,
                            "link": str(link),
                            "file": str(file),
                        },
                    )
            yield run
        finally:
            del self._runs[link.hash]
            engine = self._engine
            if engine is not None and engine.routes.pop(run._id, None) is not None:
                send(engine.process, {"type": "stop", "run": run._id})

    async def _start(self) -> None:
        if self._engine is not None:
            return
        if self._starting is None:
            self._starting = asyncio.create_task(self._createProcess())
        await asyncio.shield(self._starting)

    async def _createProcess(self) -> None:
        try:
            executable = self._executable()
            settings = self._settings()
            try:
                process = await asyncio.create_subprocess_exec(
                    executable,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    limit=STREAM_LIMIT,
                )
            except OSError as error:
                raise Error(
                    ErrorCode.START_FAILED, f"cannot start {executable}: {error}"
                ) from error
            send(process, buildHello(self._dataFolder, settings))
            ready: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            task = asyncio.create_task(self._supervise(process, ready))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            await ready
            # An update() during the handshake found no Engine Process.
            if self._settings() != settings:
                self.update()
        finally:
            self._starting = None

    async def _supervise(
        self, process: asyncio.subprocess.Process, ready: asyncio.Future[None]
    ) -> None:
        lastStderrLine = asyncio.create_task(parseLastLine(process.stderr))
        try:
            isReady = await runHandshake(process)
        except Error as error:
            process.stdin.close()
            await lastStderrLine
            await process.wait()
            ready.set_exception(error)
            return
        engine = EngineProcess(process)
        if isReady:
            self._engine = engine
            ready.set_result(None)
            while line := await process.stdout.readline():
                network = onMessage(engine, line)
                # After close() the old process may still report until it
                # exits, and a new one may already run.
                if network is not None and self._engine is engine:
                    self._onNetwork(network)
        lastLine = await lastStderrLine
        exitCode = await process.wait()
        reason = lastLine if lastLine is not None else f"exit code {exitCode}"
        if not isReady:
            ready.set_exception(
                Error(ErrorCode.START_FAILED, f"Engine Process exited during startup: {reason}")
            )
            return
        # Unless a newer Engine Process already runs, none does now.
        if self._engine is engine or self._engine is None:
            self._engine = None
            self._onNetwork(None)
        exited = Error(ErrorCode.ENGINE_EXITED, reason)
        for run in engine.routes.values():
            run._setEnded(exited)


def onMessage(engine: EngineProcess, line: bytes) -> Network | None:
    try:
        message = json.loads(line)
        match message.get("type"):
            case "progress":
                run = engine.routes.get(message["run"])
                if run is not None:
                    run._setProgress(parseProgress(message))
            case "ended":
                run = engine.routes.pop(message["run"], None)
                if run is not None:
                    run._setEnded(parseError(message["error"]))
            case "network":
                return parseNetwork(message)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        logger.warning("ignored invalid Engine Process message %r: %s", line, error)
    return None


def send(process: asyncio.subprocess.Process, message: dict[str, Any]) -> None:
    process.stdin.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")


def buildHello(dataFolder: Path, settings: Settings) -> dict[str, Any]:
    return {
        "type": "hello",
        "protocol": PROTOCOL,
        "dataFolder": str(dataFolder),
        **toMessageFields(settings),
    }


def toMessageFields(settings: Settings) -> dict[str, Any]:
    return {
        "settings": {
            "port": settings.port,
            "enableKad": settings.enableKad,
            "enableUpnp": settings.enableUpnp,
            "serverLists": [str(path) for path in settings.serverLists],
            "nodeLists": [str(path) for path in settings.nodeLists],
            "traceFile": str(settings.traceFile) if settings.traceFile is not None else "",
            "proxy": settings.proxy,
        },
        "rateLimits": {"download": settings.downloadRateLimit, "upload": settings.uploadRateLimit},
    }


async def runHandshake(process: asyncio.subprocess.Process) -> bool:
    try:
        async with asyncio.timeout(HANDSHAKE_TIMEOUT):
            line = await process.stdout.readline()
    except TimeoutError:
        process.kill()
        raise Error(
            ErrorCode.START_FAILED,
            f"Engine Process did not answer hello within {HANDSHAKE_TIMEOUT} s",
        ) from None
    if not line:
        return False
    parseHandshake(line)
    return True


def parseHandshake(line: bytes) -> None:
    try:
        message = json.loads(line)
        if message["type"] == "failed":
            raise Error(ErrorCode.START_FAILED, message["error"]["message"])
        if message["type"] != "ready":
            raise Error(ErrorCode.START_FAILED, f"unexpected handshake: {line!r}")
        version = message["version"]
    except (ValueError, KeyError, TypeError) as error:
        raise Error(ErrorCode.START_FAILED, f"invalid handshake {line!r}: {error}") from error
    if matchOutdated(version):
        required = ".".join(map(str, MIN_ENGINE_VERSION))
        raise Error(ErrorCode.OUTDATED, f"Engine Process {version} is older than v{required}")


def matchOutdated(version: str) -> bool:
    parsed = VERSION_PATTERN.match(version)
    return parsed is not None and tuple(map(int, parsed.groups())) < MIN_ENGINE_VERSION


def parseProgress(message: dict[str, Any]) -> Progress:
    return Progress(
        hash=message["hash"],
        size=message["size"],
        received=message["received"],
        downloadRate=message["downloadRate"],
        uploadRate=message["uploadRate"],
        uploaded=message["uploaded"],
        peers=message["peers"],
        activePeers=message["activePeers"],
        heldSources=message["heldSources"],
        heldUntil=message["heldUntil"],
        sources=tuple(parseSource(source) for source in message["sources"]),
    )


def parseSource(message: dict[str, Any]) -> Source:
    return Source(
        address=message["address"],
        software=message["software"],
        status=message["status"],
        rank=message["rank"],
        downloadRate=message["downloadRate"],
        channel=message["channel"],
    )


def parseNetwork(message: dict[str, Any]) -> Network:
    return Network(
        isServerConnected=message["isServerConnected"],
        isHighId=message["isHighId"],
        isKadFirewalled=message["isKadFirewalled"],
        kadNodes=message["kadNodes"],
        isBehindCarrierNat=message["isBehindCarrierNat"],
        proxyIssue=message["proxyIssue"],
    )


def parseError(error: dict[str, Any] | None) -> Error | None:
    if error is None:
        return None
    try:
        code = ErrorCode(error["code"])
    except ValueError:
        code = ErrorCode.INTERNAL
    return Error(code, error["message"])


async def parseLastLine(stream: asyncio.StreamReader) -> str | None:
    lastLine = None
    while line := await stream.readline():
        lastLine = line.decode(errors="replace").rstrip()
    return lastLine
