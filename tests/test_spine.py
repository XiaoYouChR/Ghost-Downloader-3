from app.protocol.link import MemoryLink
from app.engine.engine import Engine
from app.gui.backend import Backend
from app.gui.task_list import TaskList


def test_addTask_appearsInGuiModel(qapp):
    # 脊柱 tracer: gui 发 addTask 命令 → 过 link → engine 加任务并回发 taskAdded
    # → gui 的 TaskList 出现这条任务。证明命令/事件经 link 端到端走通。
    link = MemoryLink()
    taskList = TaskList()
    backend = Backend(link, taskList)
    engine = Engine(link)
    link.connect(engine.receive, backend.receive)

    backend.addTask("https://example.com/movie.mp4")

    assert taskList.rowCount() == 1
    index = taskList.index(0, 0)
    assert taskList.data(index, TaskList.TitleRole) == "movie.mp4"
