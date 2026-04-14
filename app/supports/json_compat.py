import json
from typing import Any

try:
    from orjson import dumps as _orjson_dumps, loads as _orjson_loads
except ImportError:
    _orjson_dumps = None
    _orjson_loads = None


def dumps(value: Any) -> bytes:
    if _orjson_dumps is not None:
        return _orjson_dumps(value)

    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def loads(value: Any) -> Any:
    if _orjson_loads is not None:
        return _orjson_loads(value)

    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")

    return json.loads(value)
