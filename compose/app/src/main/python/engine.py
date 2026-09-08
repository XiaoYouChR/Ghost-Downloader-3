"""Android composition root. Kotlin calls these functions."""
from __future__ import annotations

import asyncio
import json

from loguru import logger

_coroutineRunner = None
_taskService = None
_featureService = None
_speedMeter = None
_runtimeStatusService = None
_aria2RpcServer = None
_browserService = None
_pendingPair = None
_taskDraft = None
_draftErrors = {}
_packAdapters = {}


def _loadPacks(services):
    """按名字导入 pack，并发现各 pack 的 android.py adapter 模块。"""
    import importlib
    import sys

    from app.config.constants import VERSION
    from app.config.paths import FEATURES_DIR
    from app.loader import orderedByDependency
    from app.models.pack import PackManifest
    from app.update import parseVersion

    if str(FEATURES_DIR) not in sys.path:
        sys.path.insert(0, str(FEATURES_DIR))

    appVersion = parseVersion(VERSION)
    manifests = []
    for packDir in sorted(FEATURES_DIR.iterdir()):
        if not packDir.is_dir() or packDir.name.startswith((".", "_")):
            continue
        manifest = PackManifest.fromDir(packDir)
        if manifest is None:
            continue
        if manifest.gdMinVersion and appVersion < parseVersion(manifest.gdMinVersion):
            logger.warning("跳过 FeaturePack {}：需要 GD ≥ {}", manifest.name, manifest.gdMinVersion)
            continue
        manifests.append(manifest)

    for manifest in orderedByDependency(manifests):
        try:
            module = importlib.import_module(f"{manifest.name}.{manifest.entryPath.stem}")
            PackClass = getattr(module, manifest.className)
            pack = PackClass(services)
            pack.manifest = manifest
            _featureService._register(pack)

            try:
                adapter = importlib.import_module(f"{manifest.name}.android")
                if hasattr(adapter, 'init'):
                    adapter.init(pack)
                _packAdapters[pack.packId] = adapter
            except ImportError:
                pass

            logger.success("加载 FeaturePack: {}", manifest.name)
        except Exception as e:
            logger.opt(exception=e).error("加载 FeaturePack 失败: {}", manifest.name)


def start(dataDir: str):
    global _coroutineRunner, _taskService, _featureService, _speedMeter
    global _runtimeStatusService, _taskDraft, _aria2RpcServer, _browserService

    from app.config import paths
    paths.init(dataDir)
    from app.config.paths import APP_DATA_DIR
    from app.config.cfg import cfg

    logger.add(f"{APP_DATA_DIR}/GhostDownloader.log", rotation="512 KB", retention=3)
    cfg.load(f"{APP_DATA_DIR}/UserConfig.json")

    from app.services.coroutine_runner import CoroutineRunner
    from app.services.category_service import CategoryService
    from app.services.speed_meter import SpeedMeter

    loop = asyncio.new_event_loop()
    _coroutineRunner = CoroutineRunner(
        dispatcher=loop.call_soon_threadsafe,
        isAlive=None,
        loop=loop,
    )
    categoryService = CategoryService()
    _speedMeter = SpeedMeter(_coroutineRunner)

    from app.services.task_service import TaskService
    from app.services.feature_service import FeatureService
    from app.services.runtime_status import RuntimeStatusService

    from app.signal import BoundSignal

    class _NullFileWatcher:
        fileChanged = BoundSignal()
        def addPath(self, _): pass
        def removePath(self, _): pass

    _taskService = TaskService(_coroutineRunner, categoryService, _speedMeter, fileWatcher=_NullFileWatcher())
    _runtimeStatusService = RuntimeStatusService(_coroutineRunner)
    _featureService = FeatureService(
        _taskService, categoryService, _coroutineRunner, _runtimeStatusService,
    )

    from app.models.pack import PackServices

    _loadPacks(PackServices(
        coroutineRunner=_coroutineRunner,
        speedMeter=_speedMeter,
    ))

    cfg.load(f"{APP_DATA_DIR}/UserConfig.json")

    from app.services.task_draft import TaskDraft

    _taskDraft = TaskDraft(_coroutineRunner, _featureService)
    _taskDraft.taskConfirmed.connect(_taskService.add)
    _taskDraft.parseFailed.connect(_onParseFailed)

    from app.services.aria2_rpc import Aria2RpcServer
    from app.services.browser_service import BrowserService

    _aria2RpcServer = Aria2RpcServer(
        _coroutineRunner, parse=_featureService.parse, addTask=_taskService.add)
    cfg.isAria2RpcEnabled.valueChanged.connect(_aria2RpcServer.setEnabled)
    cfg.aria2RpcPort.valueChanged.connect(_onAria2RpcPortChanged)

    _browserService = BrowserService(
        _coroutineRunner, _taskService, parse=_featureService.parse, loadCrx=None)
    _browserService.pairRequested.connect(_onBrowserPairRequested)
    cfg.isBrowserExtensionEnabled.valueChanged.connect(_browserService.setEnabled)
    cfg.browserExtensionPort.valueChanged.connect(_onBrowserPortChanged)

    _coroutineRunner.start()
    if cfg.isAria2RpcEnabled.value:
        _aria2RpcServer.start()
    if cfg.isBrowserExtensionEnabled.value:
        _browserService.start()
    _taskService.resumeSaved()
    _featureService.activate()
    logger.info("Engine started, dataDir={}", dataDir)


