from app.gui.app import MainWindow


def test_mainWindow_loadsQml(qapp):
    # 壳冒烟：MainWindow 加载 Main.qml 成功。
    # addTask 的真下载路径默认接 coreService（需起线程/触网），其行为由 spine 测试用 fake 覆盖。
    window = MainWindow()

    assert window.engine.rootObjects()
