import struct


def frame(payload: bytes) -> bytes:
    """给一帧加 4 字节大端长度前缀，便于在字节流上切分。"""
    return struct.pack("!I", len(payload)) + payload


class Unframer:
    """累积 socket 字节流，吐出其中的完整帧。"""

    def __init__(self) -> None:
        self._buffer = b""

    def feed(self, data: bytes) -> list[bytes]:
        self._buffer += data
        frames = []
        while len(self._buffer) >= 4:
            length = struct.unpack("!I", self._buffer[:4])[0]
            if len(self._buffer) < 4 + length:
                break
            frames.append(self._buffer[4 : 4 + length])
            self._buffer = self._buffer[4 + length :]
        return frames
