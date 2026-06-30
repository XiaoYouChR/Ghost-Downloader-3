import asyncio
import subprocess
import sys
import threading


def setupHiddenSubprocess() -> None:
    if sys.platform != "win32":
        return
    asyncio.create_subprocess_exec = _createHiddenSubprocess


async def _createHiddenSubprocess(program, *args, stdin=None, stdout=None, stderr=None,
                                  cwd=None, env=None) -> "_HiddenProcess":
    startupInfo = subprocess.STARTUPINFO()
    startupInfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupInfo.wShowWindow = subprocess.SW_HIDE

    proc = subprocess.Popen(
        [program, *args],
        stdin=stdin, stdout=stdout, stderr=stderr,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        startupinfo=startupInfo,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return _HiddenProcess(proc)


class _HiddenProcess:
    def __init__(self, proc: subprocess.Popen):
        self._proc = proc
        self._loop = asyncio.get_running_loop()
        self.stdout = self._openReader(proc.stdout) if proc.stdout is not None else None
        self.stderr = self._openReader(proc.stderr) if proc.stderr is not None else None

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

    def _openReader(self, pipe) -> asyncio.StreamReader:
        reader = asyncio.StreamReader()
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
