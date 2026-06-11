from app.services.feature_service import featureService


class _FakeConfig:
    settingsTitle = "假组"

    def __init__(self):
        self.applied = []

    def settingsSchema(self):
        return [{"kind": "switch", "label": "开关", "key": "flag", "value": False}]

    def applySetting(self, key, value):
        self.applied.append((key, value))


class _FakePack:
    packId = "fake"
    priority = 0

    def __init__(self):
        self.config = _FakeConfig()


def _withFakePack():
    pack = _FakePack()
    featureService._packs["__test_fake__"] = pack
    return pack


def test_packSettings_collectsPackGroups():
    pack = _withFakePack()
    try:
        groups = featureService.packSettings()
        group = next(g for g in groups if g["packId"] == "fake")
        assert group["title"] == "假组"
        assert group["schema"][0]["key"] == "flag"
    finally:
        del featureService._packs["__test_fake__"]


def test_applyPackSetting_routesToMatchingPackConfig():
    pack = _withFakePack()
    try:
        featureService.applyPackSetting("fake", "flag", True)
        assert pack.config.applied == [("flag", True)]
    finally:
        del featureService._packs["__test_fake__"]
