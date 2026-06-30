def toReadableSize(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


BYTE_SCALE = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3,
               "Bps": 1, "KBps": 1024, "MBps": 1024 ** 2, "GBps": 1024 ** 3}


def toBytes(value: str, unit: str) -> int:
    return int(float(value) * BYTE_SCALE[unit])


def toReadableTime(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m{seconds % 60}s"
    else:
        remaining = seconds % 3600
        return f"{int(seconds // 3600)}h{int(remaining // 60)}m{remaining % 60}s"
