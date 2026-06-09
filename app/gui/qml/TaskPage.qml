import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI

// 下载任务页：工具栏（全部开始/暂停）、加链接、任务列表。所有动作经 backend 发命令。
FluentPage {
    id: taskPage
    title: "下载任务"

    property string pendingDelete: ""

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Button { text: "全部开始"; onClicked: backend.startAll() }
            Button { text: "全部暂停"; onClicked: backend.pauseAll() }
            Item { Layout.fillWidth: true }
            TextField {
                Layout.preferredWidth: 200
                placeholderText: "搜索任务"
                onTextChanged: taskFilter.keyword = text
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            TextField {
                id: urlInput
                Layout.fillWidth: true
                placeholderText: "粘贴下载链接，回车或点添加"
                onAccepted: addCurrent()
            }
            Button {
                text: "添加"
                onClicked: addCurrent()
            }
        }

        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 6
            model: taskFilter
            delegate: TaskCard {
                width: ListView.view.width
                taskId: model.taskId
                fileName: model.title
                status: model.status
                running: model.running
                progress: model.progress
                speedText: model.speedText
                progressText: model.progressText
                onDeleteRequested: function(taskId) {
                    taskPage.pendingDelete = taskId
                    deleteDialog.open()
                }
            }
        }
    }

    Dialog {
        id: deleteDialog
        title: "删除任务"
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        Text { text: "确定删除这个任务吗？" }
        onAccepted: backend.remove(taskPage.pendingDelete)
        Component.onCompleted: {
            const ok = standardButton(Dialog.Ok)
            if (ok) ok.text = "删除"
            const cancel = standardButton(Dialog.Cancel)
            if (cancel) cancel.text = "取消"
        }
    }

    function addCurrent() {
        if (urlInput.text.trim() === "")
            return
        backend.addTask(urlInput.text.trim())
        urlInput.text = ""
    }
}
