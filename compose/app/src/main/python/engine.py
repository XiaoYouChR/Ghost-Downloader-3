"""Android composition root. Kotlin calls methods on _engine."""
from __future__ import annotations

import asyncio
import json
import struct
import zipfile
from io import BytesIO
from pathlib import Path

from loguru import logger

from app.config.cfg import cfg
from app.platform.file_watcher import InotifyFileWatcher


class Engine:
    def __init__(self):
        from app.config.paths import APP_DATA_DIR

        logger.add(f"{APP_DATA_DIR}/GhostDownloader.log", rotation="512 KB", retention=3)
        cfg.load(f"{APP_DATA_DIR}/UserConfig.json")

        from app.services.coroutine_runner import CoroutineRunner
        from app.services.category_service import CategoryService
        from app.services.speed_meter import SpeedMeter

        loop = asyncio.new_event_loop()
        self._loop = loop
        self._coroutineRunner = CoroutineRunner(
            dispatcher=loop.call_soon_threadsafe,
            isAlive=None,
            loop=loop,
        )
        self._categoryService = CategoryService()
        self._speedMeter = SpeedMeter(self._coroutineRunner)

        from app.services.task_service import TaskService
        from app.services.feature_service import FeatureService
        from app.services.runtime_status import RuntimeStatusService

        self._taskService = TaskService(
            self._coroutineRunner, self._categoryService, self._speedMeter,
            fileWatcher=InotifyFileWatcher(loop, self._coroutineRunner.post),
        )
        self._runtimeStatusService = RuntimeStatusService(self._coroutineRunner)
        self._featureService = FeatureService(
            self._taskService, self._categoryService, self._coroutineRunner,
            self._runtimeStatusService,
        )

        from app.models.pack import PackServices

        self._packAdapters: dict = {}
        self._loadPacks(PackServices(
            coroutineRunner=self._coroutineRunner,
            speedMeter=self._speedMeter,
        ))

        from task_edit import TaskEdits
        self._taskEdits = TaskEdits(
            self._taskService.taskById, self._featureService.parse,
            self._taskService.edit, self._packAdapters, loop,
        )

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
        self._setupFlows()
        logger.info("Engine started, dataDir={}", APP_DATA_DIR)

    def _setupFlows(self):
        from java import jclass
        self._flows = jclass("com.xychr.ghostdownloader.engine.EngineFlows")

        for signal in (
            self._taskService.taskAdded,
            self._taskService.taskRemoved,
            self._taskService.taskStarted,
            self._taskService.taskPaused,
            self._taskService.taskCompleted,
            self._taskService.taskFailed,
            self._taskService.tasksAllCompleted,
        ):
            signal.connect(self._emitKeepAlive)
            signal.connect(self._emitTasks)

        self._speedMeter.speedChanged.connect(self._emitKeepAlive)
        self._speedMeter.speedChanged.connect(self._emitTaskProgress)
        cfg.isAria2RpcEnabled.valueChanged.connect(self._emitKeepAlive)
        cfg.isBrowserExtensionEnabled.valueChanged.connect(self._emitKeepAlive)

        self._categoryService.categoriesChanged.connect(self._emitCategoryState)
        cfg.isCategoryEnabled.valueChanged.connect(self._emitCategoryState)
        cfg.downloadFolder.valueChanged.connect(self._emitCategoryState)

        for item in cfg.byName.values():
            item.valueChanged.connect(self._emitSettings)

        self._emitKeepAlive()
        self._emitCategoryState()
        self._emitSettings()
        self._emitTasks()
        self._emitTaskProgress()

    def _emitKeepAlive(self, *_args):
        self._flows.emit("keepAlive", self.keepAlive())

    def _emitSettings(self, *_args):
        self._flows.emit("settings", self.settings())

    def _emitCategoryState(self, *_args):
        self._flows.emit("categoryState", self.categoryState())

    def _emitTasks(self, *_args):
        self._flows.emit("tasks", self.tasks())

    def _emitTaskProgress(self, *_args):
        self._flows.emit("taskProgress", self.taskProgress())

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

    def _taskFields(self, task) -> dict:
        return {
            "id": task.taskId,
            "packId": task.packId or "",
            "canPause": task.canPause,
            "canEdit": task.canEdit,
            "categoryId": task.category or "",
            "outputPath": str(task.outputPath),
            "hasOutputFile": task.hasOutputFile,
            "name": task.name,
            "url": task.url,
            "status": task.status.name,
            "fileSize": task.fileSize,
            "createdAt": task.createdAt,
            "completedAt": task.completedAt,
            "error": task.lastError.toDict() if task.lastError else None,
            **self._adapterFields(task, 'taskFields'),
        }

    def _allFields(self, task) -> dict:
        progress, speed, received = task.currentSnapshot()
        fields = self._taskFields(task)
        fields["progress"] = progress
        fields["speed"] = speed
        fields["received"] = received
        return fields

    def tasks(self) -> str:
        result = []
        for t in self._taskService.tasks:
            fields = self._taskFields(t)
            fields["fileCount"] = len(t.files) if t.files else 0
            fields["selectedFileCount"] = sum(f.selected for f in t.files) if t.files else 0
            result.append(fields)
        return json.dumps(result, ensure_ascii=False)

    def taskProgress(self) -> str:
        from app.models.task import TaskStatus
        snapshots = {}
        for t in self._taskService.tasks:
            if t.status in (TaskStatus.RUNNING, TaskStatus.WAITING):
                progress, speed, received = t.currentSnapshot()
                snapshots[t.taskId] = {
                    "progress": progress, "speed": speed, "received": received,
                }
        return json.dumps(snapshots)

    def pause(self, taskId: str):
        from app.models.task import TaskStatus
        task = self._taskService.taskById(taskId)
        if task and task.status == TaskStatus.RUNNING and task.canPause:
            self._taskService.pause(task)

    def resume(self, taskId: str):
        task = self._taskService.taskById(taskId)
        if task:
            self._taskService.start(task)

    def stopTask(self, taskId: str):
        task = self._taskService.taskById(taskId)
        if task is None:
            return
        adapter = self._packAdapters.get(task.packId)
        stop = getattr(adapter, "stop", None)
        if stop is not None:
            stop(task)

    # shouldDeleteFiles 为 None 时用设置里的全局开关，调用方逐次勾选则显式传
    def remove(self, taskId: str, shouldDeleteFiles=None):
        task = self._taskService.taskById(taskId)
        if task:
            self._taskService.delete(task, shouldDeleteFiles=(
                cfg.shouldDeleteFilesOnRemove.value if shouldDeleteFiles is None
                else shouldDeleteFiles
            ))

    def taskDetail(self, taskId: str) -> str:
        task = self._taskService.taskById(taskId)
        if task is None:
            return "{}"
        fields = self._allFields(task)
        fields["canRename"] = task.canEdit and task.status.name not in {"RUNNING", "COMPLETED"} and fields["received"] == 0
        fields["outputFolder"] = str(task.outputFolder)
        fields["files"] = [
            {
                "index": f.index,
                "path": f.relativePath,
                "categoryId": self._categoryService.matchByName(f.relativePath),
                "size": f.size,
                "isSelected": f.selected,
                "isCompleted": f.completed,
                "progress": f.downloadedBytes / f.size * 100 if f.size > 0 else 0,
            }
            for f in task.files
        ] if task.files else []
        return json.dumps(fields, ensure_ascii=False)

    def setTaskName(self, taskId: str, name: str):
        task = self._taskService.taskById(taskId)
        if task is None or not task.canEdit or task.status.name in {"RUNNING", "COMPLETED"} or task.currentSnapshot()[2] > 0:
            raise ValueError("Only tasks without downloaded data can be renamed")
        if not name.strip():
            raise ValueError("Name must not be empty")
        task.setName(name.strip())
        self._taskService.flush()

    def setTaskSelection(self, taskId: str, indexes: str):
        task = self._taskService.taskById(taskId)
        if task is None:
            raise ValueError("Task no longer exists")
        selected = {int(i) for i in indexes.split(",") if i}
        if not selected or not selected.issubset({f.index for f in task.files or []}):
            raise ValueError("Select at least one existing file")
        self._taskService.updateSelection(task, selected)

    def taskOptions(self, taskId: str) -> str:
        return json.dumps(self._taskEdits.build(taskId), ensure_ascii=False)

    def updateTaskOptions(self, taskId: str, values: str, shouldDiscard: bool = False) -> str:
        return json.dumps(self._taskEdits.update(taskId, json.loads(values), shouldDiscard))

    def cancelTaskEdit(self, taskId: str):
        self._taskEdits.cancel(taskId)

    def categoryState(self) -> str:
        from dataclasses import asdict
        return json.dumps({"isEnabled": cfg.isCategoryEnabled.value, "defaultFolder": cfg.downloadFolder.value,
                           "categories": [asdict(c) for c in self._categoryService.categories()]}, ensure_ascii=False)

    def setTaskCategory(self, taskIds: str, categoryId: str):
        if categoryId and self._categoryService.categoryById(categoryId) is None:
            raise ValueError("Category no longer exists")
        for taskId in json.loads(taskIds):
            task = self._taskService.taskById(taskId)
            if task is not None:
                self._taskService.setCategory(task, categoryId)

    def moveToFront(self, taskId: str):
        self._taskService.moveToFront([taskId])

    def redownload(self, taskId: str):
        task = self._taskService.taskById(taskId)
        if task:
            self._taskService.redownload(task)

    # ---- Draft ----

    def parse(self, urls: str):
        from app.config.cfg import currentHeaders

        nextUrls = [u.strip() for u in urls.splitlines() if u.strip()]
        self._draftErrors = {url: error for url, error in self._draftErrors.items() if url in nextUrls}
        self._taskDraft.setBaseOptions({"headers": currentHeaders()})
        self._taskDraft.setUrls(nextUrls)

    def draft(self) -> str:
        from task_category import buildDestination
        result = []
        for url in self._taskDraft.urls():
            task = self._taskDraft.taskByUrl(url)
            error = self._draftErrors.get(url)
            destination = buildDestination(task, self._categoryService, cfg.downloadFolder.value,
                                           cfg.isCategoryEnabled.value) if task else None
            result.append({
                "url": url,
                "isParsing": task is None and error is None,
                "name": "" if task is None else task.name,
                "categoryChoice": task.category if task else None,
                "categoryId": destination.categoryId if destination else "",
                "outputFolder": str(task.outputFolder) if task else "",
                "targetFolder": destination.targetFolder if destination else "",
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
            raise ValueError("Draft is no longer available")
        if action == "setCategory":
            categoryId = None if bool(args[1]) else str(args[0])
            if categoryId and self._categoryService.categoryById(categoryId) is None:
                raise ValueError("Category no longer exists")
            self._taskDraft.setUrlCategory(url, categoryId)
            task.category = categoryId
            return
        if action == "setOutputFolder":
            folder = Path(str(args[0]).strip())
            if not folder.is_absolute():
                raise ValueError("Output folder must be an absolute path")
            task.setOptions({"outputFolder": str(folder)})
            return
        if action == "setName":
            if not str(args[0]).strip():
                raise ValueError("Name cannot be empty")
            task.setName(str(args[0]).strip())
            return
        if action == "setSelection":
            indexes = [int(i) for i in str(args[0]).split(",") if i]
            if not indexes:
                raise ValueError("Select at least one file")
            task.setSelection(indexes)
            return
        adapter = self._packAdapters.get(task.packId)
        fn = getattr(adapter, action, None) if adapter else None
        if fn:
            fn(task, *args)
        else:
            raise ValueError("This draft does not support the requested operation")

    def probeDraft(self, url: str, kind: str):
        task = self._taskDraft.taskByUrl(url)
        if task is None:
            raise ValueError("Draft is no longer available")
        adapter = self._packAdapters.get(task.packId)
        fn = getattr(adapter, "probe", None) if adapter else None
        if fn is None:
            raise ValueError("Unsupported draft probe")

        async def run():
            await asyncio.to_thread(fn, task, url, kind)

        asyncio.run_coroutine_threadsafe(run(), self._loop).result()

    def draftPreview(self, url: str) -> str:
        task = self._taskDraft.taskByUrl(url)
        if task is None:
            raise ValueError("Draft is no longer available")
        adapter = self._packAdapters.get(task.packId)
        if adapter is None or not hasattr(adapter, "probePreview"):
            return '{"sheets": []}'
        result = asyncio.run_coroutine_threadsafe(adapter.probePreview(task), self._loop).result()
        return json.dumps(result, ensure_ascii=False)

    def confirmDraft(self):
        async def confirm():
            self._taskDraft.confirm()
            self._draftErrors.clear()

        # Probe completion and confirmation must not mutate the same Task concurrently.
        asyncio.run_coroutine_threadsafe(confirm(), self._loop).result()

    def clearDraft(self):
        async def clear():
            self._taskDraft.clear()
            self._draftErrors.clear()

        asyncio.run_coroutine_threadsafe(clear(), self._loop).result()

    def _onParseFailed(self, url, error):
        self._draftErrors[url] = error

    # ---- Settings ----

    def settings(self) -> str:
        return json.dumps(
            {name: item.value for name, item in cfg.byName.items()},
            ensure_ascii=False,
        )

    def setSetting(self, name: str, value):
        item = cfg.byName[name]
        cfg.set(item, value)

    # ---- Categories ----

    # 结构比 settings() 里那份 categoryRules 完整（带 categoryId），编辑页要靠它定位
    def categories(self) -> str:
        from dataclasses import asdict
        return json.dumps(
            [asdict(c) for c in self._categoryService.categories()],
            ensure_ascii=False,
        )

    def addCategory(self, categoryJson: str):
        from app.services.category_service import Category
        category = Category.fromDict(json.loads(categoryJson))
        self._categoryService.addCategory(category)

    def updateCategory(self, categoryJson: str):
        from app.services.category_service import Category
        self._categoryService.updateCategory(Category.fromDict(json.loads(categoryJson)))

    def removeCategory(self, categoryId: str):
        self._categoryService.removeCategory(categoryId)

    def reorderCategories(self, categoryIds: str):
        self._categoryService.reorder(json.loads(categoryIds))

    def resetCategories(self):
        self._categoryService.reset()

    # ---- Identity ----

    def clientProfiles(self) -> str:
        from app.client import profileFamilies, profileVersions
        return json.dumps([
            {"family": family, "versions": profileVersions(family)}
            for family in profileFamilies()
        ])

    def defaultHeaders(self) -> str:
        from app.config.cfg import BASE_HEADERS
        return json.dumps(BASE_HEADERS)

    def setIdentityOrder(self, index: int, target: int):
        presets = list(cfg.identityPresets.value)
        if not (0 <= index < len(presets) and 0 <= target < len(presets)):
            raise ValueError("Identity preset no longer exists")
        presets.insert(target, presets.pop(index))
        self.setSetting("identityPresets", presets)

    def addIdentityPreset(self, presetJson: str):
        self.setSetting("identityPresets", [*cfg.identityPresets.value, json.loads(presetJson)])

    def updateIdentityPreset(self, index: int, presetJson: str):
        presets = list(cfg.identityPresets.value)
        if not 0 <= index < len(presets):
            raise ValueError("Identity preset no longer exists")
        presets[index] = json.loads(presetJson)
        self.setSetting("identityPresets", presets)

    def removeIdentityPreset(self, index: int):
        presets = list(cfg.identityPresets.value)
        if 0 <= index < len(presets):
            del presets[index]
            self.setSetting("identityPresets", presets)

    def addHeadersPreset(self, presetJson: str):
        self.setSetting("headersPresets", [*cfg.headersPresets.value, json.loads(presetJson)])

    def updateHeadersPreset(self, index: int, presetJson: str):
        presets = list(cfg.headersPresets.value)
        if not 0 <= index < len(presets):
            raise ValueError("Headers preset no longer exists")
        presets[index] = json.loads(presetJson)
        self.setSetting("headersPresets", presets)

    def removeHeadersPreset(self, index: int):
        presets = list(cfg.headersPresets.value)
        if 0 <= index < len(presets):
            del presets[index]
            self.setSetting("headersPresets", presets)

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
        self._emitKeepAlive()

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
        self._emitKeepAlive()

    def _pairFields(self):
        if self._pendingPair is None:
            return None
        return {
            "requestId": self._pendingPair["requestId"],
            "clientKind": self._pendingPair["clientKind"],
            "extensionVersion": self._pendingPair["extensionVersion"],
        }

    def _onAria2RpcPortChanged(self, _port):
        if cfg.isAria2RpcEnabled.value:
            self._aria2RpcServer.stop()
            self._aria2RpcServer.start()

    def _onBrowserPortChanged(self, _port):
        if cfg.isBrowserExtensionEnabled.value:
            self._browserService.stop()
            self._browserService.start()

    # ---- KeepAlive ----

    def keepAlive(self) -> str:
        from app.models.task import TaskStatus

        pair = self._pairFields()

        running = [t for t in self._taskService.tasks
                   if t.status in (TaskStatus.RUNNING, TaskStatus.WAITING)]
        if running:
            snapshots = [t.currentSnapshot() for t in running]
            return json.dumps({
                "reason": "downloading",
                "count": len(running),
                "progress": sum(s[0] for s in snapshots) / len(running),
                "speed": sum(s[1] for s in snapshots),
                "pair": pair,
            })

        if self._aria2RpcServer.isRunning or self._browserService.boundPort:
            return json.dumps({"reason": "serving", "pair": pair})
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

    def packInfos(self) -> str:
        result = []
        for pack in self._featureService._packs:
            m = pack.manifest
            if m is None:
                continue
            result.append({
                "packId": pack.packId,
                "name": m.className,
                "version": m.version,
            })
        return json.dumps(result, ensure_ascii=False)

    # ---- Update ----

    def checkUpdate(self) -> str:
        import asyncio
        from app.config.constants import VERSION
        from app.update import fetchRelease, bestAsset, isNewer

        async def _check():
            release = await fetchRelease()
            asset = bestAsset(release)
            return {
                "available": isNewer(VERSION, release.version),
                "currentVersion": VERSION,
                "latestVersion": release.version,
                "assetName": asset.name if asset else "",
                "assetSize": asset.size if asset else 0,
                "releaseNotes": release.body,
                "releaseUrl": release.pageUrl,
            }

        future = asyncio.run_coroutine_threadsafe(_check(), self._loop)
        return json.dumps(future.result(timeout=30), ensure_ascii=False)

    def downloadUpdate(self, targetId: str):
        import asyncio
        from app.update import APP_REPO, fetchRelease, bestAsset
        from app.sources import probeDownloadUrl
        from app.client import fetchFile
        from app.config.paths import APP_DATA_DIR

        self._updateState = {"state": "downloading", "progress": 0, "filePath": "", "error": ""}
        self._emitUpdateState()

        async def _download():
            try:
                release = await fetchRelease()
                asset = bestAsset(release)
                if asset is None:
                    self._updateState = {"state": "failed", "progress": 0, "filePath": "",
                                         "error": "No suitable asset found"}
                    self._emitUpdateState()
                    return
                url = await probeDownloadUrl(APP_REPO, release.version, asset.name)
                outputPath = APP_DATA_DIR / "cache" / asset.name
                lastEmitted = 0
                def _onProgress(p):
                    nonlocal lastEmitted
                    self._updateState["progress"] = p
                    if p - lastEmitted >= 1 or p >= 100:
                        lastEmitted = p
                        self._emitUpdateState()
                await fetchFile(url, outputPath, onProgress=_onProgress)
                self._updateState = {"state": "ready", "progress": 100,
                                     "filePath": str(outputPath), "error": ""}
                self._emitUpdateState()
            except Exception as e:
                self._updateState = {"state": "failed", "progress": 0, "filePath": "",
                                     "error": str(e)}
                self._emitUpdateState()

        asyncio.run_coroutine_threadsafe(_download(), self._loop)

    def _emitUpdateState(self):
        self._flows.emit("updateState", self.updateState())

    def updateState(self) -> str:
        return json.dumps(getattr(self, '_updateState',
                                  {"state": "idle", "progress": 0, "filePath": "", "error": ""}))

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
    result = {}
    for packId, adapter in _engine._packAdapters.items():
        uiClass = getattr(adapter, 'UI_CLASS', None)
        if uiClass is None:
            continue
        pack = _engine._featureService._packByPackId.get(packId)
        entry = {"uiClass": uiClass}
        if pack and pack.config:
            entry["configClass"] = pack.config.__class__.__name__
        result[packId] = entry
    return json.dumps(result)
