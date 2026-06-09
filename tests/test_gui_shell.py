from app.gui.app import MainWindow


def test_mainWindow_loadsAndBackendDrivesModel(qapp):
    # 壳冒烟：MainWindow 加载 Main.qml 成功，backend 加任务进 TaskList。
    window = MainWindow()

    assert window.engine.rootObjects()

    window._backend.addTask("https://example.com/movie.mp4")
    assert window._taskList.rowCount() == 1
