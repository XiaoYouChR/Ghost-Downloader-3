from __future__ import annotations

import json

from app.config.cfg import cfg
from app.config.paths import APP_DATA_DIR
from app.models.pack import PackServices
from huggingface_pack.pack import HuggingFacePack
from m3u8_pack.pack import M3U8Pack

MODEL_URL = "https://huggingface.co/org/repo/resolve/main/model.zip"


def test_match_skips_ignored_pack(engine, httpPack):
    services = PackServices(coroutineRunner=engine.coroutineRunner, speedMeter=engine.speedMeter)
    engine.featureService.register(HuggingFacePack(services))
    assert engine.featureService.matchPassive(MODEL_URL)

    configFile = APP_DATA_DIR / "UserConfig.json"
    config = json.loads(configFile.read_text(encoding="utf-8"))
    config["Software"] = {"ClipboardIgnoredPacks": ["huggingface"]}
    configFile.write_text(json.dumps(config), encoding="utf-8")
    cfg.load(configFile)

    assert not engine.featureService.matchPassive(MODEL_URL)


def test_match_passive_skips_broken_link(engine, httpPack):
    assert not engine.featureService.matchPassive("http://[abc")


def test_match_passive_skips_drive_path(engine):
    services = PackServices(coroutineRunner=engine.coroutineRunner, speedMeter=engine.speedMeter)
    engine.featureService.register(M3U8Pack(services))
    assert engine.featureService.match("C:\\a.m3u8")

    assert not engine.featureService.matchPassive("C:\\a.m3u8")
