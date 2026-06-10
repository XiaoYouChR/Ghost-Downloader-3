from app.gui.user_agents import UserAgentModel


def _model(items=None):
    saved = []
    model = UserAgentModel(items or [{"name": "A", "value": "ua-a"}], onChanged=saved.append)
    return model, saved


def test_addAppendsAndPersists(qapp):
    model, saved = _model()
    model.add("B", "ua-b")
    assert model.rowCount() == 2
    assert model.data(model.index(1, 0), UserAgentModel.NameRole) == "B"
    assert saved[-1] == [{"name": "A", "value": "ua-a"}, {"name": "B", "value": "ua-b"}]


def test_removeAtDropsAndPersists(qapp):
    model, saved = _model([{"name": "A", "value": "a"}, {"name": "B", "value": "b"}])
    model.removeAt(0)
    assert model.rowCount() == 1
    assert model.data(model.index(0, 0), UserAgentModel.NameRole) == "B"
    assert saved[-1] == [{"name": "B", "value": "b"}]


def test_addRejectsBlank(qapp):
    model, saved = _model()
    model.add("   ", "")
    assert model.rowCount() == 1  # 空名/空值不收
    assert saved == []


def test_removeAtIgnoresOutOfRange(qapp):
    model, saved = _model()
    model.removeAt(5)
    assert model.rowCount() == 1
    assert saved == []
