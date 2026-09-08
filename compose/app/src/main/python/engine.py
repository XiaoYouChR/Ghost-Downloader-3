"""Android composition root. Kotlin calls methods on _engine."""
from __future__ import annotations

import asyncio
import json
import struct
import zipfile
from io import BytesIO
from pathlib import Path

from loguru import logger

from app.platform.file_watcher import InotifyFileWatcher


class Engine:
    def __init__(self):
        from app.config.paths import APP_DATA_DIR
        from app.config.cfg import cfg

        logger.add(f"{APP_DATA_DIR}/GhostDownloader.log", rotation="512 KB", retention=3)
        cfg.load(f"{APP_DATA_DIR}/UserConfig.json")

        from app.services.coroutine_runner import CoroutineRunner
        from app.services.category_service import CategoryService
        from app.services.speed_meter import SpeedMeter

        loop = asyncio.new_event_loop()
        self._coroutineRunner = CoroutineRunner(
            dispatcher=loop.call_soon_threadsafe,
            isAlive=None,
            loop=loop,
        )
        categoryService = CategoryService()
        self._speedMeter = SpeedMeter(self._coroutineRunner)

        from app.services.task_service import TaskService
        from app.services.feature_service import FeatureService
        from app.services.runtime_status import RuntimeStatusService

        self._taskService = TaskService(
            self._coroutineRunner, categoryService, self._speedMeter,
            fileWatcher=InotifyFileWatcher(loop, self._coroutineRunner.post),
        )
        self._runtimeStatusService = RuntimeStatusService(self._coroutineRunner)
        self._featureService = FeatureService(
            self._taskService, categoryService, self._coroutineRunner,
            self._runtimeStatusService,
        )

        from app.models.pack import PackServices

        self._packAdapters: dict = {}
        self._loadPacks(PackServices(
            coroutineRunner=self._coroutineRunner,
            speedMeter=self._speedMeter,
        ))

        # pack import 时才注册 ConfigItem，需要重建索引后重新加载
        cfg._index()
        cfg.load(f"{APP_DATA_DIR}/UserConfig.json")

        from app.services.task_draft import TaskDraft

        self._draftErrors: dict = {}
        self._taskDraft = TaskDraft(self._coroutineRunner, self._featureService)
        self._taskDraft.taskConfirmed.connect(self._taskService.add)
        self._taskDraft.parseFailed.connect(self._onParseFailed)

        from app.services.aria2_rpc import Aria2RpcServer
        from app.services.browser_service import BrowserService

        self._aria2RpcServer = Aria2RpcServer(
            self._coroutineRunner, parse=self._featureService.parse,
            addTask=self._taskService.add,
        )
        cfg.isAria2RpcEnabled.valueChanged.connect(self._aria2RpcServer.setEnabled)
        cfg.aria2RpcPort.valueChanged.connect(self._onAria2RpcPortChanged)

        self._pendingPair = None
        self._browserService = BrowserService(
            self._coroutineRunner, self._taskService,
            parse=self._featureService.parse, loadCrx=None,
        )
        self._browserService.pairRequested.connect(self._onBrowserPairRequested)
        cfg.isBrowserExtensionEnabled.valueChanged.connect(self._browserService.setEnabled)
        cfg.browserExtensionPort.valueChanged.connect(self._onBrowserPortChanged)

        self._coroutineRunner.start()
        if cfg.isAria2RpcEnabled.value:
            self._aria2RpcServer.start()
        if cfg.isBrowserExtensionEnabled.value:
            self._browserService.start()
        self._taskService.resumeSaved()
        self._featureService.activate()
        logger.info("Engine started, dataDir={}", APP_DATA_DIR)

    def _loadPacks(self, services):
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
                self._featureService._register(pack)

                try:
                    adapter = importlib.import_module(f"{manifest.name}.android")
                    if hasattr(adapter, 'init'):
                        adapter.init(pack)
                    self._packAdapters[pack.packId] = adapter
                except ImportError:
                    pass

                logger.success("加载 FeaturePack: {}", manifest.name)
            except Exception as e:
                logger.opt(exception=e).error("加载 FeaturePack 失败: {}", manifest.name)

    # ---- Tasks ----

    def tasks(self) -> str:
        result = []
        for t in self._taskService.tasks:
            progress, speed, received = t.currentSnapshot()
            result.append({
                "id": t.taskId,
                "name": t.name,
                "progress": progress,
                "speed": speed,
                "received": received,
                "status": t.status.name,
                "fileSize": t.fileSize,
                "fileCount": len(t.files) if t.files else 0,
                "error": t.lastError.toDict() if t.lastError else None,
                **self._adapterFields(t, 'taskFields'),
            })
        return json.dumps(result, ensure_ascii=False)

    def pause(self, taskId: str):
        task = self._taskService.taskById(taskId)
        if task:
            self._taskService.pause(task)

    def resume(self, taskId: str):
        task = self._taskService.taskById(taskId)
        if task:
            self._taskService.start(task)

    def remove(self, taskId: str):
        from app.config.cfg import cfg
        task = self._taskService.taskById(taskId)
        if task:
            self._taskService.delete(task, shouldDeleteFiles=cfg.shouldDeleteFilesOnRemove.value)

    # ---- Draft ----

    def parse(self, urls: str):
        from app.config.cfg import currentHeaders

        self._draftErrors.clear()
        self._taskDraft.setBaseOptions({"headers": currentHeaders()})
        self._taskDraft.setUrls([u.strip() for u in urls.splitlines() if u.strip()])

    def draft(self) -> str:
        result = []
        for url in self._taskDraft.urls():
            task = self._taskDraft.taskByUrl(url)
            error = self._draftErrors.get(url)
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
                "error": error.toDict() if error else None,
                **self._adapterFields(task, 'draftFields'),
            })
        return json.dumps(result, ensure_ascii=False)

    def setDraftName(self, url: str, name: str):
        task = self._taskDraft.taskByUrl(url)
        if task:
            task.name = name

    def setDraftSelection(self, url: str, indexes: str):
        task = self._taskDraft.taskByUrl(url)
        if task:
            task.setSelection([int(i) for i in indexes.split(",") if i])

    def setDraft(self, url: str, action: str, *args):
        task = self._taskDraft.taskByUrl(url)
        if not task:
            return
        adapter = self._packAdapters.get(task.packId)
        fn = getattr(adapter, action, None) if adapter else None
        if fn:
            fn(task, *args)

    def confirmDraft(self):
        self._taskDraft.confirm()
        self._draftErrors.clear()

    def clearDraft(self):
        self._taskDraft.clear()
        self._draftErrors.clear()

    def _onParseFailed(self, url, error):
        self._draftErrors[url] = error

    # ---- Settings ----

    def settings(self) -> str:
        from app.config.cfg import cfg
        return json.dumps(
            {name: item.value for name, item in cfg.byName.items()},
            ensure_ascii=False,
        )

    def setSetting(self, name: str, value):
        from app.config.cfg import cfg
        cfg.set(cfg.byName[name], value)

    # ---- Runtimes ----

    def runtimes(self) -> str:
        result = []
        for runtime in self._featureService.runtimes():
            status = self._runtimeStatusService.status(runtime)
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
                "error": status.error.toDict() if status.error else None,
            })
        return json.dumps(result, ensure_ascii=False)

    def refreshRuntimes(self):
        for runtime in self._featureService.runtimes():
            self._runtimeStatusService.refreshStatus(runtime)

    def installRuntime(self, runtimeId: str):
        runtime = self._runtimeById(runtimeId)
        if runtime:
            self._runtimeStatusService.install(runtime)

    def cancelRuntimeInstall(self, runtimeId: str):
        runtime = self._runtimeById(runtimeId)
        if runtime:
            self._runtimeStatusService.cancelInstall(runtime)

    def _runtimeById(self, runtimeId: str):
        return next(
            (r for r in self._featureService.runtimes() if r.runtimeId == runtimeId),
            None,
        )

    # ---- Browser Extension ----

    def browserExtension(self) -> str:
        installType, version = self._browserService.connectionSummary
        return json.dumps({
            "port": self._browserService.boundPort,
            "token": self._browserService.token,
            "installType": installType,
            "extensionVersion": version,
        }, ensure_ascii=False)

    def regenerateBrowserToken(self):
        self._browserService.regenerateToken()

    def setBrowserPairApproval(self, requestId: str, isApproved: bool):
        pair = self._takePair(requestId)
        if not pair:
            return
        if isApproved:
            self._browserService.approvePair(pair["session"], requestId)
        else:
            self._browserService.rejectPair(pair["session"], requestId)

    def extractBrowserExtension(self, crxPath: str, folder: str) -> str:
        crxData = Path(crxPath).read_bytes()
        headerSize = struct.unpack_from("<I", crxData, 8)[0]
        zipOffset = 12 + headerSize

        dest = Path(folder)
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(BytesIO(crxData[zipOffset:])) as zf:
            zf.extractall(dest)
        return str(dest)

    def _takePair(self, requestId: str):
        if self._pendingPair is None or self._pendingPair["requestId"] != requestId:
            return None
        pair, self._pendingPair = self._pendingPair, None
        return pair

    def _onBrowserPairRequested(self, request: dict):
        self._pendingPair = request

    def _pairFields(self):
        if self._pendingPair is None:
            return None
        return {
            "requestId": self._pendingPair["requestId"],
            "clientKind": self._pendingPair["clientKind"],
            "extensionVersion": self._pendingPair["extensionVersion"],
        }

    def _onAria2RpcPortChanged(self, _port):
        from app.config.cfg import cfg
        if cfg.isAria2RpcEnabled.value:
            self._aria2RpcServer.stop()
            self._aria2RpcServer.start()

    def _onBrowserPortChanged(self, _port):
        from app.config.cfg import cfg
        if cfg.isBrowserExtensionEnabled.value:
            self._browserService.stop()
            self._browserService.start()

    # ---- KeepAlive ----

    def keepAlive(self) -> str:
        from app.models.task import TaskStatus

        running = [t for t in self._taskService.tasks
                   if t.status in (TaskStatus.RUNNING, TaskStatus.WAITING)]
        if running:
            snapshots = [t.currentSnapshot() for t in running]
            return json.dumps({
                "reason": "downloading",
                "count": len(running),
                "progress": sum(s[0] for s in snapshots) / len(running),
                "speed": sum(s[1] for s in snapshots),
            })

        if self._aria2RpcServer.isRunning or self._browserService.boundPort:
            return json.dumps({"reason": "serving", "pair": self._pairFields()})
        return json.dumps({"reason": ""})

    # ---- Pack Adapter ----

    def packState(self, packId: str, name: str) -> str:
        adapter = self._packAdapters.get(packId)
        fn = getattr(adapter, name, None) if adapter else None
        return json.dumps(fn(), ensure_ascii=False) if fn else "{}"

    def requestPack(self, packId: str, action: str, *args):
        adapter = self._packAdapters.get(packId)
        fn = getattr(adapter, action, None) if adapter else None
        if fn:
            fn(*args)

    def _adapterFields(self, task, method: str) -> dict:
        if task is None:
            return {}
        adapter = self._packAdapters.get(task.packId)
        fn = getattr(adapter, method, None) if adapter else None
        return fn(task) if fn else {}


_engine: Engine | None = None


def start():
    global _engine
    _engine = Engine()
