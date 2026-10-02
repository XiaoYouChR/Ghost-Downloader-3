"""Android View adapter for ED2kPack."""
import time
from dataclasses import asdict

from app.config.cfg import cfg
from app.i18n import N
from .config import ed2kConfig
from .lists import nodeList, serverList
from .session import ed2kSession, toHeldMinutes

UI_CLASS = "com.xychr.ghostdownloader.features.ed2k_pack.Ed2kUi"


def init(pack) -> dict:
    return {"network": ed2kSession.networkChanged, "isIdle": ed2kSession.runsChanged}


def network() -> dict | None:
    network = ed2kSession.network
    return None if network is None else asdict(network)


def isIdle() -> bool:
    return ed2kSession.isIdle


async def stop() -> None:
    await ed2kSession.stop()


def taskFields(task) -> dict:
    progress = ed2kSession.progressOf(task)
    heldMinutes = toHeldMinutes(progress, int(time.time() * 1000))
    uploadRate = progress.uploadRate if progress is not None else 0
    return {
        "progressMode": "hidden" if task.isSeeding else "determinate",
        "statusText": N("TaskState", "做种中") if task.isSeeding else "",
        "secondarySpeed": uploadRate,
        "packFields": {
            "peers": None if progress is None else {"active": progress.activePeers, "total": progress.peers},
            "held": None if heldMinutes is None else {"sources": progress.heldSources, "minutes": heldMinutes},
            "shareRatio": task.shareRatioPercent,
            "seedingSeconds": task.seedingTimeSeconds,
            "uploadSpeed": uploadRate,
        },
    }


def bootstrapListByName(name: str):
    return {"servers": serverList, "nodes": nodeList}[name]


def sourcesItemByName(name: str):
    return {"servers": ed2kConfig.serverListSources, "nodes": ed2kConfig.nodeListSources}[name]


async def bootstrapListState(name: str) -> dict:
    bootstrapList = bootstrapListByName(name)
    sourcesItem = sourcesItemByName(name)
    return {
        "sources": list(sourcesItem.value),
        "defaults": list(sourcesItem.defaultValue),
        "statuses": [asdict(status) for status in bootstrapList.statuses()],
        "entryCount": bootstrapList.entryCount(),
        "isRefreshing": bootstrapList.isRefreshing,
    }


def setBootstrapListSources(name: str, sources: str):
    cfg.set(sourcesItemByName(name), list(dict.fromkeys(sources.split())))


async def refreshBootstrapList(name: str) -> dict:
    await bootstrapListByName(name).refresh()
    return await bootstrapListState(name)
