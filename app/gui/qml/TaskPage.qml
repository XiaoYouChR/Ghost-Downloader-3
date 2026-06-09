import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI

// 下载任务页：顶部加链接，下面列出 taskList 里的任务卡。所有动作经 backend 发命令。
FluentPage {
    title: "下载任务"

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 10

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
            model: taskList
            delegate: TaskCard {
                width: ListView.view.width
                taskId: model.taskId
                fileName: model.title
                status: model.status
            }
        }
    }

    function addCurrent() {
        if (urlInput.text.trim() === "")
            return
        backend.addTask(urlInput.text.trim())
        urlInput.text = ""
    }
}
