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
            Button { text: "选择"; onClicked: taskList.setSelectionMode(true) }
            Button { text: "清空已完成"; onClicked: backend.clearCompleted() }
            Item { Layout.fillWidth: true }
            Text {
                text: backend.globalSpeedText
                visible: backend.globalSpeedText !== ""
                opacity: 0.8
            }
            TextField {
                Layout.preferredWidth: 200
                placeholderText: "搜索任务"
                onTextChanged: taskFilter.keyword = text
            }
        }

        RowLayout {
            Layout.fillWidth: true
            visible: taskList.selectionMode
            spacing: 8
            Text { text: "已选 " + taskList.selectedCount }
            Item { Layout.fillWidth: true }
            Button { text: "全选"; onClicked: taskList.selectAll() }
            Button { text: "删除选中"; onClicked: backend.removeSelected() }
            Button { text: "取消"; onClicked: taskList.setSelectionMode(false) }
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

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            Text {
                anchors.centerIn: parent
                horizontalAlignment: Text.AlignHCenter
                text: "还没有下载任务\n粘贴链接开始"
                opacity: 0.6
                visible: listView.count === 0
            }

            ListView {
                id: listView
                anchors.fill: parent
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
                    completed: model.completed
                    output: model.output
                    selectionMode: taskList.selectionMode
                    selected: model.selected
                    fileCount: model.fileCount
                    onDeleteRequested: function(taskId) {
                        taskPage.pendingDelete = taskId
                        deleteDialog.open()
                    }
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

    Connections {
        target: backend
        function onFilesRequested() { fileDialog.open() }
    }

    Dialog {
        id: fileDialog
        title: "选择下载文件"
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        onAccepted: backend.confirmFiles()

        ListView {
            implicitWidth: 460
            implicitHeight: 320
            clip: true
            model: backend.filesModel
            delegate: RowLayout {
                width: ListView.view.width
                spacing: 10
                CheckBox { checked: model.selected; onClicked: backend.filesModel.toggle(index) }
                Text { text: model.path; Layout.fillWidth: true; elide: Text.ElideMiddle }
                Text { text: model.sizeText; opacity: 0.7 }
            }
        }

        Component.onCompleted: {
            const ok = standardButton(Dialog.Ok)
            if (ok) ok.text = "确定"
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
