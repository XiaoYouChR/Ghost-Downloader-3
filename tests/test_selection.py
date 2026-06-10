from app.gui.task_list import TaskList


def _taskId(spine, row=0):
    return spine.taskList.data(spine.taskList.index(row, 0), TaskList.IdRole)


def test_toggleSelect_addsThenRemoves(spine):
    spine.backend.addTask("https://example.com/a.mp4")
    taskId = _taskId(spine)

    spine.taskList.toggleSelect(taskId)
    assert spine.taskList.selectedCount == 1
    assert spine.taskList.data(spine.taskList.index(0, 0), TaskList.SelectedRole) is True

    spine.taskList.toggleSelect(taskId)
    assert spine.taskList.selectedCount == 0


def test_selectAll_selectsEveryItem(spine):
    spine.backend.addTask("https://example.com/a.mp4")
    spine.backend.addTask("https://example.com/b.mp4")

    spine.taskList.selectAll()

    assert spine.taskList.selectedCount == 2


def test_setSelectionMode_offClearsSelection(spine):
    spine.backend.addTask("https://example.com/a.mp4")
    spine.taskList.setSelectionMode(True)
    spine.taskList.selectAll()

    spine.taskList.setSelectionMode(False)

    assert spine.taskList.selectedCount == 0


def test_removeSelected_removesAllSelected(spine):
    spine.backend.addTask("https://example.com/a.mp4")
    spine.backend.addTask("https://example.com/b.mp4")
    spine.taskList.selectAll()

    spine.backend.removeSelected()

    assert spine.taskList.rowCount() == 0
    assert len(spine.store.removed) == 2
