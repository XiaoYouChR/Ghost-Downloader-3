from __future__ import annotations

import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from app.config.cfg import cfg
from app.services.update_service import (
    UpdateInfo, UpdateService, UpdateState, installPendingPacks,
)
from app.startup import refreshUpdatesAtStartup
from app.view.dialogs.pack_info import MAX_VISIBLE_PACK_ROWS, PACK_ROW_HEIGHT, PackInfoDialog


class StubUpdateService:
    def __init__(self):
        self.refreshes: list[tuple[bool, bool]] = []

    def refresh(self, *, shouldRefreshApp: bool, shouldRefreshPacks: bool) -> None:
        self.refreshes.append((shouldRefreshApp, shouldRefreshPacks))


class StubPackUpdateService(QObject):
    changed = Signal(object)
    packsRefreshed = Signal(int, bool)

    def __init__(self):
        super().__init__()
        self.downloads: list[str] = []

    def refresh(self, *, shouldRefreshApp: bool, shouldRefreshPacks: bool) -> None:
        pass

    def download(self, targetId: str) -> None:
        self.downloads.append(targetId)


class StubPack:
    pass


def setUpdatePolicy(monkeypatch, *, isCompiled: bool, hasMarker: bool,
                    shouldRefreshApp: bool, shouldRefreshPacks: bool) -> None:
    import app.config.paths as paths

    monkeypatch.setattr(paths, "IS_COMPILED", isCompiled)
    monkeypatch.setattr(paths, "hasNoAutoUpdateMarker", lambda: hasMarker)
    monkeypatch.setattr(cfg.shouldCheckUpdateAtStartup, "value", shouldRefreshApp)
    monkeypatch.setattr(cfg.shouldAutoUpdatePacks, "value", shouldRefreshPacks)


def test_source_build_disables_automatic_updates(monkeypatch):
    from loguru import logger

    setUpdatePolicy(
        monkeypatch,
        isCompiled=False,
        hasMarker=False,
        shouldRefreshApp=True,
        shouldRefreshPacks=True,
    )
    saved = []
    messages = []
    monkeypatch.setattr(cfg, "set", lambda item, value: saved.append((item, value)))
    monkeypatch.setattr(logger, "info", messages.append)
    updateService = StubUpdateService()

    refreshUpdatesAtStartup(updateService)

    assert saved == []
    assert updateService.refreshes == []
    assert messages == ["App and feature pack auto updates disabled in source mode"]


def test_marker_disables_only_app_refresh(monkeypatch):
    setUpdatePolicy(
        monkeypatch,
        isCompiled=True,
        hasMarker=True,
        shouldRefreshApp=True,
        shouldRefreshPacks=True,
    )
    saved = []
    monkeypatch.setattr(cfg, "set", lambda item, value: saved.append((item, value)))
    updateService = StubUpdateService()

    refreshUpdatesAtStartup(updateService)

    assert saved == [(cfg.shouldCheckUpdateAtStartup, False)]
    assert updateService.refreshes == [(False, True)]


def test_compiled_build_refreshes_enabled_targets(monkeypatch):
    setUpdatePolicy(
        monkeypatch,
        isCompiled=True,
        hasMarker=False,
        shouldRefreshApp=True,
        shouldRefreshPacks=False,
    )
    updateService = StubUpdateService()

    refreshUpdatesAtStartup(updateService)

    assert updateService.refreshes == [(True, False)]


def test_disabled_targets_do_not_refresh(monkeypatch):
    setUpdatePolicy(
        monkeypatch,
        isCompiled=False,
        hasMarker=False,
        shouldRefreshApp=True,
        shouldRefreshPacks=False,
    )
    updateService = StubUpdateService()

    refreshUpdatesAtStartup(updateService)

    assert updateService.refreshes == []


def test_source_mode_does_not_write_pack_updates(monkeypatch, tmp_path):
    import app.services.update_service as updateServiceModule

    featuresDir = tmp_path / "features"
    installedDir = featuresDir / "http_pack"
    pendingDir = featuresDir / "http_pack_pending"
    installedDir.mkdir(parents=True)
    pendingDir.mkdir()
    (installedDir / "version.txt").write_text("installed", encoding="utf-8")
    (pendingDir / "version.txt").write_text("pending", encoding="utf-8")

    stagingDir = tmp_path / "staging"
    stagingDir.mkdir()
    with zipfile.ZipFile(stagingDir / "bili_pack.zip", "w") as archive:
        archive.writestr("version.txt", "downloaded")

    monkeypatch.setattr(updateServiceModule, "IS_COMPILED", False)
    monkeypatch.setattr(updateServiceModule, "FEATURES_DIR", featuresDir)
    monkeypatch.setattr(updateServiceModule, "STAGING_DIR", stagingDir)

    installPendingPacks(featuresDir)
    UpdateService(None)._applyPack("bili_pack")

    assert (installedDir / "version.txt").read_text(encoding="utf-8") == "installed"
    assert (pendingDir / "version.txt").read_text(encoding="utf-8") == "pending"
    assert not (featuresDir / "bili_pack_pending").exists()


@pytest.mark.asyncio
async def test_update_retry_clears_previous_failure(monkeypatch):
    service = UpdateService(None)
    service._infos["http_pack"] = UpdateInfo(
        targetId="http_pack",
        label="HttpPack 2.0.0",
        currentVersion="1.0.0",
        latestVersion="2.0.0",
        state=UpdateState.FAILED,
        progress=65,
        error="network error",
    )
    monkeypatch.setattr(service, "_downloadPack", AsyncMock())
    infos = []
    service.changed.connect(infos.append)

    await service._download("http_pack")

    assert infos[0].state == UpdateState.DOWNLOADING
    assert infos[0].progress == 0
    assert infos[0].error == ""