def _onAria2RpcPortChanged(_port):
    from app.config.cfg import cfg
    if cfg.isAria2RpcEnabled.value:
        _aria2RpcServer.stop()
        _aria2RpcServer.start()


def _onBrowserPortChanged(_port):
    from app.config.cfg import cfg
    if cfg.isBrowserExtensionEnabled.value:
        _browserService.stop()
        _browserService.start()


def stop():
    if _taskService is None:
        return
    _aria2RpcServer.stop()
    _browserService.stop()
    _taskService.stop()
    _taskService.flush()
    _speedMeter.stop()
    _featureService.deactivate()
    _coroutineRunner.stop()
    logger.info("Engine stopped")


# ---- Pack Adapter (generic, pack-agnostic) ----

def packAdapter(packId: str):
    return _packAdapters.get(packId)


def packState(packId: str, name: str) -> str:
    adapter = _packAdapters.get(packId)
    fn = getattr(adapter, name, None) if adapter else None
    return json.dumps(fn(), ensure_ascii=False) if fn else "{}"


def requestPack(packId: str, action: str, *args):
    adapter = _packAdapters.get(packId)
    fn = getattr(adapter, action, None) if adapter else None
    if fn:
        fn(*args)


# ---- Settings ----

def settings() -> str:
    from app.config.cfg import cfg
    return json.dumps({name: item.value for name, item in cfg.byName.items()}, ensure_ascii=False)


def setSetting(name: str, value):
    from app.config.cfg import cfg
    cfg.set(cfg.byName[name], value)


# ---- Draft ----

def parse(urls: str):
    from app.config.cfg import currentHeaders

    _draftErrors.clear()
    _taskDraft.setBaseOptions({"headers": currentHeaders()})
    _taskDraft.setUrls([u.strip() for u in urls.splitlines() if u.strip()])


def draft() -> str:
    result = []
    for url in _taskDraft.urls():
        task = _taskDraft.taskByUrl(url)
        error = _draftErrors.get(url)
        result.append({
            "url": url,
            "isParsing": task is None and error is None,
            "name": "" if task is None else task.name,
            "fileSize": 0 if task is None else task.fileSize,
            "files": [] if task is None or not task.files else [
                {
                    "index": f.index,
                    "path": f.relativePath,
                    "size": f.size,
                    "isSelected": f.selected,
                }
                for f in task.files
            ],
            "error": None if error is None else {
                "message": error.message,
                "params": {k: str(v) for k, v in error.params.items()},
            },
            **_draftFields(task),
        })
    return json.dumps(result, ensure_ascii=False)


def _draftFields(task) -> dict:
    if task is None:
        return {}
    adapter = _packAdapters.get(task.packId)
    return adapter.draftFields(task) if adapter and hasattr(adapter, 'draftFields') else {}


def setDraftName(url: str, name: str):
    task = _taskDraft.taskByUrl(url)
    if task:
        task.name = name


def setDraftSelection(url: str, indexes: str):
    task = _taskDraft.taskByUrl(url)
    if task:
        task.setSelection([int(i) for i in indexes.split(",") if i])


def setDraft(url: str, action: str, *args):
    task = _taskDraft.taskByUrl(url)
    if not task:
        return
    adapter = _packAdapters.get(task.packId)
    fn = getattr(adapter, action, None) if adapter else None
    if fn:
        fn(task, *args)


def confirmDraft():
    _taskDraft.confirm()
    _draftErrors.clear()


def clearDraft():
    _taskDraft.clear()
    _draftErrors.clear()


def _onParseFailed(url, error):
    _draftErrors[url] = error


# ---- Tasks ----

