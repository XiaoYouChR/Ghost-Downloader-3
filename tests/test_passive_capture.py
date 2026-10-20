from __future__ import annotations

import json

from app.config.cfg import cfg
from app.config.paths import APP_DATA_DIR
from app.models.pack import PackServices
from http_pack.pack import HttpPack
from huggingface_pack.pack import HuggingFacePack

MODEL_URL = "https://huggingface.co/org/repo/resolve/main/model.zip"


def test_match_skips_ignored_pack(engine):
    services = PackServices(coroutineRunner=engine.coroutineRunner, speedMeter=engine.speedMeter)
    engine.featureService.register(HuggingFacePack(services))
    engine.featureService.register(HttpPack(services))
    assert engine.featureService.matchPassive(MODEL_URL)

    configFile = APP_DATA_DIR / "UserConfig.json"
    config = json.loads(configFile.read_text(encoding="utf-8"))
    config["Software"] = {"ClipboardIgnoredPacks": ["huggingface"]}
    configFile.write_text(json.dumps(config), encoding="utf-8")
    cfg.load(configFile)

    assert not engine.featureService.matchPassive(MODEL_URL)
