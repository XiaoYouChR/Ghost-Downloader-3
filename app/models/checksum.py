from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from pathlib import Path

COMMON_ALGORITHMS = ("md5", "sha1", "sha256", "sha512")
SHAKE_LENGTHS = {"shake_128": 32, "shake_256": 64}
CHUNK_SIZE = 4 * 1024 * 1024


def toAlgorithms() -> list[str]:
    return sorted(hashlib.algorithms_available)


async def toChecksum(path: Path, algorithm: str, onProgress: Callable[[int], None]) -> str:
    hasher = hashlib.new(algorithm)
    size = path.stat().st_size
    done = 0
    with open(path, "rb") as f:
        while chunk := await asyncio.to_thread(f.read, CHUNK_SIZE):
            await asyncio.to_thread(hasher.update, chunk)
            done += len(chunk)
            onProgress(done * 100 // size)
    length = SHAKE_LENGTHS.get(algorithm)
    return hasher.hexdigest(length) if length else hasher.hexdigest()
