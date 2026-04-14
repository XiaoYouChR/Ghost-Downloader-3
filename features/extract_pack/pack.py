from __future__ import annotations

from collections.abc import Mapping

from app.feature_pack.api import FeaturePack

from .task import ExtractPack as _ExtractPackImpl
from .task import ExtractTask
from .task import parse


class ExtractPack(_ExtractPackImpl):
    def canHandle(self, url: str) -> bool:
        return self.accepts(url)

    def canHandleTask(self, task: object) -> bool:
        return isinstance(task, ExtractTask) and getattr(task, "packId", "") == "extract_pack"

    async def createTaskFromPayload(self, payload: Mapping[str, object]) -> ExtractTask | None:
        return await super().createTaskFromPayload(payload)

    async def parse(self, payload: Mapping[str, object]) -> ExtractTask:
        return await parse(payload)


__all__ = ["ExtractPack"]
