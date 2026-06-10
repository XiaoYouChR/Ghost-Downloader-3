from app.gui.task_list import TaskFilter, TaskList


def _filter() -> TaskFilter:
    tasks = TaskList()
    tasks.reset([
        {"taskId": "1", "title": "banana.zip", "status": "COMPLETED", "createdAt": 100},
        {"taskId": "2", "title": "apple.mp4", "status": "RUNNING", "createdAt": 200},
        {"taskId": "3", "title": "cherry.exe", "status": "PAUSED", "createdAt": 150},
    ])
    proxy = TaskFilter(tasks)
    proxy._source = tasks  # Python 引用保住 source，测试期间不被回收
    return proxy


def test_keyword_filtersByTitle(qapp):
    proxy = _filter()
    proxy.keyword = "apple"
    assert proxy.rowCount() == 1


def test_statusFilter_activeHidesCompleted(qapp):
    proxy = _filter()
    proxy.statusFilter = "active"
    assert proxy.rowCount() == 2  # RUNNING + PAUSED，藏掉 COMPLETED


def test_statusFilter_completeShowsOnlyCompleted(qapp):
    proxy = _filter()
    proxy.statusFilter = "complete"
    assert proxy.rowCount() == 1


def test_statusFilter_andKeywordCombine(qapp):
    proxy = _filter()
    proxy.statusFilter = "active"
    proxy.keyword = "cherry"
    assert proxy.rowCount() == 1


def _titles(proxy) -> list:
    return [proxy.data(proxy.index(i, 0), TaskList.TitleRole) for i in range(proxy.rowCount())]


def test_sortMode_defaultTimeNewestFirst(qapp):
    proxy = _filter()  # createdAt 200/150/100 → apple, cherry, banana
    assert _titles(proxy) == ["apple.mp4", "cherry.exe", "banana.zip"]


def test_sortMode_nameSortsByTitle(qapp):
    proxy = _filter()
    proxy.sortMode = "name"
    assert _titles(proxy) == ["apple.mp4", "banana.zip", "cherry.exe"]
