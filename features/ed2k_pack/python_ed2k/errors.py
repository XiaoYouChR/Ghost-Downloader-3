from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    INTERNAL = "INTERNAL"
    INVALID_LINK = "INVALID_LINK"
    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_RUNNING = "NOT_RUNNING"
    OUTPUT_EXISTS = "OUTPUT_EXISTS"
    TRANSFER_EXISTS = "TRANSFER_EXISTS"
    TRANSFER_NOT_FOUND = "TRANSFER_NOT_FOUND"


class Error(Exception):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class EngineExited(Error):
    def __init__(self, returnCode: int, stderr: tuple[str, ...]) -> None:
        message = f"goed2kd exited with code {returnCode}"
        if stderr:
            message = f"{message}: {stderr[-1]}"
        super().__init__(ErrorCode.NOT_RUNNING, message)
        self.returnCode = returnCode
        self.stderr = stderr


class ProtocolError(Error):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.INVALID_REQUEST, message)
