from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from RinUI.core.config import RINUI_PATH

from app.gui.task_list import TaskFilter

QML_DIR = Path(__file__).resolve().parents[1] / "app" / "gui" / "qml"

_QML = b"""
import QtQuick

Item {
    width: 200; height: 200
    ListView {
        objectName: "list"
        anchors.fill: parent
        model: taskList
        delegate: Item { width: 1; height: 1; property string shown: title }
    }
}
"""


def test_taskList_rendersInQmlListView(spine):
    # gui 渲染冒烟：TaskList 喂给真 QML ListView，零报错加载且行数对得上。
    spine.backend.addTask("https://example.com/a.mp4")
    spine.backend.addTask("https://example.com/b.mp4")

    qmlEngine = QQmlEngine()
    qmlEngine.rootContext().setContextProperty("taskList", spine.taskList)
    component = QQmlComponent(qmlEngine)
    component.setData(_QML, QUrl())
    assert component.errors() == [], component.errorString()

    root = component.create()
    listView = root.findChild(QObject, "list")
    assert listView.property("count") == 2


@pytest.mark.parametrize("qmlFile", ["TaskPage.qml", "SettingsPage.qml", "TaskCard.qml"])
def test_realQmlPageLoadsWithoutError(spine, qmlFile):
    # 渲染期冒烟：每个真实 .qml 当组件加载，零加载错误。
    # 挡住「只读属性误赋」这类直到窗口真显示、页面真渲染才暴露的 QML 加载失败。
    spine.backend.addTask("https://example.com/a.mp4")

    qmlEngine = QQmlEngine()
    qmlEngine.addImportPath(str(RINUI_PATH))
    taskFilter = TaskFilter(spine.taskList)
    context = qmlEngine.rootContext()
    context.setContextProperty("backend", spine.backend)
    context.setContextProperty("taskList", spine.taskList)
    context.setContextProperty("taskFilter", taskFilter)

    component = QQmlComponent(qmlEngine, QUrl.fromLocalFile(str(QML_DIR / qmlFile)))
    assert component.errors() == [], component.errorString()
    assert component.create() is not None
