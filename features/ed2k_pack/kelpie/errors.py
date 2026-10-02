from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_LINK = "INVALID_LINK"
    OUTPUT_EXISTS = "OUTPUT_EXISTS"
    TRANSFER_BUSY = "TRANSFER_BUSY"
    DISK_FULL = "DISK_FULL"
    FILE_ERROR = "FILE_ERROR"
    OUTDATED = "OUTDATED"
    START_FAILED = "START_FAILED"
    ENGINE_EXITED = "ENGINE_EXITED"
    INTERNAL = "INTERNAL"


class Error(Exception):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
