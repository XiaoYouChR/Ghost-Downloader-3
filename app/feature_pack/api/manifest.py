"""Feature Pack manifest data model and loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from collections.abc import Mapping
from typing import cast


@dataclass(frozen=True, slots=True, kw_only=True)
class Manifest:
    """Readonly Python view of a pack's ``manifest.toml`` metadata."""

    id: str
    name: str
    version: str
    api: int
    entry: str = "pack.py"
    dependencies: tuple[str, ...] = ()
    schemes: tuple[str, ...] = ()
    tasks: tuple[str, ...] = ()
    stages: tuple[str, ...] = ()


class ManifestError(ValueError):
    """Stable manifest loading error with machine-readable failure details."""

    manifestPath: Path
    code: str
    reason: str
    field: str | None

    def __init__(
        self,
        *,
        manifestPath: Path,
        code: str,
        reason: str,
        field: str | None = None,
    ) -> None:
        self.manifestPath = manifestPath
        self.code = code
        self.reason = reason
        self.field = field
        if field is None:
            message = f"{manifestPath}: [{code}] {reason}"
        else:
            message = f"{manifestPath}: [{code}] {field}: {reason}"
        super().__init__(message)


def loadManifest(manifestPath: str | Path) -> Manifest:
    """Load and validate a ``manifest.toml`` file."""

    resolvedPath = Path(manifestPath)
    try:
        with resolvedPath.open("rb") as stream:
            document = tomllib.load(stream)
    except FileNotFoundError as error:
        raise ManifestError(
            manifestPath=resolvedPath,
            code="missing-file",
            reason="manifest.toml 文件不存在",
        ) from error
    except tomllib.TOMLDecodeError as error:
        raise ManifestError(
            manifestPath=resolvedPath,
            code="invalid-toml",
            reason=str(error),
        ) from error
    except OSError as error:
        raise ManifestError(
            manifestPath=resolvedPath,
            code="read-failed",
            reason=str(error),
        ) from error

    return parseManifest(document, manifestPath=resolvedPath)


def parseManifest(document: object, *, manifestPath: str | Path) -> Manifest:
    """Validate a parsed manifest document and return the readonly model."""

    resolvedPath = Path(manifestPath)
    if not isinstance(document, dict):
        raise ManifestError(
            manifestPath=resolvedPath,
            code="invalid-document",
            reason="manifest 根对象必须是 TOML table",
        )
    documentData = _normalizeMapping(cast(dict[object, object], document))

    packSection = documentData.get("pack")
    if not isinstance(packSection, dict):
        raise ManifestError(
            manifestPath=resolvedPath,
            code="missing-pack-section",
            reason="manifest 必须包含 [pack] 节",
        )
    packData = _normalizeMapping(cast(dict[object, object], packSection))

    return Manifest(
        id=_readRequiredString(packData, "id", manifestPath=resolvedPath),
        name=_readRequiredString(packData, "name", manifestPath=resolvedPath),
        version=_readRequiredString(packData, "version", manifestPath=resolvedPath),
        api=_readRequiredInt(packData, "api", manifestPath=resolvedPath),
        entry=_readOptionalString(
            packData,
            "entry",
            manifestPath=resolvedPath,
            default="pack.py",
        ),
        dependencies=_readStringTuple(
            packData,
            "dependencies",
            manifestPath=resolvedPath,
        ),
        schemes=_readStringTuple(
            packData,
            "schemes",
            manifestPath=resolvedPath,
        ),
        tasks=_readStringTuple(
            packData,
            "tasks",
            manifestPath=resolvedPath,
        ),
        stages=_readStringTuple(
            packData,
            "stages",
            manifestPath=resolvedPath,
        ),
    )


def _normalizeMapping(data: dict[object, object]) -> dict[str, object]:
    normalizedData: dict[str, object] = {}
    for key, value in data.items():
        if isinstance(key, str):
            normalizedData[key] = value
    return normalizedData


def _readRequiredString(
    data: Mapping[str, object],
    fieldName: str,
    *,
    manifestPath: Path,
) -> str:
    if fieldName not in data:
        raise ManifestError(
            manifestPath=manifestPath,
            code="missing-field",
            field=fieldName,
            reason="缺少必填字段",
        )

    value = data[fieldName]
    return _normalizeString(value, fieldName=fieldName, manifestPath=manifestPath)


def _readOptionalString(
    data: Mapping[str, object],
    fieldName: str,
    *,
    manifestPath: Path,
    default: str,
) -> str:
    if fieldName not in data:
        return default

    value = data[fieldName]
    return _normalizeString(value, fieldName=fieldName, manifestPath=manifestPath)


def _normalizeString(
    value: object,
    *,
    fieldName: str,
    manifestPath: Path,
) -> str:
    if not isinstance(value, str):
        raise ManifestError(
            manifestPath=manifestPath,
            code="invalid-field-type",
            field=fieldName,
            reason="必须是字符串",
        )

    normalizedValue = value.strip()
    if not normalizedValue:
        raise ManifestError(
            manifestPath=manifestPath,
            code="invalid-field-value",
            field=fieldName,
            reason="不能为空字符串",
        )

    return normalizedValue


def _readRequiredInt(
    data: Mapping[str, object],
    fieldName: str,
    *,
    manifestPath: Path,
) -> int:
    if fieldName not in data:
        raise ManifestError(
            manifestPath=manifestPath,
            code="missing-field",
            field=fieldName,
            reason="缺少必填字段",
        )

    value = data[fieldName]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ManifestError(
            manifestPath=manifestPath,
            code="invalid-field-type",
            field=fieldName,
            reason="必须是整数",
        )
    return value


def _readStringTuple(
    data: Mapping[str, object],
    fieldName: str,
    *,
    manifestPath: Path,
) -> tuple[str, ...]:
    if fieldName not in data:
        return ()

    value = data[fieldName]
    if not isinstance(value, list):
        raise ManifestError(
            manifestPath=manifestPath,
            code="invalid-field-type",
            field=fieldName,
            reason="必须是字符串数组",
        )
    values = cast(list[object], value)

    normalizedValues: list[str] = []
    for index, item in enumerate(values):
        if not isinstance(item, str):
            raise ManifestError(
                manifestPath=manifestPath,
                code="invalid-field-type",
                field=fieldName,
                reason=f"第 {index + 1} 项必须是字符串",
            )

        normalizedItem = item.strip()
        if not normalizedItem:
            raise ManifestError(
                manifestPath=manifestPath,
                code="invalid-field-value",
                field=fieldName,
                reason=f"第 {index + 1} 项不能为空字符串",
            )
        normalizedValues.append(normalizedItem)

    return tuple(normalizedValues)


__all__ = ["Manifest", "ManifestError", "loadManifest", "parseManifest"]
