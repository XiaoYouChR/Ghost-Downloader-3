import asyncio
import subprocess
import sys
import threading


def setupHiddenSubprocess() -> None:
    if sys.platform != "win32":
        return
    asyncio.create_subprocess_exec = _createHiddenSubprocess


async def _createHiddenSubprocess(program, *args, stdin=None, stdout=None, stderr=None,
                                  limit=2**16, **kwds) -> "_HiddenProcess":
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE

    proc = subprocess.Popen(
        [program, *args],
        stdin=stdin, stdout=stdout, stderr=stderr,
        startupinfo=si,
        creationflags=subprocess.CREATE_NO_WINDOW,
        **kwds,
    )
    return _HiddenProcess(proc, limit)


class _StdinWriter:
    __slots__ = ("_pipe",)

    def __init__(self, pipe):
        self._pipe = pipe

    def write(self, data: bytes) -> None:
        self._pipe.write(data)

    async def drain(self) -> None:
        self._pipe.flush()

    def close(self) -> None:
        self._pipe.close()

    async def wait_closed(self) -> None:
        pass


class _HiddenProcess:
    def __init__(self, proc: subprocess.Popen, limit: int):
        self._proc = proc
        self._loop = asyncio.get_running_loop()
        self.stdin = _StdinWriter(proc.stdin) if proc.stdin is not None else None
        self.stdout = self._openReader(proc.stdout, limit) if proc.stdout is not None else None
        self.stderr = self._openReader(proc.stderr, limit) if proc.stderr is not None else None

    @property
    def returncode(self) -> int | None:
        return self._proc.returncode

    async def wait(self) -> int:
        return await asyncio.to_thread(self._proc.wait)

    async def communicate(self) -> tuple[bytes | None, bytes | None]:
        stdout = await self.stdout.read() if self.stdout is not None else None
        stderr = await self.stderr.read() if self.stderr is not None else None
        await self.wait()
        return stdout, stderr

    def terminate(self) -> None:
        self._proc.terminate()

    def kill(self) -> None:
        self._proc.kill()
        self._proc.wait()

    def _openReader(self, pipe, limit: int) -> asyncio.StreamReader:
        reader = asyncio.StreamReader(limit=limit)
        threading.Thread(
            target=self._pumpPipe, args=(pipe, reader),
            name="subprocess-pipe-pump", daemon=True,
        ).start()
        return reader

    def _pumpPipe(self, pipe, reader: asyncio.StreamReader) -> None:
        try:
            while chunk := pipe.read1(65536):
                self._loop.call_soon_threadsafe(reader.feed_data, chunk)
        except (OSError, ValueError):
            pass
        finally:
            try:
                self._loop.call_soon_threadsafe(reader.feed_eof)
            except RuntimeError:
                pass
