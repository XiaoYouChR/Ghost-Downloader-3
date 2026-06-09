from app.gui.task_list import TaskFilter, TaskList


def test_filter_keywordMatchesTitle(spine):
    # 关键词只筛标题含它的任务；过滤逻辑在 Python 侧，TaskList 本身不动。
    spine.backend.addTask("https://example.com/movie.mp4")
    spine.backend.addTask("https://example.com/song.mp3")
    filter = TaskFilter(spine.taskList)

    filter.keyword = "movie"

    assert filter.rowCount() == 1
    assert filter.data(filter.index(0, 0), TaskList.TitleRole) == "movie.mp4"


def test_filter_emptyKeywordShowsAll(spine):
    spine.backend.addTask("https://example.com/movie.mp4")
    spine.backend.addTask("https://example.com/song.mp3")
    filter = TaskFilter(spine.taskList)

    filter.keyword = ""

    assert filter.rowCount() == 2


def test_filter_sortsNewestFirst(qapp):
    # createdAt 大（新）的排前面。
    taskList = TaskList()
    taskList.reset([
        {"taskId": "a", "title": "old", "status": "WAITING", "createdAt": 100},
        {"taskId": "b", "title": "new", "status": "WAITING", "createdAt": 200},
    ])
    filter = TaskFilter(taskList)

    assert filter.data(filter.index(0, 0), TaskList.TitleRole) == "new"
    assert filter.data(filter.index(1, 0), TaskList.TitleRole) == "old"
