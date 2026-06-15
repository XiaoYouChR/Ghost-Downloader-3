"""全 app 唯一的 libtorrent session。

主流 BT 客户端(qBittorrent/Deluge)都是一个进程一个 session，所有 torrent 加进同一个
session，由它统一持有监听端口 / DHT / 限速器 / 连接池，并用一条 alert 泵驱动全部 torrent。
本模块就是这个角色:Pack 拥有 session 这台机器,Core 只负责调度(占不占 slot)。

每个 BTTask 通过 `lease()` 把自己的 torrent 登记进来、挂起等终态;泵循环直接把
`torrent_status` 写回各 task 字段,并在做种到限额时 resolve 对应 Future 让 worker 收尾。
"""

import asyncio
from base64 import b64decode, b64encode
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import gettempdir
from urllib.parse import urlsplit

import libtorrent as lt
from loguru import logger

from app.services.core_service import coreService
from app.supports.config import VERSION
from app.supports.utils import getProxies
from .config import bittorrentConfig
from .task import BTTask
from .trackers import mergeTrackers

USER_AGENT = f"GhostDownloader/{VERSION} libtorrent/{lt.__version__}"

# torrent_status.state.name → 展示文案
_STATE_TEXT = {
    "checking_files": "校验已有文件",
    "checking_resume_data": "检查续传状态",
    "downloading_metadata": "获取元数据",
    "downloading": "下载中",
    "finished": "下载完成",
    "seeding": "做种中",
    "allocating": "分配文件中",
    "queued_for_checking": "等待校验",
}

_ERROR_ALERTS = (
    lt.file_error_alert,
    lt.metadata_failed_alert,
    lt.torrent_error_alert,
    lt.hash_failed_alert,
)


@dataclass(eq=False)
class _ActiveTorrent:
    """session 视角下的一条在跑 torrent:把 task、handle 与做种计时记在一处。"""

    task: BTTask
    handle: lt.torrent_handle
    done: asyncio.Future
    resumeWaiter: asyncio.Future | None = None
    appliedSelectionVersion: int = -1
    _seedBase: int = field(init=False)
    _seedStart: int | None = field(default=None, init=False)

    def __post_init__(self):
        self._seedBase = self.task.seedingTimeSeconds

    def seedingElapsed(self, isSeeding: bool, sessionSeconds: int) -> int:
        if isSeeding:
            if self._seedStart is None:
                self._seedStart = sessionSeconds
            return self._seedBase + max(0, sessionSeconds - self._seedStart)
        if self._seedStart is not None:
            self._seedBase += max(0, sessionSeconds - self._seedStart)
            self._seedStart = None
        return self._seedBase


