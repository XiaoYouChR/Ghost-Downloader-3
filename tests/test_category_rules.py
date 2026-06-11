from app.gui.category_rules import CategoryRuleModel


def _model(rules=None):
    saved = []
    model = CategoryRuleModel(rules or [], onChanged=saved.append)
    return model, saved


def test_addParsesExtensionsAndPersists(qapp):
    model, saved = _model()
    model.add("我的视频", "mp4, .mkv，avi", "{default}/MyVideo", "VIDEO")
    assert model.rowCount() == 1
    assert model.data(model.index(0, 0), CategoryRuleModel.NameRole) == "我的视频"
    assert model.data(model.index(0, 0), CategoryRuleModel.ExtensionsRole) == "mp4, mkv, avi"  # 去点/小写/全角逗号
    assert saved[-1][0]["extensions"] == ["mp4", "mkv", "avi"]
    assert saved[-1][0]["categoryId"].startswith("cat_")


def test_addRejectsBlankNameOrNoExtensions(qapp):
    model, saved = _model()
    model.add("   ", "mp4", "", "VIDEO")  # 名字空
    model.add("名字", "  ", "", "VIDEO")  # 没扩展名
    assert model.rowCount() == 0
    assert saved == []


def test_removeAtDropsAndPersists(qapp):
    model, saved = _model([
        {"categoryId": "cat_1", "name": "A", "icon": "VIDEO", "folder": "", "extensions": ["mp4"]},
        {"categoryId": "cat_2", "name": "B", "icon": "MUSIC", "folder": "", "extensions": ["mp3"]},
    ])
    model.removeAt(0)
    assert model.rowCount() == 1
    assert model.data(model.index(0, 0), CategoryRuleModel.NameRole) == "B"
    assert saved[-1] == [{"categoryId": "cat_2", "name": "B", "icon": "MUSIC", "folder": "", "extensions": ["mp3"]}]