def tasks() -> str:
    result = []
    for t in _taskService.tasks:
        progress, speed, received = t.currentSnapshot()
        error = t.lastError
        result.append({
            "id": t.taskId,
            "name": t.name,
            "progress": progress,
            "speed": speed,
            "received": received,
            "status": t.status.name,
            "fileSize": t.fileSize,
            "fileCount": len(t.files) if t.files else 0,
            "error": None if error is None else {
                "message": error.message,
                "params": {k: str(v) for k, v in error.params.items()},
            },
            **_packFields(t),
        })
    return json.dumps(result, ensure_ascii=False)


def _packFields(task) -> dict:
    adapter = _packAdapters.get(task.packId)
    return adapter.taskFields(task) if adapter and hasattr(adapter, 'taskFields') else {}


def pause(taskId: str):
    task = _taskService.taskById(taskId)
    if task:
        _taskService.pause(task)


def resume(taskId: str):
    task = _taskService.taskById(taskId)
    if task:
        _taskService.start(task)


def remove(taskId: str):
    from app.config.cfg import cfg
    task = _taskService.taskById(taskId)
    if task:
        _taskService.delete(task, shouldDeleteFiles=cfg.shouldDeleteFilesOnRemove.value)


# ---- KeepAlive ----

def keepAlive() -> str:
    from app.models.task import TaskStatus

    running = [t for t in _taskService.tasks
               if t.status in (TaskStatus.RUNNING, TaskStatus.WAITING)]
    if running:
        snapshots = [t.currentSnapshot() for t in running]
        return json.dumps({
            "reason": "downloading",
            "count": len(running),
            "progress": sum(s[0] for s in snapshots) / len(running),
            "speed": sum(s[1] for s in snapshots),
        })

    if _aria2RpcServer.isRunning or _browserService.boundPort:
        return json.dumps({"reason": "serving", "pair": _pairFields()})
    return json.dumps({"reason": ""})


# ---- Runtimes ----

def runtimes() -> str:
    result = []
    for runtime in _featureService.runtimes():
        status = _runtimeStatusService.status(runtime)
        error = status.error
        result.append({
            "id": runtime.runtimeId,
            "title": runtime.title,
            "description": runtime.description,
            "canInstall": runtime.canInstall,
            "isInstalled": bool(status.path),
            "isBusy": status.isBusy,
            "isInstalling": status.isInstalling,
            "progress": status.progress,
            "version": status.version,
            "detail": status.detail,
            "latestVersion": status.latestVersion,
            "error": None if error is None else {
                "message": error.message,
                "params": {k: str(v) for k, v in error.params.items()},
            },
        })
    return json.dumps(result, ensure_ascii=False)


def refreshRuntimes():
    for runtime in _featureService.runtimes():
        _runtimeStatusService.refreshStatus(runtime)


def installRuntime(runtimeId: str):
    runtime = _runtimeById(runtimeId)
    if runtime:
        _runtimeStatusService.install(runtime)


def cancelRuntimeInstall(runtimeId: str):
    runtime = _runtimeById(runtimeId)
    if runtime:
        _runtimeStatusService.cancelInstall(runtime)


def _runtimeById(runtimeId: str):
    return next(
        (r for r in _featureService.runtimes() if r.runtimeId == runtimeId), None,
    )


# ---- Browser Extension ----

def browserExtension() -> str:
    installType, version = _browserService.connectionSummary
    return json.dumps({
        "port": _browserService.boundPort,
        "token": _browserService.token,
        "installType": installType,
        "extensionVersion": version,
    }, ensure_ascii=False)


def regenerateBrowserToken():
    _browserService.regenerateToken()


def respondBrowserPair(requestId: str, isApproved: bool):
    request = _takePair(requestId)
    if not request:
        return
    if isApproved:
        _browserService.approvePair(request["session"], requestId)
    else:
        _browserService.rejectPair(request["session"], requestId)


def _takePair(requestId: str):
    global _pendingPair
    if _pendingPair is None or _pendingPair["requestId"] != requestId:
        return None
    request, _pendingPair = _pendingPair, None
    return request


def _onBrowserPairRequested(request: dict):
    global _pendingPair
    _pendingPair = request


def _pairFields():
    if _pendingPair is None:
        return None
    return {
        "requestId": _pendingPair["requestId"],
        "clientKind": _pendingPair["clientKind"],
        "extensionVersion": _pendingPair["extensionVersion"],
    }


def exportBrowserExtension(crxPath: str, folder: str) -> str:
    import struct
    import zipfile
    from io import BytesIO
    from pathlib import Path

    crxData = Path(crxPath).read_bytes()
    headerSize = struct.unpack_from("<I", crxData, 8)[0]
    zipOffset = 12 + headerSize

    dest = Path(folder)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(BytesIO(crxData[zipOffset:])) as zf:
        zf.extractall(dest)
    return str(dest)
