from PySide6.QtCore import QObject, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine

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
