from app.gui.file_selection import FileSelection


def test_selectedIndexes_listsCheckedFiles(qapp):
    fs = FileSelection([
        {"index": 0, "relativePath": "a.txt", "size": 100, "selected": True},
        {"index": 1, "relativePath": "b.txt", "size": 200, "selected": False},
    ])
    assert fs.selectedIndexes() == [0]


def test_toggle_flipsSelected(qapp):
    fs = FileSelection([{"index": 5, "relativePath": "a.txt", "size": 100, "selected": True}])

    fs.toggle(0)
    assert fs.selectedIndexes() == []

    fs.toggle(0)
    assert fs.selectedIndexes() == [5]


def test_data_exposesPathSizeSelected(qapp):
    fs = FileSelection([{"index": 0, "relativePath": "movie.mp4", "size": 1024, "selected": True}])
    index = fs.index(0, 0)

    assert fs.data(index, FileSelection.PathRole) == "movie.mp4"
    assert fs.data(index, FileSelection.SizeTextRole) == "1.00 KB"
    assert fs.data(index, FileSelection.SelectedRole) is True


def test_editFiles_buildsModelFromTaskFiles(spine):
    # 卡片「选择文件」→ backend.editFiles 从任务的 files 建出对话框模型。
    spine.taskList.reset([{
        "taskId": "t1", "title": "torrent", "status": "WAITING", "createdAt": 1,
        "files": [
            {"index": 0, "relativePath": "a.mkv", "size": 100, "selected": True},
            {"index": 1, "relativePath": "b.srt", "size": 10, "selected": True},
        ],
    }])

    spine.backend.editFiles("t1")
    assert spine.backend.filesModel.rowCount() == 2

    spine.backend.filesModel.toggle(1)
    assert spine.backend.filesModel.selectedIndexes() == [0]
