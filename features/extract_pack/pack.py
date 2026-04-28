from __future__ import annotations

from .task import ExtractPack as _ExtractPackImpl


class ExtractPack(_ExtractPackImpl):
    """Feature Pack entry class for the extract task implementation."""


__all__ = ["ExtractPack"]
