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
    property string url
    property string typeIcon: "ic_fluent_document_20_filled"
    property string categoryIcon
    property bool running
    property bool completed
    property real progress
    property string speedText
    property string leftTimeText
    property string progressText
    property string statusText
    property var chips: []
    property var segments: []
    property string actionKind: "toggle"
    property string errorText
    property bool selectionMode
    property bool selected
    property int fileCount
    property string output

    // 卡片不直接删/改，只发意图，由页面弹框（动作即意图）
    signal deleteRequested(string taskId)
    signal editRequested(string taskId, string fileName, string url)
    signal hashRequested(string taskId)
    signal redownloadRequested(string taskId)

    padding: 0
    height: 60
    border.color: selected ? Theme.currentTheme.colors.primaryColor : Theme.currentTheme.colors.cardBorderColor

    // 选择模式整卡点击切勾选；双击已完成开文件；右键编辑（改名/换链接，完整右键菜单后续）
    TapHandler {
        enabled: card.selectionMode
        onTapped: taskList.toggleSelect(card.taskId)
    }
    TapHandler {
        onDoubleTapped: if (card.completed) backend.openFile(card.output)
    }
    TapHandler {
        acceptedButtons: Qt.RightButton
        onTapped: cardMenu.popup()
    }

    // 右键菜单（复刻原版）：复制链接 / 编辑参数（重新下载/移动分类后续补）
    Menu {
        id: cardMenu
        MenuItem { text: "复制下载链接"; onTriggered: backend.copyToClipboard(card.url) }
        MenuItem { text: "编辑任务参数"; onTriggered: card.editRequested(card.taskId, card.fileName, card.url) }
        MenuItem { text: "重新下载"; onTriggered: card.redownloadRequested(card.taskId) }
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

        Image {
            // 真实 OS 文件类型图标（复刻原版 QFileIconProvider），按文件名解析
            Layout.preferredWidth: 40
            Layout.preferredHeight: 40
            source: "image://fileicon/" + encodeURIComponent(card.fileName)
            sourceSize.width: 40
            sourceSize.height: 40
            fillMode: Image.PreserveAspectFit
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2

            RowLayout {
                Layout.fillWidth: true
                spacing: 5

                // 自动分类小图标（复刻原版）：文件名命中分类且开了自动分类才显
                Icon {
                    visible: card.categoryIcon !== "" && backend.config.enableCategory
                    icon: card.categoryIcon
                    size: 14
                    color: Theme.currentTheme.colors.textSecondaryColor
                }
                Text {
                    Layout.fillWidth: true
                    typography: Typography.BodyStrong
                    text: card.fileName
                    elide: Text.ElideRight
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 14

                // 非运行态的状态文字（完成/暂停/等待，引擎算好）；运行态隐藏，让位给速度/进度
                Row {
                    spacing: 5
                    visible: card.statusText !== ""
                    Icon {
                        icon: "ic_fluent_info_20_regular"; size: 14
                        anchors.verticalCenter: parent.verticalCenter
                        color: Theme.currentTheme.colors.textSecondaryColor
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        typography: Typography.Caption; text: card.statusText
                        color: Theme.currentTheme.colors.textSecondaryColor
                    }
                }
                Row {
                    spacing: 5
                    visible: card.running && card.speedText !== ""
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
                    visible: card.running && card.leftTimeText !== "" && card.leftTimeText !== "--"
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
                    visible: card.running && card.progressText !== ""
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
            // finalize（直播）显「停止定案」对勾，否则按 running 切暂停/继续；点了发统一 primaryAction 意图
            icon.name: card.actionKind === "finalize"
                ? "ic_fluent_checkmark_circle_20_filled"
                : (card.running ? "ic_fluent_pause_20_filled" : "ic_fluent_play_20_filled")
            highlighted: !card.completed
            enabled: !card.completed
            size: 17
            onClicked: backend.primaryAction(card.taskId)
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

    // 底部进度：HTTP 多线程有分段就画一排矩形（复刻原版 SegmentedProgressBar），否则普通进度条
    Item {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: 6
        anchors.rightMargin: 6
        anchors.bottomMargin: 2
        height: 4
        visible: !card.completed

        ProgressBar {
            anchors.fill: parent
            from: 0; to: 100; value: card.progress
            visible: card.segments.length === 0
        }
        // 分段：背景轨 + 每连接已下区间矩形
        Rectangle {
            anchors.fill: parent; radius: 2
            visible: card.segments.length > 0
            color: Theme.currentTheme.colors.primaryColor; opacity: 0.15
        }
        Repeater {
            model: card.segments
            delegate: Rectangle {
                height: parent.height; radius: 2
                color: Theme.currentTheme.colors.primaryColor
                x: parent.width * modelData.start / 100
                width: Math.max(1, parent.width * (modelData.end - modelData.start) / 100)
            }
        }
    }
}
