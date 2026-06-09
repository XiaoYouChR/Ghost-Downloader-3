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