class BTSessionService:
    def __init__(self):
        self._session: lt.session | None = None
        self._pump: asyncio.Task | None = None
        self._active: dict[str, _ActiveTorrent] = {}
        self._pendingMetadata: list[tuple[lt.torrent_handle, asyncio.Future]] = []
        for item in (
            bittorrentConfig.downloadRateLimit,
            bittorrentConfig.uploadRateLimit,
            bittorrentConfig.connectionsLimit,
        ):
            item.valueChanged.connect(self._onLimitsChanged)

    # ── 对 worker:登记一条 torrent,挂起到终态 ──────────────────────────────
    async def lease(self, task: BTTask):
        if task.countSelected <= 0:
            raise RuntimeError("至少需要选择一个文件")

        self._prepareTarget(task)
        self._saveMagnetFile(task)
        self._open()

        handle = self._addTorrent(task)
        handle.resume()
        handle.force_reannounce(0, -1, lt.reannounce_flags_t.ignore_min_interval)
        if bittorrentConfig.enableDHT.value:
            handle.force_dht_announce()

        active = _ActiveTorrent(task, handle, asyncio.get_running_loop().create_future())
        self._active[task.taskId] = active
        try:
            await active.done
        finally:
            await asyncio.shield(self._removeTorrent(active))

    # ── 对 loaders:磁力取元数据,复用共享 session 的热 DHT ─────────────────
    async def fetchMetadata(
        self, magnetUri: str, webTrackers: list[str]
    ) -> tuple[bytes, lt.torrent_info, list[str]]:
        self._open()

        params = lt.parse_magnet_uri(magnetUri)
        params.trackers = mergeTrackers(params.trackers, webTrackers)
        tempDir = Path(gettempdir()) / "ghost_downloader_bt_metadata"
        tempDir.mkdir(parents=True, exist_ok=True)
        params.save_path = str(tempDir)
        params.storage_mode = lt.storage_mode_t.storage_mode_sparse
        params.flags |= lt.torrent_flags.default_dont_download | lt.torrent_flags.update_subscribe

        handle = self._addToSession(params)
        handle.force_reannounce(0, -1, lt.reannounce_flags_t.ignore_min_interval)
        if bittorrentConfig.enableDHT.value:
            handle.force_dht_announce()

        waiter = asyncio.get_running_loop().create_future()
        self._pendingMetadata.append((handle, waiter))
        try:
            ti = await asyncio.wait_for(waiter, timeout=bittorrentConfig.metadataTimeout.value)
            torrentBytes = lt.bencode(lt.create_torrent(ti).generate())
        except asyncio.TimeoutError:
            raise TimeoutError("等待 magnet 元数据超时")
        finally:
            self._pendingMetadata.remove((handle, waiter))
            try:
                self._session.remove_torrent(handle)
            except Exception:
                pass

        return torrentBytes, ti, params.trackers.copy()

    # ── 对 Core:app 退出前优雅关闭(必须在事件循环停止前完成)─────────────
    def shutdown(self):
        if self._session is None:
            return
        try:
            coreService.runBlocking(self._shutdown(), timeout=15)
        except Exception as e:
            logger.opt(exception=e).warning("BitTorrent session 关闭异常")

    async def _shutdown(self):
        actives = list(self._active.values())
        if actives:
            await asyncio.gather(
                *(self._saveResume(active) for active in actives),
                return_exceptions=True,
            )

        if self._pump is not None:
            self._pump.cancel()
            try:
                await self._pump
            except asyncio.CancelledError:
                pass
            self._pump = None

        session, self._session = self._session, None
        if session is not None:
            for active in actives:
                try:
                    session.remove_torrent(active.handle)
                except Exception:
                    pass
        self._active.clear()

    # ── session / 泵 的拉起 ────────────────────────────────────────────────
    def _open(self):
        if self._session is None:
            self._session = lt.session(self._sessionSettings())
        if self._pump is None or self._pump.done():
            self._pump = asyncio.get_running_loop().create_task(self._pumpLoop())

    def _sessionSettings(self) -> dict:
        settings = {
            "user_agent": USER_AGENT,
            "listen_interfaces": f"0.0.0.0:{bittorrentConfig.listenPort.value}",
            "connections_limit": bittorrentConfig.connectionsLimit.value,
            "download_rate_limit": bittorrentConfig.downloadRateLimit.value,
            "upload_rate_limit": bittorrentConfig.uploadRateLimit.value,
            "enable_dht": bittorrentConfig.enableDHT.value,
            "enable_lsd": bittorrentConfig.enableLSD.value,
            "enable_upnp": bittorrentConfig.enableUPnP.value,
            "enable_natpmp": bittorrentConfig.enableNATPMP.value,
            "announce_to_all_trackers": True,
            "announce_to_all_tiers": True,
            "alert_mask": lt.alert.category_t.all_categories,
        }
        settings.update(self._proxySettings(getProxies()))
        return settings

    def _proxySettings(self, proxies: dict | None) -> dict:
        if not proxies:
            return {}
        proxyUrl = str(proxies.get("https") or proxies.get("http") or "").strip()
        if not proxyUrl:
            return {}
        parsed = urlsplit(proxyUrl)
        # 只接受 SOCKS5: HTTP/HTTPS/SOCKS4 不支持 UDP, 配上反而会拖垮 DHT 与 UDP tracker
        if parsed.scheme.lower() != "socks5" or not parsed.hostname or not parsed.port:
            return {}
        hasCredentials = bool(parsed.username or parsed.password)
        return {
            "proxy_type": lt.proxy_type_t.socks5_pw if hasCredentials else lt.proxy_type_t.socks5,
            "proxy_hostname": parsed.hostname,
            "proxy_port": parsed.port,
            "proxy_username": parsed.username or "",
            "proxy_password": parsed.password or "",
            "proxy_hostnames": True,
            "proxy_peer_connections": True,
            "proxy_tracker_connections": True,
            "force_proxy": False,
        }

    def _onLimitsChanged(self, _=None):
        if self._session is None:
            return
        self._session.apply_settings({
            "download_rate_limit": bittorrentConfig.downloadRateLimit.value,
            "upload_rate_limit": bittorrentConfig.uploadRateLimit.value,
            "connections_limit": bittorrentConfig.connectionsLimit.value,
        })

    # ── 把一条 torrent 加进 session ───────────────────────────────────────
    def _addTorrent(self, task: BTTask) -> lt.torrent_handle:
        params = None
        if task.resumeData:
            try:
                params = lt.read_resume_data(b64decode(task.resumeData))
            except Exception as e:
                logger.opt(exception=e).warning("读取 BitTorrent resume 数据失败,改用种子元数据 {}", task.title)

        if params is None:
            params = lt.add_torrent_params()
            params.ti = lt.torrent_info(b64decode(task.torrentData))
            params.flags |= lt.torrent_flags.update_subscribe

        params.save_path = str(task.path)
        params.storage_mode = (
            lt.storage_mode_t.storage_mode_allocate
            if bittorrentConfig.storageMode.value == "allocate"
            else lt.storage_mode_t.storage_mode_sparse
        )
        params.file_priorities = task.priorities()
        if bittorrentConfig.sequentialDownload.value:
            params.flags |= lt.torrent_flags.sequential_download
        else:
            params.flags &= ~lt.torrent_flags.sequential_download
        if task.trackers:
            params.trackers = task.trackers.copy()

        handle = self._addToSession(params)
        for file in task.files:
            mappedPath = task.mapPath(file)
            if mappedPath != file.path:
                handle.rename_file(file.index, mappedPath)
        return handle

    def _addToSession(self, params: lt.add_torrent_params) -> lt.torrent_handle:
        # 共享 session 里一个 info_hash 只能有一个种子: add_torrent 对重复会返回既有
        # handle, 之后误删它会连累正在下载的任务, 故在唯一的 add 入口前拦截
        if self._session.find_torrent(self._infoHash(params)).is_valid():
            raise RuntimeError("该种子已在下载中")
        return self._session.add_torrent(params)

    def _infoHash(self, params: lt.add_torrent_params) -> lt.sha1_hash:
        # ti 构造的 params 不填 info_hashes(实测), 只能从 ti 取; 磁力/resume 在 info_hashes
        if params.ti is not None:
            return params.ti.info_hashes().v1
        return params.info_hashes.v1

    def _prepareTarget(self, task: BTTask):
        target = Path(task.outputFolder)
        if target.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch() if task.isSingleFile else target.mkdir()

    def _saveMagnetFile(self, task: BTTask):
        if task.sourceType != "magnet" or not bittorrentConfig.saveMagnetTorrentFile.value:
            return
        torrentPath = task.magnetTorrentPath
        if torrentPath is None:
            return
        try:
            torrentPath.write_bytes(b64decode(task.torrentData))
        except Exception as e:
            logger.opt(exception=e).warning("保存 magnet 种子文件失败 {}", task.title)

    # ── 摘除 / 存 resume ──────────────────────────────────────────────────
    async def _removeTorrent(self, active: _ActiveTorrent):
        # 先存 resume(此刻仍在 _active 中, 泵才能把 alert 回填)再摘除
        await self._saveResume(active)
        self._active.pop(active.task.taskId, None)
        if self._session is not None:
            try:
                self._session.remove_torrent(active.handle)
            except Exception:
                pass

    async def _saveResume(self, active: _ActiveTorrent):
        if self._session is None:
            active.task.resumeData = ""
            return

        try:
            active.handle.save_resume_data(
                lt.save_resume_flags_t.flush_disk_cache | lt.save_resume_flags_t.save_info_dict
            )
        except Exception as e:
            logger.opt(exception=e).warning("保存 BitTorrent resume 数据失败 {}", active.task.title)
            active.task.resumeData = ""
            return

        active.resumeWaiter = asyncio.get_running_loop().create_future()
        try:
            await asyncio.wait_for(active.resumeWaiter, timeout=10)
        except asyncio.TimeoutError:
            logger.warning("等待 BitTorrent resume 数据超时 {}", active.task.title)
            active.task.resumeData = ""
        finally:
            active.resumeWaiter = None

    # ── 泵:一条循环驱动所有 torrent ──────────────────────────────────────
    async def _pumpLoop(self):
        # 一条循环驱动全部 torrent: 单个 torrent 的瞬时错误不该掀翻整条泵
        while self._session is not None:
            try:
                for alert in self._session.pop_alerts():
                    self._handleAlert(alert)
                for active in list(self._active.values()):
                    self._applyStatus(active)
            except Exception as e:
                logger.opt(exception=e).error("BitTorrent 泵循环异常")
            await asyncio.sleep(1)

    def _applyStatus(self, active: _ActiveTorrent):
        task = active.task
        status = active.handle.status()
        wasSeeding = task.isSeeding

        task.stateText = _STATE_TEXT.get(status.state.name, status.state.name)
        task.peerCount = status.num_peers
        task.seedCount = status.num_seeds
        task.isSeeding = status.is_seeding
        task.downloadRate = status.download_rate
        task.uploadRate = status.upload_rate
        task._updateSlot()

        downloaded = status.all_time_download or status.total_wanted_done or status.total_done
        task.shareRatioPercent = (status.all_time_upload / downloaded * 100) if downloaded > 0 else 0.0
        task.seedingTimeSeconds = active.seedingElapsed(
            task.isSeeding, int(status.seeding_duration.total_seconds())
        )

        task.stage.speed = status.download_rate
        task.stage.receivedBytes = status.total_wanted_done
        if status.total_wanted > 0:
            task.fileSize = status.total_wanted
            task.stage.progress = status.total_wanted_done / status.total_wanted * 100
        elif task.fileSize > 0:
            task.stage.progress = task.stage.receivedBytes / task.fileSize * 100
        else:
            task.stage.progress = 0

        task.updateProgress(active.handle.file_progress())

        if active.appliedSelectionVersion != task.fileSelectionVersion:
            active.handle.prioritize_files(task.priorities())
            active.appliedSelectionVersion = task.fileSelectionVersion

        if wasSeeding != task.isSeeding:
            coreService.rebalance()

        if self._shouldStopSeeding(task) and not active.done.done():
            active.done.set_result(None)

    def _shouldStopSeeding(self, task: BTTask) -> bool:
        if not task.isSeeding:
            return False

        ratioLimit = bittorrentConfig.seedRatioLimitPercent.value
        if ratioLimit > 0 and task.shareRatioPercent >= ratioLimit:
            logger.info(
                "{} 自动暂停做种: 分享率达到 {:.2f}% / {}%",
                task.title, task.shareRatioPercent, ratioLimit,
            )
            return True

        timeLimitMinutes = bittorrentConfig.seedTimeLimitMinutes.value
        if timeLimitMinutes > 0 and task.seedingTimeSeconds >= timeLimitMinutes * 60:
            logger.info(
                "{} 自动暂停做种: 做种时间达到 {} / {} 分钟",
                task.title, round(task.seedingTimeSeconds / 60), timeLimitMinutes,
            )
            return True

        return False

    def _handleAlert(self, alert: lt.alert):
        if isinstance(alert, lt.metadata_received_alert):
            self._resolveMetadata(alert)
            return

        if isinstance(alert, lt.save_resume_data_alert):
            active = self._activeOf(alert.handle)
            if active is not None and active.resumeWaiter is not None and not active.resumeWaiter.done():
                active.task.resumeData = b64encode(lt.write_resume_data_buf(alert.params)).decode()
                active.resumeWaiter.set_result(True)
            return

        if isinstance(alert, lt.save_resume_data_failed_alert):
            active = self._activeOf(alert.handle)
            if active is not None and active.resumeWaiter is not None and not active.resumeWaiter.done():
                logger.warning("保存 BitTorrent resume 数据失败 {}: {}", active.task.title, alert.message())
                active.task.resumeData = ""
                active.resumeWaiter.set_result(False)
            return

        if isinstance(alert, lt.file_completed_alert):
            active = self._activeOf(alert.handle)
            if active is not None:
                for file in active.task.files:
                    if file.index == alert.index:
                        file.completed = True
                        file.downloadedBytes = file.size
                        break
            return

        if isinstance(alert, lt.fastresume_rejected_alert):
            active = self._activeOf(alert.handle)
            if active is not None:
                active.task.resumeData = ""
            logger.warning("BitTorrent fastresume 被拒绝: {}", alert.message())
            return

        if isinstance(alert, _ERROR_ALERTS):
            self._failTorrent(alert)

    def _resolveMetadata(self, alert: lt.metadata_received_alert):
        for handle, waiter in self._pendingMetadata:
            if handle == alert.handle and not waiter.done():
                ti = handle.torrent_file()
                if ti is not None and ti.is_valid():
                    waiter.set_result(ti)
                else:
                    waiter.set_exception(RuntimeError("magnet 元数据无效"))
                return

    def _failTorrent(self, alert: lt.alert):
        active = self._activeOf(alert.handle)
        if active is not None:
            if not active.done.done():
                active.done.set_exception(RuntimeError(alert.message()))
            return
        for handle, waiter in self._pendingMetadata:
            if handle == alert.handle and not waiter.done():
                waiter.set_exception(RuntimeError(alert.message()))
                return

    def _activeOf(self, handle: lt.torrent_handle) -> _ActiveTorrent | None:
        for active in self._active.values():
            if active.handle == handle:
                return active
        return None


btSessionService = BTSessionService()
