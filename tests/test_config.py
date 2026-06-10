from app.engine.config import Config, Setting
from app.engine.settings import GLOBAL_SETTINGS


def test_config_returnsDefaultThenStoredValue(tmp_path, qapp):
    # 未设过时返回默认；set 之后返回新值。
    config = Config([Setting("maxTaskNum", 3)], tmp_path / "config.json")
    assert config.value("maxTaskNum") == 3

    config.set("maxTaskNum", 5)
    assert config.value("maxTaskNum") == 5


def test_config_emitsChangedOnSet(tmp_path, qapp):
    # set 改了值就发 changed(key)，引擎据此热应用（如 maxTaskNum 触发 rebalance）。
    config = Config([Setting("maxTaskNum", 3)], tmp_path / "config.json")
    seen: list[str] = []
    config.changed.connect(seen.append)

    config.set("maxTaskNum", 5)

    assert seen == ["maxTaskNum"]


def test_config_rejectsInvalidValue(tmp_path, qapp):
    # 在边界校验：越界的值不写入、不发 changed，保住旧值。
    config = Config([Setting("maxTaskNum", 3, validate=lambda v: 1 <= v <= 10)], tmp_path / "config.json")
    seen: list[str] = []
    config.changed.connect(seen.append)

    config.set("maxTaskNum", 999)

    assert config.value("maxTaskNum") == 3
    assert seen == []


def test_config_silentOnUnchangedValue(tmp_path, qapp):
    # 值没变就不发 changed，避免引擎做无谓的热应用（如空 rebalance）。
    config = Config([Setting("maxTaskNum", 3)], tmp_path / "config.json")
    config.set("maxTaskNum", 5)
    seen: list[str] = []
    config.changed.connect(seen.append)

    config.set("maxTaskNum", 5)

    assert seen == []


def test_config_persistsAcrossReload(tmp_path, qapp):
    # set 后落盘；新建同路径的 Config 加载后值还在（gui/engine 重启不丢配置）。
    path = tmp_path / "config.json"
    config = Config([Setting("maxTaskNum", 3)], path)
    config.set("maxTaskNum", 7)

    reloaded = Config([Setting("maxTaskNum", 3)], path)
    reloaded.load()

    assert reloaded.value("maxTaskNum") == 7


def test_globalSettings_defaultsAndValidation(tmp_path, qapp):
    # 引擎全局 schema：默认对齐旧 cfg，校验器拦住越界/非法值。
    config = Config(GLOBAL_SETTINGS, tmp_path / "config.json")
    assert config.value("preBlockNum") == 8
    assert config.value("customThemeMode") == "System"

    config.set("preBlockNum", 9999)  # 越界
    assert config.value("preBlockNum") == 8

    config.set("customThemeMode", "Dark")
    assert config.value("customThemeMode") == "Dark"
    config.set("customThemeMode", "Neon")  # 非法主题
    assert config.value("customThemeMode") == "Dark"
