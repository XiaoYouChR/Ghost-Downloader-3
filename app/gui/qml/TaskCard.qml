import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI

// 通用任务卡（复刻旧 GD 的 UniversalTaskCard 版式）。只展示 + 把动作转成 backend/taskList 意图，不含业务判断。
// 单个开关靠 running 切图标，按了发 toggle 意图、由引擎决定暂停还是继续。
// pack 专属段（BT 上传/Peers、M3U8 直播）后续经片段槽接入，此处只管通用形态。
Frame {
    id: card

    property string taskId
    property string fileName
    property string typeIcon: "ic_fluent_document_20_filled"
    property bool running
    property bool completed
    property real progress
    property string speedText
    property string leftTimeText
    property string progressText
    property var chips: []
    property string errorText
    property bool selectionMode
    property bool selected
    property int fileCount
    property string output

    // 卡片不直接删/改，只发意图，由页面弹框（动作即意图）
    signal deleteRequested(string taskId)
    signal editRequested(string taskId, string fileName)
    signal hashRequested(string taskId)

    padding: 0
    height: 60
    border.color: selected ? Theme.currentTheme.colors.primaryColor : Theme.currentTheme.colors.cardBorderColor

    // 选择模式整卡点击切勾选；双击已完成开文件；右键改名（完整右键菜单后续）
    TapHandler {
        enabled: card.selectionMode
        onTapped: taskList.toggleSelect(card.taskId)
    }
    TapHandler {
        onDoubleTapped: if (card.completed) backend.openFile(card.output)
    }
    TapHandler {
        acceptedButtons: Qt.RightButton
        onTapped: card.editRequested(card.taskId, card.fileName)
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 12
        anchors.rightMargin: 10
        spacing: 10

        CheckBox {
            visible: card.selectionMode
            checked: card.selected
            onClicked: taskList.toggleSelect(card.taskId)
        }

        Icon {
            icon: card.typeIcon
            size: 36
            color: Theme.currentTheme.colors.primaryColor
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2

            Text {
                Layout.fillWidth: true
                typography: Typography.BodyStrong
                text: card.fileName
                elide: Text.ElideRight
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 14

                Row {
                    spacing: 5
                    visible: card.completed
                    Icon {
                        icon: "ic_fluent_info_20_regular"; size: 14
                        anchors.verticalCenter: parent.verticalCenter
                        color: Theme.currentTheme.colors.textSecondaryColor
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        typography: Typography.Caption; text: "任务已经完成"
                        color: Theme.currentTheme.colors.textSecondaryColor
                    }
                }
                Row {
                    spacing: 5
                    visible: !card.completed && card.speedText !== ""
                    Icon {
                        icon: "ic_fluent_top_speed_20_regular"; size: 14
                        anchors.verticalCenter: parent.verticalCenter
                        color: Theme.currentTheme.colors.textSecondaryColor
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        typography: Typography.Caption; text: card.speedText
                        color: Theme.currentTheme.colors.textSecondaryColor
                    }
                }
                Row {
                    spacing: 5
                    visible: !card.completed && card.leftTimeText !== "" && card.leftTimeText !== "--"
                    Icon {
                        icon: "ic_fluent_clock_20_regular"; size: 14
                        anchors.verticalCenter: parent.verticalCenter
                        color: Theme.currentTheme.colors.textSecondaryColor
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        typography: Typography.Caption; text: card.leftTimeText
                        color: Theme.currentTheme.colors.textSecondaryColor
                    }
                }
                Row {
                    spacing: 5
                    visible: !card.completed && card.progressText !== ""
                    Icon {
                        icon: "ic_fluent_document_20_regular"; size: 14
                        anchors.verticalCenter: parent.verticalCenter
                        color: Theme.currentTheme.colors.textSecondaryColor
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        typography: Typography.Caption; text: card.progressText
                        color: Theme.currentTheme.colors.textSecondaryColor
                    }
                }
                // pack 专属 chips（BT 的 Peers/Seeds·↑上传、M3U8 的直播态）——核心只渲染，不认识具体 pack
                Repeater {
                    model: card.chips
                    delegate: Text {
                        typography: Typography.Caption
                        text: modelData
                        color: Theme.currentTheme.colors.textSecondaryColor
                    }
                }
                Text {
                    visible: card.errorText !== ""
                    Layout.fillWidth: true
                    typography: Typography.Caption
                    text: card.errorText
                    color: "#C42B1C"
                    elide: Text.ElideRight
                }
                Item { Layout.fillWidth: true }
            }
        }

        ToolButton {
            icon.name: card.running ? "ic_fluent_pause_20_filled" : "ic_fluent_play_20_filled"
            highlighted: !card.completed
            enabled: !card.completed
            size: 17
            onClicked: backend.toggle(card.taskId)
        }
        ToolButton {
            icon.name: "ic_fluent_library_20_regular"; size: 17
            visible: card.fileCount > 1
            onClicked: backend.editFiles(card.taskId)
        }
        ToolButton {
            icon.name: "ic_fluent_fingerprint_20_regular"; size: 17
            visible: card.completed
            onClicked: card.hashRequested(card.taskId)
        }
        ToolButton {
            icon.name: "ic_fluent_open_20_regular"; size: 17
            visible: card.completed
            onClicked: backend.openFile(card.output)
        }
        ToolButton {
            icon.name: "ic_fluent_folder_20_regular"; size: 17
            visible: card.completed
            onClicked: backend.openFolder(card.output)
        }
        ToolButton {
            icon.name: "ic_fluent_dismiss_20_regular"; size: 17; flat: true
            onClicked: card.deleteRequested(card.taskId)
        }
    }

    ProgressBar {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: 6
        anchors.rightMargin: 6
        anchors.bottomMargin: 2
        from: 0
        to: 100
        value: card.progress
        visible: !card.completed
    }
}
