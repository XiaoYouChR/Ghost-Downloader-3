from __future__ import annotations

import json

from app.config.cfg import cfg


def test_load_keeps_unavailable_folder_and_later_settings(config, blockedFolder, tmp_path):
    configFile = tmp_path / "UserConfig.json"
    configFile.write_text(json.dumps({"GeneralDownload": {
        "DownloadFolder": str(blockedFolder),
        "RecentFolders": [str(blockedFolder)],
        "MaxTaskNum": 5,
    }}), encoding="utf-8")

    cfg.load(configFile)

    assert cfg.downloadFolder.value == str(blockedFolder)
    assert cfg.recentFolders.value == [str(blockedFolder)]
    assert cfg.maxTaskNum.value == 5
