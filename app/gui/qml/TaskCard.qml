import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI

// 一张任务卡。只展示 + 把按钮点击转成 backend 命令，不含业务逻辑。
// 「暂停 / 继续」靠 running 布尔做 visible 绑定切换，判断在 Python 侧。
Frame {
    id: card

    property string taskId
    property string fileName
    property string status
    property bool running
    property real progress
    property string speedText
    property string progressText
    property bool completed
    property string output
    property string errorText
    property bool selectionMode
    property bool selected
    property int fileCount

    // 卡片不直接删，只发意图；由页面弹确认框（Q5：动作即意图）
    signal deleteRequested(string taskId)

    height: 68

    // 双击已完成任务直接打开文件（GD 同款便利）
    TapHandler {
        onDoubleTapped: if (card.completed) backend.openFile(card.output)
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 14
        spacing: 12

        CheckBox {
            visible: card.selectionMode
            checked: card.selected
            onClicked: taskList.toggleSelect(card.taskId)
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text { text: card.fileName; typography: Typography.BodyStrong }
            RowLayout {
                spacing: 10
                Text { text: card.status; typography: Typography.Caption }
                Text { text: card.progressText; typography: Typography.Caption; visible: card.progressText !== "" }
                Text { text: card.speedText; typography: Typography.Caption; visible: card.speedText !== "" }
                Text {
                    text: card.errorText
                    typography: Typography.Caption
                    color: "#C42B1C"
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                    visible: card.errorText !== ""
                }
            }
            ProgressBar {
                Layout.fillWidth: true
                from: 0
                to: 100
                value: card.progress
            }
        }

        Button {
            text: "选择文件"
            visible: card.fileCount > 1
            onClicked: backend.editFiles(card.taskId)
        }
        Button {
            text: "暂停"
            visible: card.running
            onClicked: backend.pause(card.taskId)
        }
        Button {
            text: "继续"
            visible: !card.running && !card.completed
            onClicked: backend.resume(card.taskId)
        }
        Button {
            text: "打开"
            visible: card.completed
            onClicked: backend.openFile(card.output)
        }
        Button {
            text: "文件夹"
            visible: card.completed
            onClicked: backend.openFolder(card.output)
        }
        Button {
            text: "删除"
            onClicked: card.deleteRequested(card.taskId)
        }
    }
}
