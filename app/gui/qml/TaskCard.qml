import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI

// 一张任务卡。只展示 + 把按钮点击转成 backend 命令，不含业务逻辑。
Frame {
    id: card

    property string taskId
    property string fileName
    property string status

    height: 60

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 14
        spacing: 12

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text { text: card.fileName; typography: Typography.BodyStrong }
            Text { text: card.status; typography: Typography.Caption }
        }

        Button {
            text: "暂停"
            onClicked: backend.pause(card.taskId)
        }
        Button {
            text: "删除"
            onClicked: backend.remove(card.taskId)
        }
    }
}