def test_pack_panel_uses_fixed_rows_and_scrolls(qapp, qtbot):
    parent = QWidget()
    parent.resize(900, 800)
    qtbot.addWidget(parent)

    packs = []
    for index in range(MAX_VISIBLE_PACK_ROWS + 4):
        pack = StubPack()
        pack.manifest = SimpleNamespace(name=f"pack_{index}", version="1.0.0")
        packs.append(pack)

    dialog = PackInfoDialog(packs, StubPackUpdateService(), parent)
    dialog.show()
    qapp.processEvents()

    assert all(row.height() == PACK_ROW_HEIGHT for row in dialog._rows.values())
    assert all(row.statusLabel.text() == "✓" for row in dialog._rows.values())
    assert all(row.statusLabel.lightColor.name() == "#0f7b0f" for row in dialog._rows.values())
    assert dialog.packListArea.height() == MAX_VISIBLE_PACK_ROWS * PACK_ROW_HEIGHT
    assert dialog.packListArea.verticalScrollBar().maximum() > 0


def test_pack_update_button_always_updates_in_compiled_build(monkeypatch, qapp, qtbot):
    import app.view.dialogs.pack_info as packInfoModule

    parent = QWidget()
    qtbot.addWidget(parent)
    pack = StubPack()
    pack.manifest = SimpleNamespace(name="http_pack", version="1.0.0")
    monkeypatch.setattr(packInfoModule, "IS_COMPILED", True)
    monkeypatch.setattr(cfg.shouldAutoUpdatePacks, "value", False)
    monkeypatch.setattr(cfg, "set", lambda item, value: None)
    updateService = StubPackUpdateService()

    dialog = PackInfoDialog([pack], updateService, parent)

    assert dialog.checkButton.text() == "更新功能包"
    assert dialog.checkButton.isEnabled()

    dialog._isRefreshingPacks = True
    dialog._onUpdateChanged(SimpleNamespace(
        targetId="http_pack",
        state=UpdateState.AVAILABLE,
    ))

    assert updateService.downloads == ["http_pack"]
    assert dialog._rows["http_pack"].statusLabel.text() == "↑"
    assert dialog._rows["http_pack"].statusLabel.lightColor.name() == "#9d5d00"

    monkeypatch.setattr(packInfoModule, "IS_COMPILED", False)
    sourceUpdateService = StubPackUpdateService()
    sourceDialog = PackInfoDialog([pack], sourceUpdateService, parent)
    sourceDialog._isRefreshingPacks = True
    sourceDialog._onUpdateChanged(SimpleNamespace(
        targetId="http_pack",
        state=UpdateState.AVAILABLE,
    ))

    assert not sourceDialog.checkButton.isEnabled()
    assert sourceUpdateService.downloads == []


@pytest.mark.asyncio
async def test_pack_refresh_does_not_check_app(monkeypatch, tmp_path, qapp):
    import app.services.update_service as updateServiceModule

    packDir = tmp_path / "http_pack"
    packDir.mkdir()
    (packDir / "manifest.toml").write_text(
        '[pack]\nentry = "pack.py"\nclass = "HttpPack"\n'
        'version = "1.0.0"\ngdMinVersion = "4.0.0"\n',
        encoding="utf-8",
    )
    (packDir / "pack.py").touch()
    monkeypatch.setattr(updateServiceModule, "FEATURES_DIR", tmp_path)
    monkeypatch.setattr(updateServiceModule, "IS_ANDROID", False)

    service = UpdateService(None)
    service._fetchVersions = AsyncMock(return_value={
        "app": {"version": "999.0.0"},
        "packs": {"http_pack": {"version": "2.0.0"}},
    })
    infos = []
    results = []
    service.changed.connect(infos.append)
    service.packsRefreshed.connect(lambda count, error: results.append((count, error)))

    await service._refresh(False, True)

    assert [(info.targetId, info.state) for info in infos] == [
        ("http_pack", UpdateState.AVAILABLE),
    ]
    assert results == [(1, False)]


@pytest.mark.asyncio
async def test_app_refresh_does_not_check_packs(monkeypatch, tmp_path, qapp):
    import app.services.update_service as updateServiceModule

    monkeypatch.setattr(updateServiceModule, "FEATURES_DIR", tmp_path)
    monkeypatch.setattr(updateServiceModule, "IS_ANDROID", False)
    service = UpdateService(None)
    service._fetchVersions = AsyncMock(return_value={
        "app": {"version": "999.0.0"},
        "packs": {"http_pack": {"version": "2.0.0"}},
    })
    infos = []
    results = []
    service.changed.connect(infos.append)
    service.packsRefreshed.connect(lambda count, error: results.append((count, error)))

    await service._refresh(True, False)

    assert [info.targetId for info in infos] == ["app", "app"]
    assert infos[-1].state == UpdateState.AVAILABLE
    assert results == []


@pytest.mark.asyncio
async def test_pack_refresh_reports_fetch_error(monkeypatch, qapp):
    import app.services.update_service as updateServiceModule

    monkeypatch.setattr(updateServiceModule, "IS_ANDROID", False)
    service = UpdateService(None)
    service._fetchVersions = AsyncMock(return_value=None)
    results = []
    service.packsRefreshed.connect(lambda count, error: results.append((count, error)))

    await service._refresh(False, True)

    assert results == [(0, True)]
